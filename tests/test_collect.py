"""Passive collection and response-activity diagnostics."""

from __future__ import annotations

import json

from conftest import (
    OTHER_SOURCE,
    SCAN_KEY,
    SOURCE,
    TEST_KEY,
    Harness,
)

from g1acq import config


def test_activity_distinguishes_new_repeated_empty_and_nontext():
    h = Harness()
    url = "https://one.google.com/plans?token=private-token"
    body = " ".join([SOURCE, SOURCE, OTHER_SOURCE])

    h.response(body, url)
    scan = h.get(SCAN_KEY)
    assert scan["recentResponses"][0]["status"] == "new-skus"
    assert scan["recentResponses"][0]["candidateCount"] == 2
    assert scan["recentResponses"][0]["addedCount"] == 2

    h.response(body, url)
    scan = h.get(SCAN_KEY)
    assert len(scan["skus"]) == 2
    assert next(row for row in scan["skus"] if row["id"] == SOURCE)["count"] == 4
    assert scan["scannedResponses"] == 2
    assert scan["matchedResponses"] == 2
    assert scan["recentResponses"][-1]["status"] == "known-skus"
    assert scan["recentResponses"][-1]["candidateCount"] == 2
    assert scan["recentResponses"][-1]["addedCount"] == 0

    h.response("no product in this response", url)
    h.response(None, url)
    scan = h.get(SCAN_KEY)
    assert [event["status"] for event in scan["recentResponses"]] == [
        "new-skus",
        "known-skus",
        "no-skus",
        "non-text",
    ]
    assert scan["scannedResponses"] == 3
    assert scan["matchedResponses"] == 2
    assert scan["nonTextResponses"] == 1
    assert len(scan["skus"]) == 2
    assert scan["recentResponses"][-1]["bodyType"] == "non-text"
    assert scan["recentResponses"][-1]["candidateCount"] == 0
    # Pages outside /ai? must not overwrite the last mapping record.
    assert h.map.read(TEST_KEY) is None
    assert "private-token" not in h.raw(SCAN_KEY)

    data = json.loads(h.report("https://one.google.com/g1-sku-report?format=json")["response"]["body"])
    assert data["scan"]["recentResponses"] == scan["recentResponses"]
    assert data["scan"]["nonTextResponses"] == 1

    html = h.report("https://one.google.com/g1-sku-report")["response"]["body"]
    assert f"实际采集脚本：<code>{config.COLLECTOR_VERSION}</code>" in html
    assert "编号与已有记录重复" in html
    assert "正文不是可扫描文本" in html


def test_recent_activity_keeps_ten_and_redacts_urls():
    valid = {
        "at": "2099-01-01T00:00:00.000Z",
        "path": "/ai",
        "bodyType": "text",
        "status": "no-skus",
        "candidateCount": 0,
        "addedCount": 0,
        "omittedCount": 0,
        "body": "private-history-body",
    }
    h = Harness(
        {
            SCAN_KEY: json.dumps(
                {
                    "schemaVersion": 1,
                    "recentResponses": [
                        valid,
                        {**valid, "path": "/private-secret"},
                        {**valid, "status": "bad-status"},
                    ],
                }
            )
        }
    )
    h.response(SOURCE, "https://one.google.com/plans?secret=1")
    scan = h.get(SCAN_KEY)
    assert len(scan["recentResponses"]) == 2
    assert scan["recentResponses"][0]["at"] == valid["at"]
    # The newest arrival stays last even after a clock change.
    assert scan["recentResponses"][-1]["path"] == "/plans"

    paths = [
        "/",
        "/ai/",
        "/plans/",
        "/_/GoogleOne/account-secret/data/batchexecute",
        "/account/private@example.test",
    ]
    expected = ["/", "/ai", "/plans", "/_/…/data/batchexecute", "[其他 one.google.com 路径]"]
    for index in range(14):
        h.response(
            SOURCE,
            "https://one.google.com"
            + paths[index % 5]
            + "?secret=query#private-fragment",
        )
    scan = h.get(SCAN_KEY)
    assert len(scan["recentResponses"]) == 10
    assert [event["path"] for event in scan["recentResponses"]] == [
        expected[(index + 4) % 5] for index in range(10)
    ]
    assert all(
        event["status"] == "known-skus" and event["addedCount"] == 0
        for event in scan["recentResponses"]
    )
    stored = h.raw(SCAN_KEY)
    for forbidden in (
        "private-history-body",
        "private-secret",
        "account-secret",
        "private@example.test",
        "query",
        "private-fragment",
        "secret=",
    ):
        assert forbidden not in stored


def test_old_scan_records_stay_old_until_a_new_response_arrives():
    old = {
        "schemaVersion": 1,
        "version": "g1-acq-v7.1",
        "updatedAt": "2026-11-23T07:40:18.464Z",
        "scannedResponses": 5,
        "matchedResponses": 1,
        "skus": [{"id": SOURCE, "count": 4, "lastSeen": "2026-11-23T07:40:06.325Z"}],
    }
    h = Harness({SCAN_KEY: json.dumps(old)})
    before = h.raw(SCAN_KEY)

    data = json.loads(
        h.report("https://one.google.com/g1-sku-report?format=json")["response"]["body"]
    )
    assert data["scan"]["version"] == "g1-acq-v7.1"
    assert data["scan"]["recentResponses"] == []
    assert data["scan"]["scannedResponses"] == 5
    assert h.raw(SCAN_KEY) == before

    html = h.report("https://one.google.com/g1-sku-report")["response"]["body"]
    assert "旧采集记录；尚未保存本版采集响应记录" in html

    h.response(SOURCE, "https://one.google.com/plans")
    data = json.loads(
        h.report("https://one.google.com/g1-sku-report?format=json")["response"]["body"]
    )
    assert data["scan"]["version"] == config.COLLECTOR_VERSION
    assert data["scan"]["scannedResponses"] == 6
    assert data["scan"]["matchedResponses"] == 2
    assert len(data["scan"]["skus"]) == 1
    assert data["scan"]["skus"][0]["count"] == 5
    assert len(data["scan"]["recentResponses"]) == 1
    assert data["scan"]["recentResponses"][0]["status"] == "known-skus"
    assert data["scan"]["recentResponses"][0]["addedCount"] == 0


def test_corrupt_storage_recovers_and_accumulates():
    h = Harness({SCAN_KEY: "corrupt JSON"})
    h.response(SOURCE)
    h.response(SOURCE + " g1.2tb.fixture", "https://one.google.com/plans")
    scan = h.get(SCAN_KEY)
    assert scan["scannedResponses"] == 2
    assert len(scan["skus"]) == 2
    assert next(row for row in scan["skus"] if row["id"] == SOURCE)["count"] == 2


def test_write_failure_is_reported_in_logs():
    h = Harness(storage_write_fails=True)
    h.response(SOURCE, "https://one.google.com/plans")
    assert any("saved=no" in line for line in h.logs)


def test_collector_logs_each_candidate_once():
    h = Harness()
    h.response(" ".join([SOURCE, SOURCE, OTHER_SOURCE]), "https://one.google.com/plans")
    candidate_lines = [line for line in h.logs if line.endswith(" x2")]
    assert f"[g1-acq] {SOURCE} x2" in candidate_lines
    assert f"[g1-acq] {OTHER_SOURCE} x1" not in candidate_lines


def test_trailing_newline_ids_are_rejected_on_reload():
    """A stored id must match the whole string, not just up to a newline."""
    stored = {
        "schemaVersion": 1,
        "skus": [{"id": SOURCE + "\n", "count": 9}, {"id": SOURCE, "count": 1}],
    }
    h = Harness({SCAN_KEY: json.dumps(stored)})
    h.response("nothing here", "https://one.google.com/plans")
    ids = [row["id"] for row in h.get(SCAN_KEY)["skus"]]
    assert ids == [SOURCE]
    assert h.get(SCAN_KEY)["skus"][0]["count"] == 1
