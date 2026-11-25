"""Single source of truth for the Google One SKU rewrite contract.

The values in this module are the contract shared by the Clash profile, the
MITM sidecar, the local report page and the offline test-suite.  Nothing here
talks to the network or to mitmproxy, so it can be imported by any test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

# --------------------------------------------------------------------------
# Release identity
# --------------------------------------------------------------------------
PROJECT_VERSION = "8.2.0"
REPORT_VERSION = "v8.2.0"
# Written into every collection record so the report can tell an old record
# from a record produced by the current collector.
COLLECTOR_VERSION = "g1-acq-clash-v8.2"

# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------
HOST = "one.google.com"
REPORT_PATH = "/g1-sku-report"
REPORT_ROOT = f"https://{HOST}{REPORT_PATH}"

# --------------------------------------------------------------------------
# Three-tier mapping
# --------------------------------------------------------------------------
SOURCE_PREFIX = "g1.ios.2tb."
# User-selected 12-month offer ID from the screenshot; store metadata is still
# unverified.  Everything with the SOURCE_PREFIX is rewritten to this value.
DEFAULT_TARGET = "g1.2tb.ai.12months_ip_90p"
TARGET_ORIGIN = "user-specified"
# Target recorded by v1 / v7.1 collectors; still readable by the report.
LEGACY_TARGET = "g1.2tb.ai.annual"

SKU_MAP = MappingProxyType(
    {
        "g1.ios.20tb.m.v2": "g1.20tb.1month_eft.acq",
        "g1.ios.30tb.ai.pro.m": "g1.ai.ultra.1month_eft.acq",
    }
)

# Only used when the default target is absent from the original response and
# the matching fallback is present in it.  Mirrors upstream v7.6.0: the 20TB and
# 30TB tiers now try the one-month free trial first and fall back to the
# three-month 90p offer.
FALLBACK = MappingProxyType(
    {
        "g1.20tb.1month_eft.acq": "g1.20tb.3months_ip_90p.acq",
        "g1.ai.ultra.1month_eft.acq": "g1.ai.ultra.3months_ip_90p.acq",
    }
)

# --------------------------------------------------------------------------
# Local persistence (same keys and schema as the Shadowrocket generation, so
# exported records keep their meaning)
# --------------------------------------------------------------------------
SCAN_KEY = "g1.sku.scan.v1"
TEST_KEY = "g1.pro.annual.test.v1"
SCHEMA_VERSION = 1

SCAN_LIMIT = 300
RECENT_LIMIT = 10
MAX_EVENT_COUNT = 9007199254740991  # Number.MAX_SAFE_INTEGER

TARGET_RE = re.compile(r"^g1\.[A-Za-z0-9._-]{1,160}$")


@dataclass(frozen=True)
class Settings:
    """Runtime knobs that may be overridden from the mitmproxy command line."""

    target: str = DEFAULT_TARGET
    max_body_bytes: int = 0  # 0 means "no limit", matching max-size=0

    def __post_init__(self) -> None:
        if not TARGET_RE.fullmatch(self.target):
            raise ValueError(f"invalid g1 target SKU: {self.target!r}")
        if self.max_body_bytes < 0:
            raise ValueError("max_body_bytes must be >= 0")

    @property
    def target_origin(self) -> str:
        return TARGET_ORIGIN


SETTINGS = Settings()
