"""Record what the App Store says about a product ID.

The rewrite can only inject an ID; whether that ID is a real, purchasable
product is decided by Apple.  There is no public catalogue to query, so the
only oracle is the app's own StoreKit request -- which we can observe once the
sidecar is allowed to intercept the storefront hosts.

This module keeps that observation cheap and honest: one JSON line per store
response, with the product IDs found on the way out and on the way back.  It
records no cookies, no account data and no response body text beyond the
product identifiers themselves.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

DEFAULT_LOG = "~/.g1-acq/discovery.jsonl"

# Apple's iOS in-app-purchase storefront.  `bag.itunes.apple.com` and
# `amp-api-edge.apps.apple.com` were found by watching real StoreKit traffic —
# the obvious `buy.itunes.apple.com` alone was not enough.
STORE_HOST_PATTERN = (
    r"(?:p\d+-)?buy\.itunes\.apple\.com"
    r"|bag\.itunes\.apple\.com"
    r"|sandbox\.itunes\.apple\.com"
    r"|sf-api-token-service\.itunes\.apple\.com"
    r"|amp-api-edge\.apps\.apple\.com"
    r"|apps\.apple\.com"
)
STORE_HOST_RE = re.compile(rf"^(?:{STORE_HOST_PATTERN})$", re.IGNORECASE)

PRODUCT_ID_RE = re.compile(rb"g1\.[A-Za-z0-9._-]{2,60}")
MAX_BYTES = 4 * 1024 * 1024


def is_store_host(host: str) -> bool:
    return bool(STORE_HOST_RE.match(host or ""))


def _ids(blob: bytes | None) -> list[str]:
    if not blob:
        return []
    found: list[str] = []
    for match in PRODUCT_ID_RE.finditer(blob[:MAX_BYTES]):
        try:
            value = match.group(0).decode("ascii")
        except UnicodeDecodeError:  # pragma: no cover - regex is ASCII-only
            continue
        if value not in found:
            found.append(value)
    return found


def log_path(value: str | os.PathLike[str] | None = None) -> Path:
    raw = str(value or os.environ.get("G1_DISCOVERY_LOG") or DEFAULT_LOG)
    return Path(os.path.expanduser(raw))


class Discoveries:
    """Append-only JSONL of store responses, plus a summary for the CLI."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = log_path(path)
        self._lock = threading.Lock()

    # -- writing ---------------------------------------------------------
    def record(self, *, host: str, url: str, method: str, status: int,
               content_type: str, request_body: bytes | None,
               response_body: bytes | None) -> dict:
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "host": host,
            "path": _safe_path(url),
            "method": method,
            "status": status,
            "content_type": content_type[:60],
            "requested": _ids(request_body),
            "answered": _ids(response_body),
            "request_bytes": len(request_body or b""),
            "response_bytes": len(response_body or b""),
        }
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                return entry
        return entry

    # -- reading ---------------------------------------------------------
    def entries(self) -> list[dict]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return []
        out = []
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                out.append(item)
        return out

    def summary(self) -> list[dict]:
        """One row per product ID: was it asked for, and did Apple answer for it?"""
        asked: dict[str, int] = {}
        answered: dict[str, int] = {}
        for entry in self.entries():
            for pid in entry.get("requested", []):
                asked[pid] = asked.get(pid, 0) + 1
            for pid in entry.get("answered", []):
                answered[pid] = answered.get(pid, 0) + 1
        rows = []
        for pid in sorted(set(asked) | set(answered)):
            rows.append({
                "id": pid,
                "requested": asked.get(pid, 0),
                "answered": answered.get(pid, 0),
                "verdict": (
                    "answered" if answered.get(pid) else
                    "requested-only" if asked.get(pid) else "mentioned"
                ),
            })
        rows.sort(key=lambda row: (row["verdict"] != "answered", -row["requested"], row["id"]))
        return rows


def _safe_path(url: str) -> str:
    """Keep the endpoint, drop anything that could carry an account token."""
    from urllib.parse import urlsplit

    parts = urlsplit(url or "")
    return parts.path[:200] or "/"


__all__ = ["Discoveries", "STORE_HOST_PATTERN", "STORE_HOST_RE",
           "is_store_host", "log_path"]
