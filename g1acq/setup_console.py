"""The setup console served next to the sidecar.

Every support problem in this project came from the same place: the user could
not see what to do next, and the pieces (certificate, profile, current address,
whether the phone is even connected) lived in four different places.  This
console puts them on one page, generated from the machine's real state.

    http://<lan-ip>:8090/          中文
    http://<lan-ip>:8090/?lang=en  English

It intentionally serves only four things — the page, the CA, a generated
profile and a status snapshot — so it can never be used to read arbitrary files
from the host.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from . import ca, config, i18n, network, profile
from .report import build_report
from .store import Store

DEFAULT_PORT = 8090
MAX_SUBSCRIPTION_LENGTH = 2048

_PLACEHOLDER = re.compile(r"\{\{T:([a-z0-9_.]+)\}\}")

# Strings the browser needs; everything else is rendered on the server.
_JS_KEYS = (
    "ui.loading", "ui.kv.server", "ui.kv.address", "ui.kv.clients", "ui.kv.clients.never",
    "ui.kv.clients.times", "ui.kv.scanned", "ui.kv.candidates", "ui.kv.last",
    "ui.kv.last.none", "ui.kv.last.at", "ui.hint.none", "ui.hint.connected",
    "ui.hint.rewritten",
)

PAGE = """<!doctype html><html lang={{HTML_LANG}}><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{{T:ui.title}}</title>
<style>
body{font:16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;padding:20px;
color:#1c2737;background:#f5f7fa;max-width:720px;margin:0 auto}
h1{font-size:22px;margin:14px 0 6px}
h2{font-size:17px;margin:0 0 12px}
section{background:#fff;border:1px solid #dde3ec;border-radius:14px;padding:18px;margin:16px 0}
.badge{display:inline-block;background:#e0f4e8;color:#176238;padding:3px 10px;border-radius:8px;font-size:14px}
.muted{color:#5b6b80;font-size:14px}
code{overflow-wrap:anywhere;background:#eef2f7;padding:2px 6px;border-radius:6px;font-size:13px}
a.btn,button{display:inline-block;font:inherit;padding:11px 16px;border:0;border-radius:9px;
cursor:pointer;text-decoration:none;background:#1259be;color:#fff;margin:6px 6px 0 0}
a.alt{background:#e4eaf3;color:#1c2737}
input[type=url]{width:100%;box-sizing:border-box;padding:11px;border:1px solid #cfd8e5;
border-radius:9px;font:inherit;margin-top:8px}
.qr{background:#fff;padding:8px;border-radius:10px;display:inline-block;margin-top:10px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:14px}
.kv div:nth-child(odd){color:#5b6b80}
.ok{color:#176238;font-weight:600}
.warn{color:#9a5b00;font-weight:600}
pre{white-space:pre-wrap;word-break:break-all;font-size:12px;background:#eef2f7;
padding:10px;border-radius:8px}
.lang{float:right;font-size:13px}
</style>
<h1>{{T:ui.title}} <span class=muted style="font-size:13px">v{{VERSION}}</span>
<span class=lang><a href="{{SELF_ZH}}">中文</a> · <a href="{{SELF_EN}}">English</a></span></h1>
<p class=muted>{{T:ui.subtitle}}</p>

<section>
<h2>{{T:ui.step1}}</h2>
<p class=muted>{{T:ui.step1.body}}</p>
<a class="btn" href="/ca.mobileconfig">{{T:ui.download_profile}}</a>
<a class="btn alt" href="/ca.cer">{{T:ui.download_cer}}</a>
<p class=muted>{{T:ui.fingerprint}}<code id=fp>{{T:ui.loading}}</code></p>
</section>

<section>
<h2>{{T:ui.step2}}</h2>
<p class=muted>{{T:ui.step2.body}}<code>{{SERVER}}:{{PORT}}</code></p>
<a class="btn" href="/clash.yaml?mode=g1">{{T:ui.g1_only}}</a>
<p class=muted>{{T:ui.g1_only.note}}</p>

<form method=get action="/clash.yaml" target=_blank>
<input type=hidden name=mode value=sub>
<input type=url name=sub placeholder="{{T:ui.sub_placeholder}}" maxlength={{MAX_SUB}}>
<button type=submit>{{T:ui.sub_button}}</button>
</form>
<p class=muted>{{T:ui.step2.hint}}</p>
<p><code id=clash-url>{{CLASH_URL}}</code></p>
<div class=qr><img id=qr alt=QR src="/qr.svg?d={{CLASH_URL_ENCODED}}" width=200 height=200></div>
</section>

<section>
<h2>{{T:ui.step3}}</h2>
<div class=kv id=status><div>{{T:ui.loading}}</div></div>
<p class=muted id=hint></p>
</section>

<p class=muted>{{T:ui.footer}}</p>

<script>
const L = {{LANG_JSON}};
const fmt = v => (v === null || v === undefined || v === '') ? '—' : v;
async function refresh(){
  try{
    const r = await fetch('/status.json', {cache:'no-store'});
    const s = await r.json();
    document.getElementById('fp').textContent = s.ca_fingerprint || '—';
    const clients = s.clients_seen
      ? L['ui.kv.clients.times'].replace('{count}', s.clients_seen)
      : L['ui.kv.clients.never'];
    const last = s.last_test_status
      ? (s.last_test_status + ' · ' + s.hit_count + '×')
      : L['ui.kv.last.none'];
    const rows = [
      [L['ui.kv.server'], s.server + ':' + s.port],
      [L['ui.kv.address'], (s.lan_ips||[]).join(' / ') || '—'],
      [L['ui.kv.clients'], clients],
      [L['ui.kv.scanned'], fmt(s.scanned_responses)],
      [L['ui.kv.candidates'], fmt(s.candidates)],
      [L['ui.kv.last'], last],
      [L['ui.kv.last.at'], fmt(s.last_test_at)],
    ];
    document.getElementById('status').innerHTML =
      rows.map(([k,v]) => '<div>'+k+'</div><div>'+v+'</div>').join('');
    const hint = document.getElementById('hint');
    if (!s.clients_seen) hint.textContent = L['ui.hint.none'];
    else if (!s.last_test_status) hint.textContent = L['ui.hint.connected'];
    else hint.textContent = L['ui.hint.rewritten'];
  }catch(e){ /* keep the page usable if polling fails */ }
}
refresh(); setInterval(refresh, 3000);
</script>
</html>
"""


def _qr_svg(data: str) -> bytes | None:
    try:
        import segno
    except ImportError:  # optional: the console works without QR codes
        return None
    svg = segno.make(data, error="m").svg_inline(
        scale=6, border=2, dark="#1c2737", light="#ffffff"
    )
    return svg.encode("utf-8")


class SetupConsole:
    """Threaded HTTP console; ``start()`` is a no-op when disabled."""

    def __init__(
        self,
        store: Store,
        *,
        port: int = DEFAULT_PORT,
        sidecar_port: int = 8080,
        confdir: str | None = None,
        server_host: str | None = None,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self.port = int(port)
        self.sidecar_port = int(sidecar_port)
        self.confdir = confdir
        self._emit = emit or (lambda _m: None)
        self._host = server_host or network.primary_address() or "127.0.0.1"
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started_at = time.time()

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if not self.port:
            return
        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._emit(i18n.t("log.console_ready", url=self.url))

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}/"

    # -- payloads --------------------------------------------------------
    def _status(self) -> dict[str, Any]:
        report = build_report(self.store, config.REPORT_ROOT + "?format=json")
        data = json.loads(report.body)
        scan, test = data["scan"], data["test"]
        try:
            fingerprint = ca.fingerprint(self.confdir)
        except Exception:
            fingerprint = ""
        return {
            "version": config.PROJECT_VERSION,
            "server": self._host,
            "port": self.sidecar_port,
            "console_port": self.port,
            "lan_ips": network.lan_addresses(),
            "uptime_seconds": int(time.time() - self._started_at),
            "ca_fingerprint": fingerprint,
            "storage_available": data["storageAvailable"],
            "scanned_responses": scan["scannedResponses"],
            "candidates": len(scan["skus"]),
            "clients_seen": scan["scannedResponses"],
            "last_test_status": test["status"],
            "last_test_at": test["updatedAt"],
            "hit_count": test["hitCount"],
            "annual_hit_count": test["annualHitCount"],
            "sources": test["matchedFrom"],
        }

    def _page(self, lang: str) -> bytes:
        base = f"http://{self._host}:{self.port}/"
        clash_url = f"{base}clash.yaml?mode=g1"
        html = _PLACEHOLDER.sub(lambda m: i18n.t(m.group(1), lang=lang), PAGE)
        html = (
            html.replace("{{HTML_LANG}}", "zh-CN" if lang == "zh" else "en")
            .replace("{{VERSION}}", config.PROJECT_VERSION)
            .replace("{{SERVER}}", self._host)
            .replace("{{PORT}}", str(self.sidecar_port))
            .replace("{{MAX_SUB}}", str(MAX_SUBSCRIPTION_LENGTH))
            .replace("{{CLASH_URL_ENCODED}}", urllib.parse.quote(clash_url, safe=""))
            .replace("{{CLASH_URL}}", clash_url)
            .replace("{{SELF_ZH}}", "./?lang=zh")
            .replace("{{SELF_EN}}", "./?lang=en")
            .replace("{{LANG_JSON}}", json.dumps(
                {key: i18n.t(key, lang=lang) for key in _JS_KEYS}, ensure_ascii=False))
        )
        return html.encode("utf-8")

    def _clash(self, query: dict[str, list[str]]) -> tuple[bytes, str]:
        mode = (query.get("mode") or ["g1"])[0]
        subscription = (query.get("sub") or [""])[0][:MAX_SUBSCRIPTION_LENGTH]
        auth = (query.get("auth") or [""])[0]
        options = profile.ProfileOptions(
            server=self._host,
            port=self.sidecar_port,
            mode=mode if mode in (profile.MODE_G1_ONLY, profile.MODE_SUBSCRIPTION)
            else profile.MODE_G1_ONLY,
            subscription=subscription,
            auth=auth,
        )
        return profile.render(options).encode("utf-8"), "text/yaml; charset=utf-8"

    # -- request handling -------------------------------------------------
    def _make_handler(self):
        console = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):  # noqa: D401 - silence access logs
                return

            def _send(self, body: bytes, content_type: str, status: int = 200,
                      extra: dict[str, str] | None = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:  # client went away
                    pass

            def do_GET(self) -> None:  # noqa: N802 - stdlib naming
                parsed = urllib.parse.urlsplit(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                lang = i18n.normalize((query.get("lang") or [None])[0]
                                      or i18n.current_language())
                route = parsed.path
                try:
                    if route == "/":
                        self._send(console._page(lang), "text/html; charset=utf-8")
                    elif route == "/clash.yaml":
                        body, content_type = console._clash(query)
                        self._send(body, content_type, extra={
                            "Content-Disposition": 'attachment; filename="g1-acq.yaml"'})
                    elif route == "/ca.cer":
                        self._send(ca.der_bytes(console.confdir), ca.CER_MIME)
                    elif route == "/ca.mobileconfig":
                        self._send(ca.mobileconfig(console.confdir), ca.MOBILECONFIG_MIME,
                                   extra={"Content-Disposition":
                                          'attachment; filename="g1-acq-ca.mobileconfig"'})
                    elif route == "/status.json":
                        self._send(json.dumps(console._status(), ensure_ascii=False).encode(),
                                   "application/json; charset=utf-8")
                    elif route == "/qr.svg":
                        data = (query.get("d") or [""])[0]
                        svg = _qr_svg(data) if data else None
                        if svg is None:
                            self._send(b"qr unavailable", "text/plain", 404)
                        else:
                            self._send(svg, "image/svg+xml")
                    else:
                        self._send(b"not found", "text/plain", 404)
                except ca.MissingCertificate:
                    self._send(i18n.t("ui.ca_missing", lang=lang).encode(),
                               "text/plain; charset=utf-8", 503)
                except profile.ProfileError as error:
                    self._send(str(error).encode(), "text/plain; charset=utf-8", 400)
                except Exception as error:  # pragma: no cover - defensive
                    self._send(f"internal error: {error!r}".encode(), "text/plain", 500)

        return Handler
