"""The setup console served next to the sidecar.

Every support problem in this project came from the same place: the user could
not see what to do next, and the pieces (certificate, profile, current address,
whether the phone is even connected) lived in four different places.  This
console puts them on one page, generated from the machine's real state.

    http://<lan-ip>:8090/

It intentionally serves only four things — the page, the CA, a generated
profile and a status snapshot — so it can never be used to read arbitrary
files from the host.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from . import ca, config, network, profile
from .report import build_report
from .store import Store

DEFAULT_PORT = 8090
MAX_SUBSCRIPTION_LENGTH = 2048

PAGE = """<!doctype html><html lang=zh-CN><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>G1 ACQ 安装控制台</title>
<style>
body{font:16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;margin:0;padding:20px;
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
</style>
<h1>G1 ACQ 安装控制台 <span class=muted style="font-size:13px">v{{VERSION}}</span></h1>
<p class=muted>这里的东西都由这台机器实时生成，不需要手改配置。</p>

<section>
<h2>第一步 · 安装证书</h2>
<p class=muted>手机需要信任这张证书，旁路才能读到 <code>one.google.com</code> 的响应。
下载后到 <b>设置 → 通用 → VPN 与设备管理</b> 安装，再到
<b>设置 → 通用 → 关于本机 → 证书信任设置</b> 打开完全信任。</p>
<a class="btn" href="/ca.mobileconfig">下载证书（.mobileconfig）</a>
<a class="btn alt" href="/ca.cer">下载 .cer</a>
<p class=muted>证书 SHA-256：<code id=fp>读取中…</code></p>
</section>

<section>
<h2>第二步 · 导入 Clash 配置</h2>
<p class=muted>旁路地址已经写进配置：<code>{{SERVER}}:{{PORT}}</code></p>
<a class="btn" href="/clash.yaml?mode=g1">只做 G1（其它直连）</a>
<p class=muted>适合先在手机上把链路走通，不需要任何机场节点。</p>

<form method=get action="/clash.yaml" target=_blank>
<input type=hidden name=mode value=sub>
<input type=url name=sub placeholder="可选：粘贴你的机场订阅链接，生成带节点的完整配置" maxlength={{MAX_SUB}}>
<button type=submit>生成带订阅的配置</button>
</form>
<p class=muted>订阅链接只在这台机器上使用，不会上传。生成的配置可以直接用 Clash
「从 URL 导入」——把下面的地址复制过去，或者用手机扫二维码。</p>
<p><code id=clash-url>{{CLASH_URL}}</code></p>
<div class=qr><img id=qr alt="配置二维码" src="/qr.svg?d={{CLASH_URL_ENCODED}}" width=200 height=200></div>
</section>

<section>
<h2>第三步 · 看状态</h2>
<div class=kv id=status><div>读取中…</div></div>
<p class=muted id=hint></p>
</section>

<p class=muted>这个页面只在你自己的局域网内可访问。用完可以关掉：
<code>g1-acq serve --console 0</code> 或直接停掉服务。</p>

<script>
const fmt = v => (v === null || v === undefined || v === '') ? '—' : v;
async function refresh(){
  try{
    const r = await fetch('/status.json', {cache:'no-store'});
    const s = await r.json();
    document.getElementById('fp').textContent = s.ca_fingerprint || '未生成';
    const rows = [
      ['旁路', s.server + ':' + s.port],
      ['本机地址', (s.lan_ips||[]).join(' / ') || '未检测到'],
      ['手机连过', s.clients_seen ? (s.clients_seen + ' 次连接') : '还没有'],
      ['已扫描响应', fmt(s.scanned_responses)],
      ['采集到的编号', fmt(s.candidates)],
      ['最近改写', s.last_test_status ? (s.last_test_status + ' · ' + s.hit_count + ' 处') : '还没有'],
      ['最近改写时间', fmt(s.last_test_at)],
    ];
    const box = document.getElementById('status');
    box.innerHTML = rows.map(([k,v]) => '<div>'+k+'</div><div>'+v+'</div>').join('');
    const hint = document.getElementById('hint');
    if (!s.clients_seen) hint.textContent = '还没有手机连过来。确认手机和这台机器在同一个 Wi-Fi，并且 Clash 已导入上面的配置并连接。';
    else if (!s.last_test_status) hint.textContent = '手机已经连上，但还没抓到 one.google.com 的改写请求。打开 Google One 点一个方案试试。';
    else hint.textContent = '改写已经生效，去看 App Store 弹出的购买面板里的商品和价格。';
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
        self._emit(f"[g1-acq] 安装控制台: {self.url}")

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

    def _page(self) -> bytes:
        clash_url = f"http://{self._host}:{self.port}/clash.yaml?mode=g1"
        html = (
            PAGE.replace("{{SERVER}}", self._host)
            .replace("{{PORT}}", str(self.sidecar_port))
            .replace("{{VERSION}}", config.PROJECT_VERSION)
            .replace("{{MAX_SUB}}", str(MAX_SUBSCRIPTION_LENGTH))
            .replace("{{CLASH_URL_ENCODED}}", urllib.parse.quote(clash_url, safe=""))
            .replace("{{CLASH_URL}}", clash_url)
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
                route = parsed.path
                try:
                    if route == "/":
                        self._send(console._page(), "text/html; charset=utf-8")
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
                except ca.MissingCertificate as error:
                    self._send(str(error).encode(), "text/plain; charset=utf-8", 503)
                except profile.ProfileError as error:
                    self._send(str(error).encode(), "text/plain; charset=utf-8", 400)
                except Exception as error:  # pragma: no cover - defensive
                    self._send(f"internal error: {error!r}".encode(), "text/plain", 500)

        return Handler
