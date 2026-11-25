"""Parsing the storefront's naming convention into something readable."""

from __future__ import annotations

import json

import pytest

from g1acq import catalog, config

# Every ID below came out of a real response on a Turkish storefront account.
REAL_IDS = [
    "com.google.one.generic",
    "g1.100gb",
    "g1.100gb.2months_ip.0.49",
    "g1.100gb.annual",
    "g1.100gb.annual.12months_ip_10p",
    "g1.10tb",
    "g1.200gb",
    "g1.200gb.annual.12months_ip_10p",
    "g1.20tb.v2",
    "g1.2tb",
    "g1.2tb.2months_ip.2.49",
    "g1.2tb.ai",
    "g1.2tb.ai.2months_ip_50p",
    "g1.2tb.ai.annual",
    "g1.2tb.annual.12months_ip_10p",
    "g1.30gb.2month_ip_75p",
    "g1.30gb.annual.1year_ip_10p",
    "g1.ai.pro",
    "g1.helium.3months_ip_75p.acq",
    "g1.helium.annual.12months_ip_25p.acq",
    "g1.ios.100gb.a",
    "g1.ios.100gb.a.12month_ip_10p",
    "g1.ios.100gb.m.2month_ip_75p",
    "g1.ios.20tb.m.v2",
    "g1.ios.2tb.a",
    "g1.ios.2tb.a.12month_ip_10p",
    "g1.ios.2tb.ai.a",
    "g1.ios.2tb.m.2month_ip_75p",
    "g1.ios.30tb.ai.pro.m",
    "g1.ios.ai.2tb.a.ip_1yr_25p.acq",
    "g1.ios.ai.2tb.m.ip_3mo_75p.acq",
    "g1.ios.helium.a.ip_1yr_25p.acq",
    "g1.ios.helium.m.3month_ip_75p.acq",
]


@pytest.mark.parametrize("raw", REAL_IDS)
def test_every_real_id_parses_cleanly(raw):
    """No token may be swallowed into the tier name by accident."""
    sku = catalog.parse(raw)
    assert sku.raw == raw
    assert sku.tier and sku.tier != "—", raw
    assert "_ip" not in sku.tier, f"{raw}: offer leaked into tier {sku.tier!r}"
    assert not any(piece.endswith("p") and piece[:-1].isdigit() for piece in sku.tier.split("."))


def test_percentage_discount_with_a_separate_period_token():
    sku = catalog.parse("g1.ios.2tb.a.12month_ip_10p")
    assert (sku.family, sku.tier, sku.billing, sku.promo, sku.discount_pct) == (
        "ios", "2tb", "年付", "12 个月", 10)


def test_percentage_discount_with_the_period_inside_the_ip_token():
    """`ip_1yr_25p` carries both the period and the discount."""
    sku = catalog.parse("g1.ios.ai.2tb.a.ip_1yr_25p.acq")
    assert (sku.family, sku.tier, sku.billing, sku.promo, sku.discount_pct) == (
        "ios", "ai.2tb", "年付", "1 年", 25)
    assert sku.acq is True
    sku = catalog.parse("g1.ios.ai.2tb.m.ip_3mo_75p.acq")
    assert (sku.billing, sku.promo, sku.discount_pct) == ("月付", "3 个月", 75)


def test_absolute_pricing_is_not_a_percentage():
    sku = catalog.parse("g1.2tb.2months_ip.2.49")
    assert sku.price == 2.49
    assert sku.discount_pct is None
    assert sku.promo == "2 个月"


def test_version_suffix_does_not_land_in_the_tier():
    sku = catalog.parse("g1.ios.20tb.m.v2")
    assert (sku.tier, sku.billing, sku.discount_pct) == ("20tb", "月付", None)


def test_twenty_tb_has_no_discount_variant():
    """The finding that mattered: 20TB is offered at full price only."""
    results = [catalog.parse(raw) for raw in REAL_IDS if "20tb" in raw]
    assert results
    assert not any(sku.has_discount for sku in results)


def test_discounted_tiers_are_found():
    rows = [catalog.parse(raw) for raw in REAL_IDS]
    discounted = {(s.tier, s.billing, s.discount_pct) for s in rows if s.has_discount}
    assert ("2tb", "年付", 10) in discounted
    assert ("2tb", "月付", 75) in discounted
    assert ("ai.2tb", "年付", 25) in discounted


def test_load_reads_the_store(tmp_path):
    from g1acq.store import MemoryStore

    store = MemoryStore({config.SCAN_KEY: json.dumps(
        {"schemaVersion": 1, "skus": [{"id": "g1.ios.2tb.a.12month_ip_10p", "count": 3}]})})
    state = tmp_path / "state.json"
    state.write_text(json.dumps(store.as_dict()), encoding="utf-8")

    skus = catalog.load(state)
    assert [s.raw for s in skus] == ["g1.ios.2tb.a.12month_ip_10p"]


def test_missing_state_is_empty_not_an_error(tmp_path):
    assert catalog.load(tmp_path / "absent.json") == []
    assert "还没有采集到" in catalog.render_text([])


def test_text_output_puts_discounts_first_and_warns_about_scope():
    text = catalog.render_text([catalog.parse(raw) for raw in REAL_IDS])
    assert text.index("10% off") < text.index("原价")
    assert "不是全球目录" in text


def test_markdown_contains_both_tables_and_the_caveat():
    md = catalog.render_markdown([catalog.parse(raw) for raw in REAL_IDS],
                                 source="`~/.g1-acq/state.json`")
    assert "## 带折扣的档位" in md
    assert "## 全部编号（含原价）" in md
    assert "不是全球商品目录" in md
    assert "g1.ios.20tb.m.v2" in md
    assert "_ip_NNp" in md
