"""Orchestration shared by the mitmproxy addon and the offline tests.

``G1App`` has no mitmproxy dependency: it takes a URL plus an already decoded
body, and returns what should go back on the wire.  That keeps the tested
surface identical to the traffic path.
"""

from __future__ import annotations

from typing import Any, Callable

from . import config, i18n
from .collector import collect
from .report import ReportResponse, build_report
from .rewriter import log_record, rewrite, save_record
from .store import Store
from .urls import is_one_google, is_report, is_rewrite_scope

Emit = Callable[[str], None]


def _silent(_message: str) -> None:
    return None


class G1App:
    def __init__(
        self,
        store: Store,
        settings: config.Settings = config.SETTINGS,
        emit: Emit | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.emit = emit or _silent

    # -- request path ----------------------------------------------------
    def report_for(self, url: str) -> ReportResponse | None:
        """Synthesise the local report; ``None`` means "let it through"."""
        if not is_report(url):
            return None
        try:
            return build_report(self.store, url, settings=self.settings, emit=self.emit)
        except Exception as error:  # a broken report must not break browsing
            self.emit(i18n.t("log.report_failed", error=repr(error)))
            return None

    # -- response path ---------------------------------------------------
    def on_response(self, url: str, body: Any) -> str | None:
        """Return the replacement body, or ``None`` to leave it untouched."""
        if not isinstance(url, str) or not is_one_google(url) or is_report(url):
            return None

        try:
            collect(self.store, url, body, emit=self.emit)
        except Exception:
            self.emit(i18n.t("log.collect_unavailable"))

        if not is_rewrite_scope(url):
            return None

        try:
            result = rewrite(body, settings=self.settings)
        except Exception as error:
            self.emit(i18n.t("log.rewrite_unavailable", error=repr(error)))
            return None

        save_record(self.store, result.record, emit=self.emit)
        log_record(result.record, emit=self.emit)
        return result.body


__all__ = ["G1App"]
