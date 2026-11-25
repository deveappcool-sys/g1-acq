"""Discovery mode: can we see what Apple says about an injected product ID?"""

from __future__ import annotations

import json

import pytest

from g1acq import discovery, launch


@pytest.mark.parametrize("host", [
    "buy.itunes.apple.com",
    "sandbox.itunes.apple.com",
    "p24-buy.itunes.apple.com",
    "sf-api-token-service.itunes.apple.com",
    "apps.apple.com",
])
def test_store_hosts_are_recognised(host):
    assert discovery.is_store_host(host)


@pytest.mark.parametrize("host", [
    "one.google.com",
    "buy.itunes.apple.com.evil.test",
    "evil-buy.itunes.apple.com",
    "itunes.apple.com",
])
def test_lookalike_hosts_are_not(host):
    assert not discovery.is_store_host(host)


def test_product_ids_are_extracted_from_raw_bytes():
    blob = b'{"ids":["g1.20tb.1month_eft.acq","g1.2tb.ai.12months_ip_90p"]}'
    assert discovery._ids(blob) == ["g1.20tb.1month_eft.acq", "g1.2tb.ai.12months_ip_90p"]


def test_binary_payloads_do_not_break_extraction():
    blob = b"bplist00\x00\x01g1.20tb.v2\xff\xfe garbage"
    assert "g1.20tb.v2" in discovery._ids(blob)


def test_record_and_summary(tmp_path):
    log = discovery.Discoveries(tmp_path / "d.jsonl")
    log.record(host="buy.itunes.apple.com", url="https://buy.itunes.apple.com/WebObjects/x?token=SECRET",
               method="POST", status=200, content_type="application/json",
               request_body=b'["g1.20tb.1month_eft.acq","g1.bogus.id"]',
               response_body=b'{"products":[{"id":"g1.20tb.1month_eft.acq","price":"0"}]}')

    rows = {row["id"]: row for row in log.summary()}
    assert rows["g1.20tb.1month_eft.acq"]["verdict"] == "answered"
    assert rows["g1.bogus.id"]["verdict"] == "requested-only"

    # the query string (which can carry an account token) must not be persisted
    raw = (tmp_path / "d.jsonl").read_text(encoding="utf-8")
    assert "SECRET" not in raw
    entry = json.loads(raw.splitlines()[0])
    assert entry["path"] == "/WebObjects/x"


def test_missing_log_is_not_an_error(tmp_path):
    log = discovery.Discoveries(tmp_path / "absent.jsonl")
    assert log.entries() == []
    assert log.summary() == []


def test_corrupt_lines_are_skipped(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"requested":["g1.a"],"answered":[]}\nnot json\n[]\n', encoding="utf-8")
    assert len(discovery.Discoveries(path).entries()) == 1


def test_launcher_widens_allow_hosts_only_when_asked():
    plain = launch.build_argv(launch.LaunchOptions())
    assert any("allow_hosts=^one\\.google\\.com" in a for a in plain)

    wide = launch.build_argv(launch.LaunchOptions(discover=True))
    hosts = next(a for a in wide if a.startswith("allow_hosts="))
    assert "one\\.google\\.com" in hosts
    assert "buy\\.itunes\\.apple\\.com" in hosts
    assert "sandbox\\.itunes\\.apple\\.com" in hosts
    # widening alone is useless: the addon must be told to record
    assert "g1_discover=true" in wide
    assert "g1_discover=true" not in plain


@pytest.mark.parametrize("host", [
    "bag.itunes.apple.com",
    "amp-api-edge.apps.apple.com",
])
def test_hosts_found_in_real_storekit_traffic_are_covered(host):
    """These two only showed up when watching a real purchase attempt."""
    assert discovery.is_store_host(host)


def test_launcher_and_matcher_share_one_host_list():
    """They drifted apart once: the launcher intercepted hosts the recorder
    did not recognise, so the discovery log stayed empty."""
    hosts = next(a for a in launch.build_argv(launch.LaunchOptions(discover=True))
                 if a.startswith("allow_hosts="))
    for host in ("bag.itunes.apple.com", "amp-api-edge.apps.apple.com",
                 "buy.itunes.apple.com", "sandbox.itunes.apple.com"):
        assert discovery.is_store_host(host)
        assert host.replace(".", "\\.") in hosts, host
