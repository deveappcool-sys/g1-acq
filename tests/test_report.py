"""Local report page and JSON export."""

from __future__ import annotations

import json
import re

import pytest
from conftest import (
    LEGACY_TARGET,
    REPORT,
    SCAN_KEY,
    SOURCE,
    TARGET,
    TEST_KEY,
    THIRTY,
    THIRTY_FALLBACK,
    TWENTY,
    TWENTY_TARGET,
    Harness,
)

from g1acq import config

JSON_URL = REPORT + "?format=json"


def _json(harness: Harness, url: str = JSON_URL) -> dict:
    payload = harness.report(url)
    assert payload, f"report must answer {url}"
    return json.loads(payload["response"]["body"])


def _html(harness: Harness, url: str = REPORT) -> str:
    payload = harness.report(url)
    assert payload, f"report must answer {url}"
    return payload["response"]["body"]


def test_report_shows_captured_ids_without_external_assets():
    h = Harness()
    h.response(SOURCE)
    payload = h.report(REPORT)
    body = payload["response"]["body"]
    assert payload["response"]["status"] == 200
    assert re.search("Google One SKU 本地报告", body)
    assert SOURCE in body
    assert TARGET in body
    assert f"G1 ACQ 旁路已接管 · {config.REPORT_VERSION}" in body
    assert re.search(
        r"<button\b[^>]*name=format[^>]*value=json[^>]*>导出 JSON</button>", body
    )
    assert not re.search(r"<(?:script|img|iframe)\b", body, re.IGNORECASE)
    assert payload["response"]["headers"]["Cache-Control"] == "no-store"


def test_export_form_resolves_to_a_json_attachment_and_allows_trailing_slash():
    h = Harness()
    h.response(SOURCE)
    html = _html(h, REPORT + "/")
    match = re.search(
        r'<form method=get action="([^"]+)"><button type=submit name=format value=json>',
        html,
    )
    assert match, "the visible export button must submit a GET form"
    export_url = match.group(1) + "?format=json"

    for url in (export_url, REPORT + "/?format=json"):
        payload = h.report(url)
        headers = payload["response"]["headers"]
        assert payload["response"]["status"] == 200
        assert headers["Content-Disposition"] == 'attachment; filename="g1-sku-report.json"'
        assert headers["X-G1-Report-Version"] == config.REPORT_VERSION
        data = json.loads(payload["response"]["body"])
        assert data["reportVersion"] == config.REPORT_VERSION
        assert data["configuredTarget"] == TARGET
        assert data["test"]["target"] == TARGET
        assert data["test"]["targetOrigin"] == "user-specified"
        assert data["scan"]["skus"][0]["id"] == SOURCE
        assert data["test"]["matchedFrom"][0]["to"] == TARGET
        assert any(
            f"[g1-sku-report] {config.REPORT_VERSION} json" in line for line in h.logs
        )


def test_report_exports_each_actual_target_and_separates_annual_hits():
    h = Harness()
    h.response(json.dumps([SOURCE, TWENTY, THIRTY, THIRTY_FALLBACK]))
    data = _json(h)["test"]
    assert data["version"] == config.COLLECTOR_VERSION
    assert data["hitCount"] == 3
    assert data["annualHitCount"] == 1
    assert next(row for row in data["matchedFrom"] if row["id"] == TWENTY)["to"] == TWENTY_TARGET
    assert next(row for row in data["matchedFrom"] if row["id"] == THIRTY) == {
        "id": THIRTY,
        "count": 1,
        "to": THIRTY_FALLBACK,
        "fallback": True,
    }
    html = _html(h)
    assert "最近一次三档映射" in html
    assert "其中 2TB：1" in html
    assert TWENTY_TARGET in html
    assert THIRTY_FALLBACK in html


def test_report_displays_legacy_v1_records_with_their_original_target():
    h = Harness(
        {
            TEST_KEY: json.dumps(
                {
                    "schemaVersion": 1,
                    "version": "pro-annual-test-v1",
                    "hitCount": 2,
                    "status": "rewritten",
                    "matchedFrom": [{"id": SOURCE, "count": 2}],
                }
            )
        }
    )
    data = _json(h)["test"]
    assert data["version"] == "pro-annual-test-v1"
    assert data["hitCount"] == 2
    assert data["annualHitCount"] == 2
    assert data["target"] == LEGACY_TARGET
    assert data["targetOrigin"] == "legacy"
    assert data["matchedFrom"] == [
        {"id": SOURCE, "count": 2, "to": LEGACY_TARGET, "fallback": False}
    ]

    empty = Harness(
        {
            TEST_KEY: json.dumps(
                {
                    "schemaVersion": 1,
                    "version": "pro-annual-test-v1",
                    "hitCount": 0,
                    "status": "no-match",
                    "matchedFrom": [],
                }
            )
        }
    )
    assert "旧 v1 记录：本次响应未命中 iOS 2TB 前缀" in _html(empty)


@pytest.mark.parametrize(
    "version, prior_target, origin",
    [
        ("g1-acq-v7.1", LEGACY_TARGET, "legacy"),
        ("g1-acq-v7.2", "g1.2tb.ai.annual.3months_ip_90p.acq", "pattern-derived"),
        ("g1-acq-v7.3", "g1.2tb.ai.annual_ip_90p.acq", "user-specified"),
        ("g1-acq-v7.4", "g1.2tb.ai.annual_ip_90p.acq", "user-specified"),
    ],
)
def test_report_preserves_saved_targets_and_origins(version, prior_target, origin):
    record = {
        "schemaVersion": 1,
        "version": version,
        "target": prior_target,
        "status": "rewritten",
        "hitCount": 9,
        "annualHitCount": 9,
        "matchedFrom": [
            {"id": "g1.ios.2tb.ai.a", "to": prior_target, "count": 9, "fallback": False}
        ],
    }
    if origin != "legacy":
        record["targetOrigin"] = origin
    h = Harness({TEST_KEY: json.dumps(record)})
    before = h.raw(TEST_KEY)

    data = _json(h)
    assert data["configuredTarget"] == TARGET
    assert data["test"]["version"] == version
    assert data["test"]["target"] == prior_target
    assert data["test"]["targetOrigin"] == origin
    assert data["test"]["matchedFrom"][0]["to"] == prior_target
    assert h.raw(TEST_KEY) == before

    html = _html(h)
    assert f"当前配置的 2TB 候选目标：<code>{TARGET}</code>" in html
    assert f"该次记录的 2TB 目标：<code>{prior_target}</code>" in html


def test_empty_report_still_reports_the_configured_target():
    data = _json(Harness())
    assert data["configuredTarget"] == TARGET
    assert data["test"]["target"] == ""
    assert data["test"]["targetOrigin"] == ""
    assert data["test"]["status"] == ""


def test_json_export_is_limited_and_escapes_untrusted_html():
    h = Harness(
        {
            SCAN_KEY: json.dumps(
                {
                    "schemaVersion": 1,
                    "updatedAt": "<script>fixture</script>",
                    "scannedResponses": 1,
                    "secret": "must-not-export",
                    "body": "must-not-export",
                    "skus": [
                        {
                            "id": SOURCE,
                            "count": 2,
                            "lastSeen": "<img src=x>",
                            "secret": "must-not-export",
                        }
                    ],
                }
            )
        }
    )
    payload = h.report(JSON_URL)
    assert "application/json" in payload["response"]["headers"]["Content-Type"]
    body = payload["response"]["body"]
    report = json.loads(body)
    assert report["scan"]["skus"][0]["id"] == SOURCE
    assert "must-not-export" not in body

    html = _html(h)
    assert "<script>fixture" not in html
    assert "&lt;img src=x&gt;" in html


def test_activity_export_rejects_malformed_metadata():
    event = {
        "at": "2026-11-23T07:40:06.325Z",
        "path": "/plans",
        "bodyType": "text",
        "status": "known-skus",
        "candidateCount": 2,
        "addedCount": 0,
        "omittedCount": 0,
        "body": "private-body",
        "query": "private-token",
    }
    h = Harness(
        {
            SCAN_KEY: json.dumps(
                {
                    "schemaVersion": 1,
                    "version": config.COLLECTOR_VERSION,
                    "recentResponses": [
                        event,
                        {**event, "at": "<script>private</script>"},
                        {**event, "status": "constructor"},
                        {**event, "bodyType": "unknown"},
                    ],
                }
            )
        }
    )
    payload = h.report(JSON_URL)
    data = json.loads(payload["response"]["body"])
    assert data["scan"]["recentResponses"] == [
        {
            "at": event["at"],
            "path": event["path"],
            "bodyType": "text",
            "status": "known-skus",
            "candidateCount": 2,
            "addedCount": 0,
            "omittedCount": 0,
        }
    ]
    assert "private" not in payload["response"]["body"]


def test_clear_action_affects_only_the_two_keys():
    h = Harness(
        {
            SCAN_KEY: json.dumps({"schemaVersion": 1, "skus": [{"id": SOURCE, "count": 1}]}),
            TEST_KEY: json.dumps({"schemaVersion": 1, "hitCount": 1}),
            "other-tool": "untouched",
        }
    )
    h.report(REPORT + "?clear=1")
    assert h.get(SCAN_KEY) == {}
    assert h.get(TEST_KEY) == {}
    assert h.map.read("other-tool") == "untouched"
    assert set(h.reads) == {SCAN_KEY, TEST_KEY}


def test_report_survives_unavailable_storage_and_ignores_other_paths():
    unavailable = Harness(storage_available=False)
    data = json.loads(unavailable.report(JSON_URL)["response"]["body"])
    assert data["storageAvailable"] is False

    for url in ("https://one.google.com/ai?x=1", REPORT + "-other", "https://example.test/g1-sku-report"):
        h = Harness()
        assert h.report(url) == {}
        assert h.reads == []


def test_clear_message_is_rendered():
    h = Harness()
    html = _html(h, REPORT + "?clear=1")
    assert "本工具的两份本地记录已清空。" in html


def test_unreadable_state_file_is_reported_as_unavailable(tmp_path):
    from g1acq.store import FileStore

    # A directory in the place of the state file cannot be read as JSON.
    broken = tmp_path / "state.json"
    broken.mkdir()
    store = FileStore(broken)
    from g1acq.report import build_report

    response = build_report(store, REPORT + "?format=json")
    data = json.loads(response.body)
    assert data["storageAvailable"] is False
    assert data["scan"]["skus"] == []
