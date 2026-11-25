"""Shared fixtures for the offline suite.

``Harness`` replaces the Shadowrocket host: it supplies a storage backend,
records reads/writes the way the original ``$persistentStore`` tests did, and
returns payloads shaped like ``$done({...})`` so the ported assertions stay
readable next to the originals.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from g1acq import config  # noqa: E402
from g1acq.app import G1App  # noqa: E402
from g1acq.store import MemoryStore  # noqa: E402

TARGET = "g1.2tb.ai.12months_ip_90p"
LEGACY_TARGET = "g1.2tb.ai.annual"
SCAN_KEY = config.SCAN_KEY
TEST_KEY = config.TEST_KEY
REPORT = "https://one.google.com/g1-sku-report"

# Fixture source IDs test the matching contract; they are not store evidence.
SOURCE = "g1.ios.2tb.fixture_monthly"
OTHER_SOURCE = "g1.ios.2tb.fixture_annual"
TWENTY = "g1.ios.20tb.m.v2"
THIRTY = "g1.ios.30tb.ai.pro.m"
TWENTY_TARGET = "g1.20tb.1month_eft.acq"
THIRTY_TARGET = "g1.ai.ultra.1month_eft.acq"
TWENTY_FALLBACK = "g1.20tb.3months_ip_90p.acq"
THIRTY_FALLBACK = "g1.ai.ultra.3months_ip_90p.acq"

DEFAULT_AI_URL = "https://one.google.com/ai?fixture=1"


class Recorder:
    """Wraps a store and records the keys it was asked for."""

    def __init__(self, inner, *, throws: bool = False, write_fails: bool = False):
        self._inner = inner
        self._throws = throws
        self._write_fails = write_fails
        self.reads: list[str] = []
        self.writes: list[str] = []

    def read(self, key: str):
        if self._throws:
            raise RuntimeError("fixture storage failure")
        self.reads.append(key)
        return self._inner.read(key)

    def write(self, value: str, key: str) -> bool:
        if self._throws:
            raise RuntimeError("fixture storage failure")
        self.writes.append(key)
        if self._write_fails:
            return False
        return self._inner.write(value, key)


class Harness:
    def __init__(
        self,
        storage=None,
        *,
        settings: config.Settings = config.SETTINGS,
        storage_available: bool = True,
        storage_throws: bool = False,
        storage_write_fails: bool = False,
    ) -> None:
        self.map = storage if isinstance(storage, MemoryStore) else MemoryStore(storage)
        self.logs: list[str] = []
        backing = self.map if storage_available else MemoryStore()
        self.store = Recorder(
            backing,
            throws=storage_throws or not storage_available,
            write_fails=storage_write_fails,
        )
        self.app = G1App(self.store, settings=settings, emit=self.logs.append)

    # -- traffic ---------------------------------------------------------
    def response(self, body, url: str = DEFAULT_AI_URL) -> dict:
        replacement = self.app.on_response(url, body)
        return {} if replacement is None else {"body": replacement}

    def report(self, url: str = REPORT) -> dict:
        result = self.app.report_for(url)
        if result is None:
            return {}
        return {
            "response": {
                "status": result.status,
                "headers": result.headers,
                "body": result.body,
            }
        }

    # -- storage ---------------------------------------------------------
    def get(self, key: str):
        return json.loads(self.map.read(key))

    def raw(self, key: str):
        return self.map.read(key)

    @property
    def reads(self) -> list[str]:
        return self.store.reads

    @property
    def writes(self) -> list[str]:
        return self.store.writes


@pytest.fixture()
def harness():
    return Harness()


def run_body(body, url: str = DEFAULT_AI_URL, **kwargs) -> Harness:
    """One-shot helper mirroring the original ``run(name, options)``."""
    instance = Harness(**kwargs)
    instance.response(body, url)
    return instance
