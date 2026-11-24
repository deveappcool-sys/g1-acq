"""URL classification.

The original module scoped its work with three Shadowrocket regexes.  They are
reproduced verbatim here so the rewrite scope cannot silently widen: a host
such as ``one.google.com.evil`` must never match.
"""

from __future__ import annotations

import re

# Any response under https://one.google.com/ is scanned for candidate SKUs.
ONE_GOOGLE_RE = re.compile(r"^https://one\.google\.com/")

# The local report, including a trailing slash and any query string.
REPORT_RE = re.compile(r"^https://one\.google\.com/g1-sku-report/?(?:\?|$)")

# Only /ai? responses are rewritten.
AI_RE = re.compile(r"^https://one\.google\.com/ai\?")

_BATCHEXECUTE_RE = re.compile(r"^/_/[^?#]+/data/batchexecute$")

ROUTE_HOME = "/"
ROUTE_AI = "/ai"
ROUTE_PLANS = "/plans"
ROUTE_BATCHEXECUTE = "/_/…/data/batchexecute"  # "…" is literal display text
ROUTE_OTHER = "[其他 one.google.com 路径]"

ROUTES = (
    ROUTE_HOME,
    ROUTE_AI,
    ROUTE_PLANS,
    ROUTE_BATCHEXECUTE,
    ROUTE_OTHER,
)

_JSON_RE = re.compile(r"(?:\?|&)format=json(?:&|$)")
_CLEAR_RE = re.compile(r"(?:\?|&)clear=1(?:&|$)")


def is_one_google(url: str) -> bool:
    return bool(ONE_GOOGLE_RE.match(url))


def is_report(url: str) -> bool:
    return bool(REPORT_RE.match(url))


def is_rewrite_scope(url: str) -> bool:
    return bool(AI_RE.match(url))


def safe_route(url: str) -> str:
    """Collapse a request URL to one of the fixed, redacted route classes."""
    path = url.replace("https://one.google.com", "", 1).split("?", 1)[0].split("#", 1)[0]
    path = path.rstrip("/") or "/"
    if path in (ROUTE_HOME, ROUTE_AI, ROUTE_PLANS):
        return path
    if _BATCHEXECUTE_RE.match(path):
        return ROUTE_BATCHEXECUTE
    return ROUTE_OTHER


def wants_json(url: str) -> bool:
    return bool(_JSON_RE.search(url))


def wants_clear(url: str) -> bool:
    return bool(_CLEAR_RE.search(url))
