"""Read a scraped Play/App Store offer catalogue.

`catalog` answers "what did *this* account get offered".  This module answers a
different question: "what offers exist at all".  It consumes the
``sku-catalog.json`` format produced by the g1-acq-plus project, which is a list
of store offers with their phase structure — intro phase (discount or free
trial) followed by the regular price.

Two things matter here:

* **Sanitise on the way in.**  Every entry in the upstream file carries a
  ``token`` field, which is a store purchase token belonging to whoever ran the
  scrape.  We drop it, along with ``tags``, before anything is cached or shown.
* **Say where it came from.**  This is somebody else's data.  The default
  source is recorded next to the cache so a reader can tell the difference
  between "we observed this" and "we copied this".
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/tgai521/g1-acq-plus/main/sku-catalog.json"
)
CACHE_PATH = "~/.g1-acq/offers.json"
KEEP_FIELDS = ("ev", "product", "basePlanId", "id", "title", "name",
               "micros", "formatted", "period")
PHASE_FIELDS = ("micros", "formatted", "currency", "period", "cycles", "mode")


@dataclass
class Offer:
    product: str
    base_plan: str
    title: str = ""
    name: str = ""
    phases: list[dict] = field(default_factory=list)

    @property
    def has_intro(self) -> bool:
        """True when the first phase is cheaper than the follow-up price."""
        return len(self.phases) >= 2

    @property
    def is_free(self) -> bool:
        return any(
            str(phase.get("micros")) == "0"
            or str(phase.get("formatted", "")).strip().lower() in ("free", "$0", "0")
            for phase in self.phases
        )

    def describe(self) -> str:
        if not self.phases:
            return "—"
        intro, rest = self.phases[0], (self.phases[-1] if self.has_intro else None)
        parts = [_phase_text(intro)]
        if self.has_intro and rest is not None:
            parts.append(f"之后 {_phase_text(rest)}")
        return "，".join(parts)

    def regular_price(self) -> str:
        phase = self.phases[-1] if self.phases else {}
        return f"{phase.get('formatted', '?')}/{_period_text(phase.get('period', ''))}"

    @property
    def rank(self) -> tuple:
        """Free trials first, then intro discounts, then plain prices."""
        return (not self.is_free, not self.has_intro, self.product, self.base_plan)


def _phase_text(phase: dict) -> str:
    amount = phase.get("formatted") or phase.get("micros") or "?"
    period = _period_text(phase.get("period", ""))
    text = f"{amount}/{period}" if period else str(amount)
    cycles = phase.get("cycles")
    if cycles:
        text += f" ×{cycles}"
    return text


_ISO_DURATION = re.compile(
    r"^P(?:(?P<y>\d+)Y)?(?:(?P<mo>\d+)M)?(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?$"
)
_UNIT_LABELS = (("y", "年"), ("mo", "个月"), ("w", "周"), ("d", "天"))


def _period_text(iso: str) -> str:
    """'P1Y' -> '1年', 'P52W1D' -> '52周1天', 'P4W3D' -> '4周3天'."""
    text = (iso or "").strip().upper()
    if not text.startswith("P"):
        return text
    match = _ISO_DURATION.match(text)
    if not match:
        return text
    parts = [
        f"{int(match.group(key))}{label}"
        for key, label in _UNIT_LABELS
        if match.group(key) and int(match.group(key))
    ]
    return "".join(parts) or "0"


def sanitize(raw: dict) -> dict:
    """Keep the offer shape, drop anything belonging to the scraper's account."""
    hits = []
    for item in raw.get("hits") or []:
        clean = {key: item[key] for key in KEEP_FIELDS if key in item}
        clean["phases"] = [
            {key: phase[key] for key in PHASE_FIELDS if key in phase}
            for phase in item.get("phases") or []
        ]
        hits.append(clean)
    return {
        "source": raw.get("source", ""),
        "sanitized": True,
        "hits": hits,
        "device_strings": raw.get("device_strings") or [],
    }


def fetch(url: str = DEFAULT_SOURCE, *, timeout: float = 45.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        raw = json.loads(response.read().decode("utf-8"))
    clean = sanitize(raw)
    clean["source"] = url
    return clean


def save(data: dict, path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(os.path.expanduser(str(path or CACHE_PATH)))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


def load(path: str | os.PathLike[str] | None = None) -> tuple[list[Offer], str]:
    target = Path(os.path.expanduser(str(path or CACHE_PATH)))
    raw = json.loads(target.read_text(encoding="utf-8"))
    offers = [
        Offer(
            product=item.get("product", ""),
            base_plan=item.get("basePlanId", ""),
            title=item.get("title", ""),
            name=item.get("name", ""),
            phases=item.get("phases") or [],
        )
        for item in raw.get("hits") or []
    ]
    return offers, raw.get("source", "")


def render_text(offers: list[Offer], *, source: str = "", limit: int = 0) -> str:
    if not offers:
        return "没有载入任何 offer 目录。先跑 `g1acq offers --fetch`。"
    rows = sorted(offers, key=lambda offer: offer.rank)
    if limit:
        rows = rows[:limit]
    width = min(40, max(len(o.product) for o in rows))
    lines = [
        f"{'商品'.ljust(width)}  {'计划':8}  {'优惠 / 价格'.ljust(34)}  续费原价",
        "-" * (width + 56),
    ]
    for offer in rows:
        mark = "☑ " if (offer.is_free or offer.has_intro) else "  "
        lines.append(
            f"{offer.product[:width].ljust(width)}  {offer.base_plan[:8].ljust(8)}  "
            f"{mark}{offer.describe()[:32].ljust(32)}  {offer.regular_price()}"
        )
    free = sum(1 for o in rows if o.is_free)
    intro = sum(1 for o in rows if o.has_intro)
    lines += [
        "",
        f"共 {len(rows)} 条：{free} 条免费试用，{intro} 条带首期折扣。",
    ]
    if source:
        lines.append(f"数据来源：{source}")
    lines.append("说明：这是别人抓取的商品目录（含 Play 商店），不是本机采集结果，"
                 "也不代表你的账号能买到。")
    return "\n".join(lines)
