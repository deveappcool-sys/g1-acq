"""Three-tier mapping contract, ported from the v7.5 offline suite."""

from __future__ import annotations

import json

import pytest
from conftest import (
    DEFAULT_AI_URL,
    OTHER_SOURCE,
    REPORT,
    SCAN_KEY,
    SOURCE,
    TARGET,
    TEST_KEY,
    THIRTY,
    THIRTY_FALLBACK,
    THIRTY_TARGET,
    TWENTY,
    TWENTY_FALLBACK,
    TWENTY_TARGET,
    Harness,
)

from g1acq import config


def legacy_v6_rewrite(body: str) -> str:
    """Independent restatement of the v6 algorithm used for parity checks.

    The original walked SKU_MAP one source at a time, counted plain substring
    occurrences in the original body to decide the fallback, and replaced with
    ``split``/``join``.  No token boundaries were considered.
    """
    present = {
        value
        for value in (*config.SKU_MAP.values(), *config.FALLBACK.values())
        if value in body
    }

    out = body
    for source, default_target in config.SKU_MAP.items():
        if source not in out:
            continue
        target = default_target
        fallback = config.FALLBACK.get(default_target)
        if default_target not in present and fallback and fallback in present:
            target = fallback
        out = out.replace(source, target)
    return out


def test_combined_mapping_keeps_unrelated_tokens():
    untouched = [
        "g1.ios.12tb.fixture",
        TWENTY + ".extra",
        THIRTY + ".extra",
        "g1.ios.2tbx.fixture",
        "prefix" + SOURCE,
        "x." + SOURCE,
        "person@" + SOURCE,
        "g1.2tb",
        TARGET,
    ]
    values = [SOURCE, OTHER_SOURCE, SOURCE, TWENTY, THIRTY, *untouched]
    h = Harness()
    payload = h.response(json.dumps(values))
    assert json.loads(payload["body"]) == [
        TARGET,
        TARGET,
        TARGET,
        TWENTY_TARGET,
        THIRTY_TARGET,
        *untouched,
    ]
    record = h.get(TEST_KEY)
    assert record["hitCount"] == 5
    assert record["annualHitCount"] == 3
    assert record["status"] == "rewritten"
    assert record["version"] == config.COLLECTOR_VERSION
    assert record["matchedFrom"] == [
        {"id": TWENTY, "to": TWENTY_TARGET, "count": 1, "fallback": False},
        {"id": OTHER_SOURCE, "to": TARGET, "count": 1, "fallback": False},
        {"id": SOURCE, "to": TARGET, "count": 2, "fallback": False},
        {"id": THIRTY, "to": THIRTY_TARGET, "count": 1, "fallback": False},
    ]


@pytest.mark.parametrize(
    "body", ["", "g1.ios.100gb.m", "g1.ios.20tb.other", "g1.ios.30tb.other"]
)
def test_unmatched_text_passes_through(body):
    h = Harness()
    assert h.response(body) == {}
    assert h.get(TEST_KEY)["status"] == "no-match"


@pytest.mark.parametrize("body", [None, 123, {}])
def test_nontext_bodies_pass_through(body):
    h = Harness()
    assert h.response(body) == {}
    assert h.get(TEST_KEY)["status"] == "non-text"


def test_fallback_results_match_v6_across_all_offer_combinations():
    offers = [TWENTY_TARGET, THIRTY_TARGET, TWENTY_FALLBACK, THIRTY_FALLBACK]
    for mask in range(16):
        observed = [offer for index, offer in enumerate(offers) if mask & (1 << index)]
        body = json.dumps([TWENTY, THIRTY, TWENTY, *observed])
        h = Harness()
        payload = h.response(body)
        assert payload["body"] == legacy_v6_rewrite(body), f"offer mask={mask}"
        record = h.get(TEST_KEY)
        assert record["hitCount"] == 3
        assert record["annualHitCount"] == 0
        assert record["status"] == "rewritten"


def test_fallback_decisions_are_independent_and_2tb_stays_fixed():
    body = json.dumps(
        [SOURCE, TWENTY, THIRTY, TWENTY_TARGET, TWENTY_FALLBACK, THIRTY_FALLBACK]
    )
    h = Harness()
    payload = h.response(body)
    assert json.loads(payload["body"])[:3] == [TARGET, TWENTY_TARGET, THIRTY_FALLBACK]
    rows = {row["id"]: row for row in h.get(TEST_KEY)["matchedFrom"]}
    assert rows[SOURCE] == {"id": SOURCE, "to": TARGET, "count": 1, "fallback": False}
    assert rows[TWENTY] == {
        "id": TWENTY,
        "to": TWENTY_TARGET,
        "count": 1,
        "fallback": False,
    }
    assert rows[THIRTY] == {
        "id": THIRTY,
        "to": THIRTY_FALLBACK,
        "count": 1,
        "fallback": True,
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://one.google.com/ai",
        "https://one.google.com/ai/other?x=1",
        "https://one.google.com/plans?x=1",
    ],
)
def test_collection_without_rewrite_scope_keeps_last_record(url):
    previous = json.dumps(
        {"schemaVersion": 1, "version": "previous-record", "hitCount": 2}
    )
    h = Harness({TEST_KEY: previous})
    assert h.response(SOURCE, url) == {}
    assert h.map.read(TEST_KEY) == previous
    assert h.get(SCAN_KEY)["skus"][0]["id"] == SOURCE


@pytest.mark.parametrize(
    "url",
    [
        "https://one.google.com.evil/ai?x=1",
        "http://one.google.com/ai?x=1",
        REPORT,
        REPORT + "?format=json",
        REPORT + "/",
        REPORT + "/?format=json",
    ],
)
def test_out_of_scope_urls_touch_nothing(url):
    h = Harness()
    assert h.response(SOURCE, url) == {}
    assert h.map.as_dict() == {}


def test_collection_saves_originals_before_rewriting():
    body = json.dumps([SOURCE, SOURCE, TWENTY, THIRTY, "com.google.one.fixture"])
    h = Harness()
    payload = h.response(body)
    assert json.loads(payload["body"]) == [
        TARGET,
        TARGET,
        TWENTY_TARGET,
        THIRTY_TARGET,
        "com.google.one.fixture",
    ]
    scan = h.get(SCAN_KEY)
    assert scan["version"] == config.COLLECTOR_VERSION
    assert [row["id"] for row in scan["skus"]] == [
        "com.google.one.fixture",
        TWENTY,
        SOURCE,
        THIRTY,
    ]
    assert next(row for row in scan["skus"] if row["id"] == SOURCE)["count"] == 2
    assert h.writes == [SCAN_KEY, TEST_KEY]


def test_escaped_dots_are_discovered_but_not_rewritten():
    escaped = r"g1\u002eios\u002e2tb\u002eescaped"
    h = Harness()
    assert h.response(escaped) == {}
    assert h.get(SCAN_KEY)["skus"][0]["id"] == "g1.ios.2tb.escaped"


def test_full_list_still_maps_and_reports_capacity_loss():
    h = Harness()
    full = " ".join("g1.fixture." + str(index) for index in range(305))
    h.response(full, "https://one.google.com/plans")
    event = h.get(SCAN_KEY)["recentResponses"][-1]
    assert event["status"] == "new-skus"
    assert event["candidateCount"] == 305
    assert event["addedCount"] == 300
    assert event["omittedCount"] == 5

    payload = h.response(SOURCE + " g1.fixture.0")
    assert payload["body"] == TARGET + " g1.fixture.0"
    scan = h.get(SCAN_KEY)
    assert len(scan["skus"]) == 300
    assert scan["truncated"] is True
    assert scan["scannedResponses"] == 2
    assert next(row for row in scan["skus"] if row["id"] == "g1.fixture.0")["count"] == 2
    last = scan["recentResponses"][-1]
    assert last["status"] == "limit-reached"
    assert last["candidateCount"] == 2
    assert last["addedCount"] == 0
    assert last["omittedCount"] == 1


def test_storage_errors_do_not_block_a_matched_response():
    for flags in (
        {"storage_available": False},
        {"storage_throws": True},
        {"storage_write_fails": True},
    ):
        h = Harness(**flags)
        assert h.response(SOURCE)["body"] == TARGET


def test_records_omit_cookies_headers_and_bodies():
    h = Harness()
    h.response(json.dumps({"sku": SOURCE, "email": "private@example.test"}))
    assert "private@example.test" not in h.raw(TEST_KEY)
    assert "secret" not in h.raw(TEST_KEY)
    assert h.reads == [SCAN_KEY]
    assert "private@example.test" not in h.raw(SCAN_KEY)
    assert "secret" not in h.raw(SCAN_KEY)


def test_custom_target_override_is_applied():
    settings = config.Settings(target="g1.2tb.ai.custom_ip_90p")
    h = Harness(settings=settings)
    assert h.response(SOURCE)["body"] == "g1.2tb.ai.custom_ip_90p"
    record = h.get(TEST_KEY)
    assert record["target"] == "g1.2tb.ai.custom_ip_90p"
    assert record["targetOrigin"] == "user-specified"


def test_default_scope_url():
    assert DEFAULT_AI_URL.startswith("https://one.google.com/ai?")


def test_mapping_matches_upstream_v7_6():
    """Pin the table itself: v7.6.0 switched 20TB/30TB to the one-month free trial."""
    assert dict(config.SKU_MAP) == {
        "g1.ios.20tb.m.v2": "g1.20tb.1month_eft.acq",
        "g1.ios.30tb.ai.pro.m": "g1.ai.ultra.1month_eft.acq",
    }
    assert dict(config.FALLBACK) == {
        "g1.20tb.1month_eft.acq": "g1.20tb.3months_ip_90p.acq",
        "g1.ai.ultra.1month_eft.acq": "g1.ai.ultra.3months_ip_90p.acq",
    }
    assert config.DEFAULT_TARGET == "g1.2tb.ai.12months_ip_90p"


def test_free_trial_is_preferred_when_present():
    """Both offers in the body: the free-trial target wins, no fallback flag."""
    body = json.dumps([TWENTY, THIRTY, TWENTY_TARGET, TWENTY_FALLBACK,
                       THIRTY_TARGET, THIRTY_FALLBACK])
    h = Harness()
    payload = h.response(body)
    assert json.loads(payload["body"])[:2] == [TWENTY_TARGET, THIRTY_TARGET]
    rows = {row["id"]: row for row in h.get(TEST_KEY)["matchedFrom"]}
    assert rows[TWENTY]["fallback"] is False
    assert rows[THIRTY]["fallback"] is False


def test_fallback_log_names_the_actual_target():
    """`fallback=` used to be a hardcoded `75p`; it now names the real target."""
    h = Harness()
    h.response(json.dumps([TWENTY, TWENTY_FALLBACK]))
    assert f"fallback={TWENTY_FALLBACK}" in "\n".join(h.logs)
    assert "fallback=75p" not in "\n".join(h.logs)
