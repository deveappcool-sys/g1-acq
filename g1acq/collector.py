"""Passive product-ID collection.

Reads the original response *before* any rewrite, keeps at most
``SCAN_LIMIT`` distinct IDs, and stores a redacted activity log of the last
``RECENT_LIMIT`` responses.  No headers, query strings, bodies or full URLs are
persisted.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from . import config
from .store import Store, load_json
from .urls import ROUTES, safe_route

Emit = Callable[[str], None]

VALID_ID_RE = re.compile(r"^(?:g1\.|com\.google\.one\.)[A-Za-z0-9._-]{1,160}$")

# Dots are frequently escaped in the serialised payload; decode a discovery
# copy only, never the response itself.
ESCAPED_DOT_RE = re.compile(r"\\u002e|\\x2e|&#0*46;|&#x0*2e;|&period;", re.IGNORECASE)

TOKEN_RE = re.compile(
    r"(^|[^A-Za-z0-9._@%-])((?:g1\.|com\.google\.one\.)[A-Za-z0-9._-]+)"
    r"(?=$|[^A-Za-z0-9._-])"
)

_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def format_iso(moment: datetime) -> str:
    """Mirror ``Date.prototype.toISOString`` (millisecond precision, UTC)."""
    moment = moment.astimezone(timezone.utc)
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}T"
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}."
        f"{moment.microsecond // 1000:03d}Z"
    )


def now_iso() -> str:
    return format_iso(datetime.now(timezone.utc))


def parse_iso(value: Any) -> datetime | None:
    """Strict ISO-8601 parse: the value must round-trip exactly."""
    if not isinstance(value, str) or not _AT_RE.fullmatch(value):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    return parsed if format_iso(parsed) == value else None


def prior_count(value: Any) -> int:
    """``Number(value)`` floored, non-positive and non-finite mapped to 0."""
    if isinstance(value, bool):
        number = 1.0 if value else 0.0
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
    if not math.isfinite(number) or number <= 0:
        return 0
    return math.floor(number)


def _counter(value: Any, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return max(0, min(maximum, math.floor(value)))


def response_status(
    body_type: str, candidate_count: int, added_count: int, omitted_count: int
) -> str:
    if body_type == "non-text":
        return "non-text"
    if added_count > 0:
        return "new-skus"
    if omitted_count > 0:
        return "limit-reached"
    return "known-skus" if candidate_count > 0 else "no-skus"


def prior_response(row: Any) -> dict | None:
    """Validate one stored activity event; drop anything malformed."""
    if not isinstance(row, dict):
        return None
    if parse_iso(row.get("at")) is None:
        return None
    if row.get("path") not in ROUTES:
        return None
    if row.get("bodyType") not in ("text", "non-text"):
        return None

    candidate_count = _counter(row.get("candidateCount"), config.MAX_EVENT_COUNT)
    if candidate_count is None:
        return None
    added_count = _counter(
        row.get("addedCount"), min(config.SCAN_LIMIT, candidate_count)
    )
    if added_count is None:
        return None
    omitted_count = _counter(row.get("omittedCount"), candidate_count - added_count)
    if omitted_count is None:
        return None
    if row.get("bodyType") == "non-text" and (
        candidate_count or added_count or omitted_count
    ):
        return None
    status = response_status(
        row["bodyType"], candidate_count, added_count, omitted_count
    )
    if row.get("status") != status:
        return None
    return {
        "at": row["at"],
        "path": row["path"],
        "bodyType": row["bodyType"],
        "status": status,
        "candidateCount": candidate_count,
        "addedCount": added_count,
        "omittedCount": omitted_count,
    }


@dataclass
class CollectionResult:
    event: dict
    stored: bool
    occurrences: int
    counts: dict[str, int] = field(default_factory=dict)


def collect(
    store: Store,
    url: str,
    body: Any,
    *,
    emit: Emit | None = None,
) -> CollectionResult:
    emit = emit or (lambda _message: None)
    now = now_iso()
    saved = load_json(store, config.SCAN_KEY)

    by_id: dict[str, dict] = {}
    ids: list[str] = []
    old_rows = saved.get("skus")
    old_rows = old_rows if isinstance(old_rows, list) else []
    for row in old_rows[: config.SCAN_LIMIT]:
        if not isinstance(row, dict):
            continue
        sku = row.get("id")
        if not isinstance(sku, str) or not VALID_ID_RE.fullmatch(sku) or sku in by_id:
            continue
        last_seen = row.get("lastSeen")
        by_id[sku] = {
            "id": sku,
            "count": prior_count(row.get("count")),
            "lastSeen": last_seen[:32] if isinstance(last_seen, str) else "",
        }
        ids.append(sku)

    is_text = isinstance(body, str)
    found: dict[str, int] = {}
    occurrences = 0
    added_count = 0
    omitted_count = 0
    truncated = saved.get("truncated") is True

    if is_text:
        text = ESCAPED_DOT_RE.sub(".", body)
        for match in TOKEN_RE.finditer(text):
            sku = match.group(2)
            if not VALID_ID_RE.fullmatch(sku):
                continue
            found[sku] = found.get(sku, 0) + 1
            occurrences += 1
            if sku not in by_id:
                if len(ids) >= config.SCAN_LIMIT:
                    truncated = True
                    if found[sku] == 1:
                        omitted_count += 1
                    continue
                by_id[sku] = {"id": sku, "count": 0, "lastSeen": now}
                ids.append(sku)
                added_count += 1
            by_id[sku]["count"] += 1
            by_id[sku]["lastSeen"] = now

    candidate_count = len(found)
    body_type = "text" if is_text else "non-text"
    status = response_status(body_type, candidate_count, added_count, omitted_count)

    recent: list[dict] = []
    old_responses = saved.get("recentResponses")
    old_responses = old_responses if isinstance(old_responses, list) else []
    for row in old_responses[-config.RECENT_LIMIT :]:
        event = prior_response(row)
        if event is not None:
            recent.append(event)
    event = {
        "at": now,
        "path": safe_route(url),
        "bodyType": body_type,
        "status": status,
        "candidateCount": candidate_count,
        "addedCount": added_count,
        "omittedCount": omitted_count,
    }
    # Preserve arrival order even if the device clock moves backward.
    recent.append(event)

    state = {
        "schemaVersion": config.SCHEMA_VERSION,
        "version": config.COLLECTOR_VERSION,
        "updatedAt": now,
        "scannedResponses": prior_count(saved.get("scannedResponses")) + (1 if is_text else 0),
        "matchedResponses": prior_count(saved.get("matchedResponses"))
        + (1 if occurrences > 0 else 0),
        "nonTextResponses": prior_count(saved.get("nonTextResponses"))
        + (0 if is_text else 1),
        "recentResponses": recent[-config.RECENT_LIMIT :],
        "limit": config.SCAN_LIMIT,
        "truncated": truncated,
        "skus": [by_id[sku] for sku in sorted(ids)],
    }

    stored = False
    try:
        stored = store.write(
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            config.SCAN_KEY,
        )
        stored = bool(stored)
    except Exception:
        stored = False

    emit(
        f"[g1-acq] {config.COLLECTOR_VERSION} status={status}"
        f" addedCount={added_count} candidates={candidate_count}"
        f" omittedCount={omitted_count} occurrences={occurrences}"
        f" saved={'yes' if stored else 'no'}"
    )
    for sku in sorted(found)[: config.SCAN_LIMIT]:
        emit(f"[g1-acq] {sku} x{found[sku]}")

    return CollectionResult(
        event=event,
        stored=stored,
        occurrences=occurrences,
        counts=dict(found),
    )


__all__ = [
    "CollectionResult",
    "collect",
    "format_iso",
    "now_iso",
    "parse_iso",
    "prior_count",
    "prior_response",
    "response_status",
]
