"""Turn the collected product IDs into something a human can read.

What the collector stores is a flat list of strings.  What a person wants to
know is: *which tiers have a discount right now, and how deep is it.*  This
module parses the naming convention the storefront actually uses and renders
it as a table.

It answers "what did this account, in this region, get offered so far" — not
"what exists globally".  The two are very different and confusing them is how
people end up trusting a guess.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import config
from .store import FileStore

PERIOD_WORDS = {
    "1month": "1 个月",
    "2month": "2 个月",
    "2months": "2 个月",
    "3month": "3 个月",
    "3months": "3 个月",
    "12month": "12 个月",
    "12months": "12 个月",
    "1year": "1 年",
    "1yr": "1 年",
    "annual": "年付",
}

_DISCOUNT_RE = re.compile(r"_ip_(\d+)p")
_PRICE_RE = re.compile(r"_ip\.(\d+(?:\.\d+)?)")
_VERSION_RE = re.compile(r"\.v(\d+)$")
_PERIOD_RE = re.compile(
    r"(?<![a-z])(1month|2months?|3months?|12months?|1year|1yr)(?![a-z])"
)
_PERIOD_LETTER = {"a": "年付", "m": "月付"}


@dataclass(frozen=True)
class Sku:
    raw: str
    family: str          # "ios" | "web" | "google"
    tier: str            # "2tb", "ai.2tb", "helium", "30gb" ...
    billing: str         # 月付 / 年付 / 一次性
    promo: str           # "12 个月" 或 ""
    discount_pct: int | None
    price: float | None
    acq: bool

    @property
    def has_discount(self) -> bool:
        return self.discount_pct is not None or self.price is not None

    @property
    def label(self) -> str:
        """Human summary of the offer, e.g. '9 折' or '25 折'."""
        if self.discount_pct is not None:
            return f"{self.discount_pct}% off"
        if self.price is not None:
            return f"{self.price:g} 定价"
        return "原价"


_INLINE_PROMO = re.compile(r"^(\d+)(mo|month|months|yr|year|years)$")


def _promo_label(parts: list[str]) -> str:
    """'1yr' -> '1 年', '3mo' -> '3 个月', '12month' -> '12 个月'."""
    text = "".join(parts).lower()
    if text in PERIOD_WORDS:
        return PERIOD_WORDS[text]
    match = _INLINE_PROMO.match(text)
    if not match:
        return text
    number, unit = match.group(1), match.group(2)
    if unit.startswith("y"):
        return f"{number} 年"
    return f"{number} 个月"


def parse(raw: str) -> Sku:
    """Split an ID into tier / billing / promo / discount.

    The storefront writes the promo period in two places depending on the
    family, so both `g1.ios.2tb.a.12month_ip_10p` (period as its own token) and
    `g1.ios.ai.2tb.a.ip_1yr_25p` (period inside the `ip_` token) have to work.
    """
    body = raw.strip()
    family = "google" if body.startswith("com.google.one.") else "web"
    if body.startswith("com.google.one."):
        body = body[len("com.google.one."):]
    elif body.startswith("g1."):
        body = body[len("g1."):]

    acq = body.endswith(".acq")
    if acq:
        body = body[: -len(".acq")]

    match = _VERSION_RE.search(body)
    if match:
        body = body[: -len(match.group(0))]

    if body.startswith("ios."):
        family = "ios"
        body = body[len("ios."):]

    # Absolute pricing (`ip.2.49`) spans two dot-separated parts, so take it out
    # before tokenising.
    price = None
    match = _PRICE_RE.search(body)
    if match:
        price = float(match.group(1))
        body = (body[: match.start()] + body[match.end():]).strip(".")

    discount = None
    promo_parts: list[str] = []
    tier_parts: list[str] = []
    billing = ""
    tokens = [token for token in body.split(".") if token]
    for token in tokens:
        # A single dot-separated token can carry the whole offer:
        # "12months_ip_10p", "ip_3mo_75p", "ip_1yr".
        if "_ip_" in token:
            head, _, tail = token.partition("_ip_")
            if head:
                promo_parts.append(head)
            if re.fullmatch(r"\d+p", tail):
                discount = int(tail[:-1])
            elif tail:
                promo_parts.append(tail)
            continue
        if token == "ip" or token.startswith("ip_"):
            for piece in token.split("_")[1:]:
                if not piece:
                    continue
                if re.fullmatch(r"\d+p", piece):
                    discount = int(piece[:-1])
                else:
                    promo_parts.append(piece)
            continue
        if token == "annual":
            billing = "年付"
            continue
        if token in ("a", "m"):
            billing = _PERIOD_LETTER[token]
            continue
        if re.fullmatch(r"\d+p", token):
            discount = int(token[:-1])
            continue
        if token in PERIOD_WORDS or _INLINE_PROMO.match(token):
            promo_parts.append(token)
            continue
        tier_parts.append(token)

    promo = _promo_label(promo_parts) if promo_parts else ""
    tier = ".".join(tier_parts) or "—"
    return Sku(
        raw=raw,
        family=family,
        tier=tier,
        billing=billing or "—",
        promo=promo,
        discount_pct=discount,
        price=price,
        acq=acq,
    )


def load(state_path: str | os.PathLike[str] | None = None) -> list[Sku]:
    path = Path(os.path.expanduser(str(state_path or "~/.g1-acq/state.json")))
    raw = FileStore(path).read(config.SCAN_KEY)
    if not raw:
        return []
    try:
        rows = json.loads(raw).get("skus") or []
    except ValueError:
        return []
    return [parse(row["id"]) for row in rows if isinstance(row.get("id"), str)]


def _order(sku: Sku) -> tuple:
    # discounted offers first, then the deepest discount, then the id
    return (not sku.has_discount, -(sku.discount_pct or 0), sku.raw)


def render_text(skus: list[Sku]) -> str:
    if not skus:
        return "还没有采集到任何编号。让手机连上旁路、打开 Google One 方案页再看。"
    rows = sorted(skus, key=_order)
    width_tier = max(len("档位"), max(len(s.tier) for s in rows))
    width_billing = max(len("周期"), max(len(s.billing) for s in rows))
    lines = [
        f"{'档位'.ljust(width_tier)}  {'周期'.ljust(width_billing)}  {'优惠':10}  {'促销期':8}  编号",
        "-" * (width_tier + width_billing + 40),
    ]
    for sku in rows:
        lines.append(
            f"{sku.tier.ljust(width_tier)}  {sku.billing.ljust(width_billing)}  "
            f"{('☑ ' + sku.label if sku.has_discount else '  ' + sku.label):10}  "
            f"{sku.promo[:8].ljust(8)}  {sku.raw}"
        )
    discounted = [s for s in rows if s.has_discount]
    lines.append("")
    lines.append(f"共 {len(rows)} 个编号，其中 {len(discounted)} 个带折扣。")
    lines.append("说明：这是本机采集到的、这个账号这个地区此刻被下发的清单，不是全球目录。")
    return "\n".join(lines)


def render_markdown(skus: list[Sku], *, collected_at: str = "", source: str = "") -> str:
    rows = sorted(skus, key=_order)
    lines = [
        "# 实测 SKU 清单",
        "",
        "> 由 `python -m g1acq catalog --md` 从本地采集记录生成。",
        "> **这是某个账号、某个地区、某个时刻被下发的清单，不是全球商品目录。**",
        "",
    ]
    if collected_at:
        lines.append(f"- 采集时间：`{collected_at}`")
    if source:
        lines.append(f"- 数据来源：{source}")
    lines.append(f"- 编号总数：**{len(rows)}**，其中带折扣 **{sum(1 for s in rows if s.has_discount)}**")
    lines += ["", "## 带折扣的档位", "",
              "| 档位 | 周期 | 促销期 | 优惠 | 编号 |", "|---|---|---|---|---|"]
    for sku in rows:
        if not sku.has_discount:
            continue
        lines.append(
            f"| {sku.tier} | {sku.billing} | {sku.promo or '—'} | {sku.label} | "
            f"`{sku.raw}` |"
        )
    lines += ["", "## 全部编号（含原价）", "", "| 编号 | 档位 | 周期 | 优惠 |", "|---|---|---|---|"]
    for sku in rows:
        lines.append(f"| `{sku.raw}` | {sku.tier} | {sku.billing} | {sku.label} |")
    lines += [
        "",
        "## 命名规律（据实测归纳）",
        "",
        "```",
        "g1[.ios].<档位>.<促销期>_ip_<折扣>p[.acq]",
        "g1[.ios].<档位>[.<a|m>]          无折扣原价档",
        "```",
        "",
        "- `ios` 前缀 = iOS 内购商品；没有它的是网页/Play 族",
        "- `a` = 年付，`m` = 月付",
        "- `_ip_NNp` = 折扣百分比（`10p` 即 9 折，`90p` 即 1 折）",
        "- `_ip.2.49` 这种写法是**绝对定价**，不是百分比",
        "- `.acq` = acquisition 类促销后缀",
        "",
    ]
    return "\n".join(lines)
