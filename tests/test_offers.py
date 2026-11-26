"""Reading a third-party scraped offer catalogue, safely."""

from __future__ import annotations

import json

from g1acq import offers

RAW = {
    "device_strings": ["g1.100gb", "g1.20tb.v2"],
    "hits": [
        {
            "ev": "offer", "product": "g1.2tb.ai.12months_eft", "basePlanId": "monthly",
            "title": "Google AI Pro", "name": "AI Pro",
            "token": "AYrTWi7MVERYSECRETTOKEN==", "tags": "[object Object]",
            "phases": [
                {"micros": "0", "formatted": "Free", "currency": "USD",
                 "period": "P1Y", "cycles": 1, "mode": 1},
                {"micros": "19990000", "formatted": "$19.99", "currency": "USD",
                 "period": "P1M", "cycles": 0, "mode": 1},
            ],
        },
        {
            "ev": "offer", "product": "g1.20tb.v2", "basePlanId": "p1m",
            "token": "ANOTHERSECRET==",
            "phases": [{"micros": "99990000", "formatted": "$99.99",
                        "currency": "USD", "period": "P1M", "cycles": 0, "mode": 1}],
        },
    ],
}


def test_token_and_tags_are_dropped():
    clean = offers.sanitize(RAW)
    blob = json.dumps(clean)
    assert "SECRET" not in blob
    assert "token" not in blob
    assert "tags" not in blob
    assert clean["sanitized"] is True


def test_offers_are_parsed(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(offers.sanitize(RAW)), encoding="utf-8")
    items, _ = offers.load(path)
    assert [o.product for o in items] == ["g1.2tb.ai.12months_eft", "g1.20tb.v2"]


def test_free_trial_is_detected_and_described(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(offers.sanitize(RAW)), encoding="utf-8")
    items, _ = offers.load(path)
    free = next(o for o in items if "eft" in o.product)
    assert free.is_free and free.has_intro
    assert "Free/1年" in free.describe()
    assert "之后 $19.99/1个月" in free.describe()
    assert free.regular_price() == "$19.99/1个月"


def test_plain_offer_is_not_marked_as_a_deal(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(offers.sanitize(RAW)), encoding="utf-8")
    items, _ = offers.load(path)
    plain = next(o for o in items if o.product == "g1.20tb.v2")
    assert not plain.has_intro and not plain.is_free
    assert plain.describe() == "$99.99/1个月"


def test_free_offers_sort_first(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(offers.sanitize(RAW)), encoding="utf-8")
    items, _ = offers.load(path)
    text = offers.render_text(sorted(items, key=lambda o: o.rank), source="test")
    assert text.index("g1.2tb.ai.12months_eft") < text.index("g1.20tb.v2")
    assert "不是本机采集结果" in text


def test_iso_durations_render_in_chinese():
    assert offers._period_text("P1Y") == "1年"
    assert offers._period_text("P1Y6M") == "1年6个月"
    assert offers._period_text("P52W1D") == "52周1天"
    assert offers._period_text("P4W3D") == "4周3天"
    assert offers._period_text("P1M") == "1个月"
    assert offers._period_text("") == ""


def test_missing_cache_is_reported_not_crashed(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        offers.load(tmp_path / "absent.json")
    assert "没有载入任何 offer 目录" in offers.render_text([])
