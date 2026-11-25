"""Three-tier SKU rewrite for Google One ``/ai?`` responses.

The mapping intentionally mirrors the shipped v7.5 behaviour:

* every complete ``g1.ios.2tb.*`` token becomes the fixed 12-month candidate,
  which has no fallback;
* ``g1.ios.20tb.m.v2`` and ``g1.ios.30tb.ai.pro.m`` map to their 90p offer and
  fall back to the matching 75p offer only when the 90p string is absent from
  the original response while the 75p string is present;
* the decision is made on the original body, before any substitution.

This is a string check against the response text, not a store catalog query.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from . import config, i18n
from .collector import now_iso
from .store import Store

Emit = Callable[[str], None]

# Offer IDs actually present in the original response.
OBSERVED_RE = re.compile(r"g1\.[a-z0-9._]{2,60}acq")

# Complete tokens only: the leading/trailing guards stop the rewrite from
# touching a longer identifier such as ``g1.ios.2tbx.fixture``.
SKU_TOKEN_RE = re.compile(
    r"(^|[^A-Za-z0-9._@%-])(g1\.[A-Za-z0-9._-]+)(?=$|[^A-Za-z0-9._-])"
)


@dataclass
class RewriteResult:
    body: str | None
    record: dict


def target_for(sku: str, observed: list[str], settings: config.Settings) -> tuple[str, bool] | None:
    """Return ``(target, used_fallback)`` for a source token, or ``None``."""
    if sku.startswith(config.SOURCE_PREFIX) and len(sku) > len(config.SOURCE_PREFIX):
        return settings.target, False
    mapped = config.SKU_MAP.get(sku)
    if mapped is None:
        return None
    fallback = config.FALLBACK.get(mapped)
    if mapped not in observed and fallback and fallback in observed:
        return fallback, True
    return mapped, False


def rewrite(
    body: Any,
    *,
    settings: config.Settings = config.SETTINGS,
) -> RewriteResult:
    """Rewrite original text; return the new body (``None`` = unchanged)."""
    mappings: dict[str, dict] = {}
    hits = 0
    annual_hits = 0
    out = body

    if isinstance(body, str):
        # Preserve the v6 fallback rule by inspecting the original response.
        observed = OBSERVED_RE.findall(body)

        def replace(match: re.Match[str]) -> str:
            nonlocal hits, annual_hits
            before, sku = match.group(1), match.group(2)
            decided = target_for(sku, observed, settings)
            if decided is None:
                return match.group(0)
            target, fallback = decided
            if sku not in mappings:
                mappings[sku] = {
                    "id": sku,
                    "to": target,
                    "count": 0,
                    "fallback": fallback,
                }
            mappings[sku]["count"] += 1
            hits += 1
            if sku.startswith(config.SOURCE_PREFIX):
                annual_hits += 1
            return before + target

        out = SKU_TOKEN_RE.sub(replace, body)

    record = {
        "schemaVersion": config.SCHEMA_VERSION,
        "version": config.COLLECTOR_VERSION,
        "updatedAt": now_iso(),
        "sourcePrefix": config.SOURCE_PREFIX,
        "target": settings.target,
        "targetOrigin": settings.target_origin,
        "hitCount": hits,
        # Legacy field name: counts 2TB/Pro rewrites, not the billing interval.
        "annualHitCount": annual_hits,
        "matchedFrom": [mappings[sku] for sku in sorted(mappings)],
        "status": "non-text"
        if not isinstance(body, str)
        else ("rewritten" if hits else "no-match"),
    }
    return RewriteResult(body=out if hits else None, record=record)


def save_record(store: Store, record: dict, *, emit: Emit | None = None) -> bool:
    emit = emit or (lambda _message: None)
    try:
        stored = bool(
            store.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                config.TEST_KEY,
            )
        )
    except Exception:
        emit(i18n.t("log.record_unavailable"))
        return False
    if not stored:
        emit(i18n.t("log.record_write_failed"))
    return stored


def log_record(record: dict, *, emit: Emit | None = None) -> None:
    emit = emit or (lambda _message: None)
    emit(
        f"[g1-acq] {record['version']} hits={record['hitCount']}"
        f" annualHits={record['annualHitCount']}"
    )
    for source in record["matchedFrom"]:
        suffix = " fallback=75p" if source["fallback"] else ""
        emit(
            f"[g1-acq] {source['id']} -> {source['to']} x{source['count']}{suffix}"
        )
