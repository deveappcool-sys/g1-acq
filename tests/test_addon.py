"""The mitmproxy layer: decoding, compression round-trip and the report hook.

These use real mitmproxy flow objects but never open a socket, so they also
cover cases the end-to-end chain does not (gzip/br responses, binary bodies).
"""

from __future__ import annotations

import gzip
import json

import pytest

pytest.importorskip("mitmproxy")

from mitmproxy import http  # noqa: E402
from mitmproxy.test import tflow  # noqa: E402

import g1_addon  # noqa: E402
from g1acq import config  # noqa: E402
from g1acq.app import G1App  # noqa: E402
from g1acq.store import MemoryStore  # noqa: E402

TARGET = "g1.2tb.ai.12months_ip_90p"
SOURCE = "g1.ios.2tb.monthly.v1"


def make_addon() -> tuple[g1_addon.G1Addon, MemoryStore]:
    store = MemoryStore()
    addon = g1_addon.G1Addon()
    addon.app = G1App(store)
    addon.settings = config.Settings()
    return addon, store


def flow_for(url: str, payload: bytes, headers: dict | None = None) -> http.HTTPFlow:
    flow = tflow.tflow(resp=True)
    flow.request = http.Request.make("GET", url)
    flow.response = http.Response.make(200, payload, headers or {})
    return flow


def test_gzip_body_is_rewritten_and_stays_gzip():
    addon, store = make_addon()
    # Response.make() encodes the payload according to content-encoding, so the
    # plain bytes go in and gzip comes out.
    original = json.dumps({"offers": [SOURCE]}).encode()
    flow = flow_for(
        "https://one.google.com/ai?x=1",
        original,
        {"content-type": "application/json", "content-encoding": "gzip"},
    )
    addon.response(flow)

    assert flow.response.headers["content-encoding"] == "gzip"
    body = json.loads(gzip.decompress(flow.response.raw_content))
    assert body["offers"] == [TARGET]
    assert flow.response.headers["content-length"] == str(
        len(flow.response.raw_content)
    )
    record = json.loads(store.read(config.TEST_KEY))
    assert record["hitCount"] == 1


def test_brotli_body_is_decoded(monkeypatch):
    addon, store = make_addon()
    pytest.importorskip("brotli")
    import brotli

    original = json.dumps({"offers": [SOURCE]}).encode()
    flow = flow_for(
        "https://one.google.com/ai?x=1",
        original,
        {"content-type": "application/json", "content-encoding": "br"},
    )
    addon.response(flow)
    assert json.loads(brotli.decompress(flow.response.raw_content))["offers"] == [TARGET]
    assert json.loads(store.read(config.TEST_KEY))["hitCount"] == 1


def test_binary_response_is_counted_as_nontext_and_left_alone():
    addon, store = make_addon()
    payload = bytes(range(256))
    flow = flow_for(
        "https://one.google.com/plans",
        payload,
        {"content-type": "application/octet-stream"},
    )
    addon.response(flow)

    assert flow.response.raw_content == payload
    scan = json.loads(store.read(config.SCAN_KEY))
    assert scan["nonTextResponses"] == 1
    assert scan["scannedResponses"] == 0
    assert scan["recentResponses"][-1]["status"] == "non-text"


def test_undecodable_utf8_is_treated_as_nontext():
    addon, store = make_addon()
    flow = flow_for("https://one.google.com/plans", b"\xff\xfe\x00bad", {"content-type": "text/plain"})
    addon.response(flow)
    assert json.loads(store.read(config.SCAN_KEY))["nonTextResponses"] == 1


def test_oversized_bodies_are_left_alone_but_still_counted():
    addon, store = make_addon()
    addon.settings = config.Settings(max_body_bytes=8)
    payload = (SOURCE * 5).encode()
    flow = flow_for("https://one.google.com/ai?x=1", payload, {"content-type": "text/plain"})
    addon.response(flow)
    assert flow.response.raw_content == payload
    # A skipped body is still a response that arrived: it is counted as
    # non-text, exactly like an undecodable one.
    assert json.loads(store.read(config.SCAN_KEY))["nonTextResponses"] == 1
    assert store.read(config.TEST_KEY) is not None


def test_report_request_is_answered_without_upstream():
    addon, store = make_addon()
    flow = tflow.tflow(resp=False)
    flow.request = http.Request.make("GET", "https://one.google.com/g1-sku-report")
    assert flow.response is None

    addon.request(flow)

    assert flow.response is not None
    assert flow.response.status_code == 200
    assert flow.response.headers["x-g1-report-version"] == config.REPORT_VERSION
    assert "G1 ACQ 旁路已接管" in flow.response.get_text()


def test_report_traffic_is_not_scanned_again():
    addon, store = make_addon()
    flow = tflow.tflow(resp=False)
    flow.request = http.Request.make("GET", "https://one.google.com/g1-sku-report")
    addon.request(flow)
    before = flow.response.raw_content

    addon.response(flow)  # mitmproxy fires this for synthetic responses too

    assert flow.response.raw_content == before
    assert store.read(config.SCAN_KEY) is None


def test_unrelated_hosts_are_ignored():
    addon, store = make_addon()
    flow = flow_for("https://example.com/ai?x=1", SOURCE.encode(), {"content-type": "text/plain"})
    addon.response(flow)
    assert flow.response.raw_content == SOURCE.encode()
    assert store.as_dict() == {}


def test_errors_in_the_hook_never_raise(monkeypatch):
    addon, _ = make_addon()

    def boom(*args, **kwargs):
        raise RuntimeError("storage exploded")

    monkeypatch.setattr(addon.app, "on_response", boom)
    flow = flow_for("https://one.google.com/ai?x=1", b"{}", {"content-type": "application/json"})
    addon.response(flow)  # must not raise
    assert flow.response.raw_content == b"{}"


def test_empty_body_counts_as_an_empty_text_response():
    addon, store = make_addon()
    flow = flow_for("https://one.google.com/plans", b"", {"content-type": "text/plain"})
    addon.response(flow)
    scan = json.loads(store.read(config.SCAN_KEY))
    assert scan["scannedResponses"] == 1
    assert scan["nonTextResponses"] == 0
    assert scan["recentResponses"][-1]["status"] == "no-skus"


def test_missing_body_counts_as_nontext():
    addon, store = make_addon()
    flow = flow_for("https://one.google.com/plans", b"", {"content-type": "text/plain"})
    # Reproduce a HEAD/304-style response with no body at all.
    flow.response.raw_content = None
    flow.response.headers.pop("content-length", None)
    addon.response(flow)
    scan = json.loads(store.read(config.SCAN_KEY))
    assert scan["scannedResponses"] == 0
    assert scan["nonTextResponses"] == 1


def test_every_module_level_name_the_addon_uses_is_imported():
    """A missing import only shows up at runtime, inside mitmproxy, as a crash.

    That has bitten twice: `i18n` and `discovery` were used before they were
    imported, and mitmproxy turns the resulting NameError into "Error logged
    during startup, exiting".  ``symtable`` tells us exactly which names a
    function resolves at module scope, so this catches it without running the
    addon.
    """
    import pathlib
    import symtable

    source = pathlib.Path(g1_addon.__file__).read_text(encoding="utf-8")
    table = symtable.symtable(source, "g1_addon.py", "exec")
    module_names = {symbol.get_name() for symbol in table.get_symbols()}
    builtins = set(dir(__builtins__)) if not isinstance(__builtins__, dict) else set(__builtins__)

    missing: set[str] = set()

    def walk(scope) -> None:
        for symbol in scope.get_symbols():
            name = symbol.get_name()
            if symbol.is_global() and name not in module_names and name not in builtins:
                missing.add(name)
        for child in scope.get_children():
            walk(child)

    walk(table)
    assert not missing, f"used but never imported: {sorted(missing)}"
