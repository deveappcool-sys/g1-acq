r"""mitmproxy addon: the network edge of G1 ACQ.

Run it behind mihomo (Clash).  Prefer the launcher, which sets every flag:

    python -m g1acq serve --port 8080 --auth user:password

Running mitmdump by hand only works if you reproduce the same options, in
particular ``allow_hosts`` -- without it mitmproxy intercepts *every* TLS
connection that reaches it:

    mitmdump -s g1_addon.py -p 8080 \
        --set 'allow_hosts=^one\.google\.com(:\d+)?$' \
        --set proxyauth=user:password \
        --set g1_state=~/.g1-acq/state.json

mihomo routes ``one.google.com`` to this proxy; everything else keeps using the
user's normal nodes.
"""

from __future__ import annotations

import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mitmproxy import ctx, http  # noqa: E402

from g1acq import config, i18n  # noqa: E402
from g1acq.app import G1App  # noqa: E402
from g1acq.setup_console import SetupConsole  # noqa: E402
from g1acq.store import FileStore  # noqa: E402

DEFAULT_STATE = "~/.g1-acq/state.json"

_CHARSET_RE = re.compile(r"charset\s*=\s*\"?([A-Za-z0-9._:-]+)", re.IGNORECASE)
_BINARY_TYPES = (
    "image/",
    "audio/",
    "video/",
    "font/",
    "application/zip",
    "application/gzip",
    "application/x-protobuf",
    "application/protobuf",
    "application/grpc",
    "application/octet-stream",
    "application/pdf",
    "application/wasm",
)


def _charset(content_type: str) -> str:
    match = _CHARSET_RE.search(content_type or "")
    return match.group(1) if match else "utf-8"


def _is_binary(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return any(lowered.startswith(prefix) for prefix in _BINARY_TYPES)


def _info(message: str) -> None:
    """Log through mitmproxy when bound, plain logging otherwise (tests)."""
    log = getattr(ctx, "log", None)
    if log is None:
        logging.getLogger("g1-acq").info(message)
    else:
        log.info(message)


def _warn(message: str) -> None:
    """Recoverable problem.

    mitmproxy aborts startup on any ``error``-level log, so anything that
    happens while starting (a busy console port, a bad option) must use this.
    """
    log = getattr(ctx, "log", None)
    if log is None:
        logging.getLogger("g1-acq").warning(message)
    else:
        log.warn(message)


def _error(message: str) -> None:
    log = getattr(ctx, "log", None)
    if log is None:
        logging.getLogger("g1-acq").error(message)
    else:
        log.error(message)


class G1Addon:
    def __init__(self) -> None:
        self.app: G1App | None = None
        self.settings = config.SETTINGS
        self.console: SetupConsole | None = None
        self._logger = logging.getLogger("g1-acq")

    # -- mitmproxy lifecycle --------------------------------------------
    def load(self, loader) -> None:
        loader.add_option(
            name="g1_state",
            typespec=str,
            default=DEFAULT_STATE,
            help="JSON file holding the SKU inventory and the last rewrite record.",
        )
        loader.add_option(
            name="g1_target",
            typespec=str,
            default="",
            help=f"Override the 2TB target SKU (default: {config.DEFAULT_TARGET}).",
        )
        loader.add_option(
            name="g1_max_body",
            typespec=int,
            default=0,
            help="Skip response bodies larger than this many bytes (0 = no limit).",
        )
        loader.add_option(
            name="g1_console",
            typespec=int,
            default=8090,
            help="Port of the setup console (0 disables it).",
        )

    def configure(self, updated) -> None:
        if not {"g1_state", "g1_target", "g1_max_body"} & set(updated):
            return
        self._rebuild(force=True)

    def running(self) -> None:
        self._rebuild()
        _info(i18n.t("log.ready", version=config.PROJECT_VERSION,
                     target=self.settings.target, state=self._state_path()))
        self._start_console()

    def _start_console(self) -> None:
        port = int(ctx.options.g1_console or 0)
        if not port or self.app is None:
            return
        if self.console is not None:
            self.console.stop()
        console = SetupConsole(
            self.app.store,
            port=port,
            sidecar_port=int(ctx.options.listen_port or 8080),
            confdir=ctx.options.confdir,
            emit=_info,
        )
        try:
            console.start()
        except OSError as error:
            _warn(i18n.t("log.console_failed", port=port, error=error))
            return
        self.console = console

    def done(self) -> None:
        if self.console is not None:
            self.console.stop()
            self.console = None
        self.app = None

    # -- helpers ---------------------------------------------------------
    def _state_path(self) -> str:
        raw = (ctx.options.g1_state or "").strip() or DEFAULT_STATE
        return os.path.abspath(os.path.expanduser(raw))

    def _rebuild(self, force: bool = False) -> None:
        target = (ctx.options.g1_target or "").strip() or config.DEFAULT_TARGET
        try:
            self.settings = config.Settings(
                target=target, max_body_bytes=int(ctx.options.g1_max_body or 0)
            )
        except ValueError as error:
            _warn(i18n.t("log.invalid_option", error=error))
            self.settings = config.SETTINGS
        if self.app is not None and not force:
            self.app.settings = self.settings
            return
        store = FileStore(self._state_path())
        self.app = G1App(store, settings=self.settings, emit=_info)

    # -- hooks -----------------------------------------------------------
    def request(self, flow: http.HTTPFlow) -> None:
        """Answer ``/g1-sku-report`` locally instead of forwarding it."""
        if flow.response is not None or self.app is None:
            return
        try:
            report = self.app.report_for(flow.request.pretty_url)
        except Exception as error:  # pragma: no cover - defensive
            _error(f"[g1-acq] report hook failed: {error!r}")
            return
        if report is None:
            return
        flow.response = http.Response.make(
            report.status,
            report.body.encode("utf-8"),
            report.headers,
        )

    def response(self, flow: http.HTTPFlow) -> None:
        """Scan for candidate SKUs and rewrite ``/ai?`` bodies."""
        if flow.response is None or self.app is None:
            return
        try:
            body = self._decoded_body(flow.response)
            replacement = self.app.on_response(flow.request.pretty_url, body)
        except Exception as error:  # never break the user's browsing
            _error(f"[g1-acq] response hook failed: {error!r}")
            return
        if replacement is None:
            return
        try:
            flow.response.set_text(replacement)
        except Exception as error:  # pragma: no cover - defensive
            _error(f"[g1-acq] could not apply rewrite: {error!r}")

    def _decoded_body(self, response: http.Response) -> str | None:
        content_type = response.headers.get("content-type", "")
        if _is_binary(content_type):
            return None
        if response.raw_content is None:
            # No body at all (HEAD, 304): nothing to scan.
            return None
        limit = self.settings.max_body_bytes
        if limit and len(response.raw_content) > limit:
            return None
        try:
            content = response.get_content(strict=True)
        except ValueError:
            return None
        if content is None:
            return None
        try:
            # An empty body stays "" and is counted as an empty text response,
            # matching the original contract.
            return content.decode(_charset(content_type), errors="strict")
        except (UnicodeDecodeError, LookupError):
            return None


addons = [G1Addon()]
