"""End-to-end: the exact chain a phone uses.

    client --CONNECT--> mihomo --rule--> mitmdump (G1 ACQ) --TLS--> Google

Everything else is local: a fake Google serves a fixed offer list and a CONNECT
forwarder rewrites the destination, so the suite never touches the network.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from e2e_support import (
    REWRITTEN_SKUS,
    ConnectForwarder,
    FakeGoogle,
    Process,
    free_port,
    https_via_proxy,
    make_certificate,
    mihomo_binary,
    mitmdump_available,
    mitmdump_binary,
    openssl_available,
)

from g1acq import config, launch, profile

pytestmark = pytest.mark.e2e

yaml = pytest.importorskip("yaml")

needs_sidecar = pytest.mark.skipif(
    not (mitmdump_available() and openssl_available()),
    reason="mitmdump and openssl are required for the end-to-end chain",
)
needs_mihomo = pytest.mark.skipif(
    not mihomo_binary(), reason="mihomo binary is required to exercise Clash rules"
)


def _mihomo_profile(directory: Path, sidecar_port: int, mixed_port: int, *,
                    tcp_probe: bool = False) -> Path:
    """Render the same profile the console hands to users, pointed at the test sidecar."""
    text = profile.render(
        profile.ProfileOptions(
            server="127.0.0.1", port=sidecar_port, mixed_port=mixed_port
        )
    )
    if tcp_probe:
        # Same three conditions, but on TCP: mirrors the QUIC guard so the
        # matcher can be observed without crafting UDP traffic.
        text = text.replace("(NETWORK,udp)", "(NETWORK,tcp)")
    path = directory / ("probe.yaml" if tcp_probe else "config.yaml")
    path.write_text(text, encoding="utf-8")
    return path


def _wait_for(predicate, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    if not (mitmdump_available() and openssl_available()):
        pytest.skip("mitmdump and openssl are required")

    directory = tmp_path_factory.mktemp("g1-e2e")
    cert, key = make_certificate(directory)
    google = FakeGoogle(cert, key).start()
    forwarder = ConnectForwarder(google.port).start()

    sidecar_port = free_port()
    state = directory / "state.json"
    # Same launcher the shipped `python -m g1acq serve` uses, so the flags under
    # test are the flags users run.
    argv = launch.build_argv(
        launch.LaunchOptions(
            port=sidecar_port,
            state=str(state),
            upstream=f"http://127.0.0.1:{forwarder.port}",
            extra=(
                "--set",
                "ssl_insecure=true",
                "--set",
                f"confdir={directory / 'mitm'}",
                "--set",
                "termlog_verbosity=info",
            ),
        ),
        mitmdump=mitmdump_binary(),
    )
    mitmdump = Process(argv, directory / "mitmdump.log").start(sidecar_port)

    yield {
        "dir": directory,
        "sidecar_port": sidecar_port,
        "state": state,
        "mitmdump": mitmdump,
        "mihomo": None,
    }

    mitmdump.stop()
    forwarder.stop()
    google.stop()


@needs_sidecar
def test_sidecar_rewrites_the_three_tiers(chain):
    status, headers, body = https_via_proxy(
        chain["sidecar_port"], "one.google.com", "/ai?x=1"
    )
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["offers"] == REWRITTEN_SKUS


@needs_sidecar
def test_state_records_originals_before_rewriting(chain):
    assert _wait_for(lambda: chain["state"].exists())
    payload = json.loads(chain["state"].read_text(encoding="utf-8"))
    scan = json.loads(payload["g1.sku.scan.v1"])
    record = json.loads(payload["g1.pro.annual.test.v1"])

    collected = {row["id"] for row in scan["skus"]}
    assert {"g1.ios.2tb.monthly.v1", "g1.ios.20tb.m.v2", "g1.ios.30tb.ai.pro.m"} <= collected
    # Generated targets must never appear in the passive inventory.
    assert not collected & set(REWRITTEN_SKUS)

    assert record["status"] == "rewritten"
    assert record["hitCount"] == 3
    assert record["annualHitCount"] == 1
    assert scan["recentResponses"][-1]["path"] == "/ai"


@needs_sidecar
def test_report_page_is_answered_locally(chain):
    status, headers, body = https_via_proxy(
        chain["sidecar_port"], "one.google.com", "/g1-sku-report"
    )
    assert status == 200
    assert headers["X-G1-Report-Version"] == config.REPORT_VERSION
    assert headers["Cache-Control"] == "no-store"
    text = body.decode("utf-8")
    assert "G1 ACQ 旁路已接管" in text
    assert "g1.ios.2tb.monthly.v1" in text

    status, headers, body = https_via_proxy(
        chain["sidecar_port"], "one.google.com", "/g1-sku-report?format=json"
    )
    assert status == 200
    assert headers["Content-Disposition"] == 'attachment; filename="g1-sku-report.json"'
    report = json.loads(body)
    assert report["scan"]["skus"]
    assert report["test"]["matchedFrom"]


@needs_mihomo
def test_mihomo_routes_one_google_to_the_sidecar(chain, tmp_path):
    mixed_port = free_port()
    config = _mihomo_profile(tmp_path, chain["sidecar_port"], mixed_port)
    mihomo = Process(
        [mihomo_binary(), "-d", str(tmp_path), "-f", str(config)],
        tmp_path / "mihomo.log",
    ).start(mixed_port)
    try:
        status, _, body = https_via_proxy(mixed_port, "one.google.com", "/ai?x=1")
        assert status == 200
        assert json.loads(body)["offers"] == REWRITTEN_SKUS
        assert _wait_for(lambda: "using G1[G1-MITM]" in mihomo.log)
        assert "match Domain(one.google.com) using G1[G1-MITM]" in mihomo.log
    finally:
        mihomo.stop()


@needs_mihomo
def test_mihomo_quic_guard_matches_the_target(chain, tmp_path):
    mixed_port = free_port()
    config = _mihomo_profile(tmp_path, chain["sidecar_port"], mixed_port, tcp_probe=True)
    mihomo = Process(
        [mihomo_binary(), "-d", str(tmp_path), "-f", str(config)],
        tmp_path / "mihomo-probe.log",
    ).start(mixed_port)
    try:
        try:
            https_via_proxy(mixed_port, "one.google.com", "/ai?x=1", timeout=6)
        except OSError:
            pass  # rejected by design
        assert _wait_for(lambda: "REJECT-DROP" in mihomo.log)
        assert "(DstPort,443)" in mihomo.log
        assert "(Domain,one.google.com)" in mihomo.log
    finally:
        mihomo.stop()
