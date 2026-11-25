"""Helpers for the end-to-end suite.

The chain under test is exactly the one a phone uses:

    client --CONNECT--> mihomo --rule--> mitmdump (G1 ACQ) --TLS--> Google

Outside the test, the last hop is the real ``one.google.com``.  Here it is a
local TLS server that answers with a fixed offer list, and a small CONNECT
forwarder rewrites the destination so nothing leaves the machine.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOCK_SKUS = ["g1.ios.2tb.monthly.v1", "g1.ios.20tb.m.v2", "g1.ios.30tb.ai.pro.m"]
REWRITTEN_SKUS = [
    "g1.2tb.ai.12months_ip_90p",
    "g1.20tb.1month_eft.acq",
    "g1.ai.ultra.1month_eft.acq",
]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"nothing listening on 127.0.0.1:{port}")


class _GoogleHandler(BaseHTTPRequestHandler):
    body = json.dumps({"offers": MOCK_SKUS}).encode()

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args) -> None:  # silence
        return


class FakeGoogle:
    """TLS server that plays the part of one.google.com."""

    def __init__(self, cert: Path, key: Path) -> None:
        self.port = free_port()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), _GoogleHandler)
        self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self) -> "FakeGoogle":
        self._thread.start()
        wait_for_port(self.port)
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class ConnectForwarder:
    """Minimal HTTP proxy that redirects CONNECT to a local port."""

    def __init__(self, target_port: int) -> None:
        self.port = free_port()
        self._target = ("127.0.0.1", target_port)
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(16)

    def start(self) -> "ConnectForwarder":
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self

    def stop(self) -> None:
        self._sock.close()

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        data = b""
        try:
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    conn.close()
                    return
                data += chunk
            head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1")
            if not head.upper().startswith("CONNECT"):
                conn.close()
                return
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            upstream = socket.create_connection(self._target, timeout=10)
        except OSError:
            conn.close()
            return
        threading.Thread(target=_pump, args=(conn, upstream), daemon=True).start()
        _pump(upstream, conn)


def _pump(source: socket.socket, sink: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            sink.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            sink.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Process:
    """Small wrapper that keeps stdout in a file for assertions."""

    def __init__(self, argv: list[str], log_path: Path, cwd: Path | None = None) -> None:
        self.argv = argv
        self.log_path = log_path
        self.cwd = cwd
        self._handle = None

    def start(self, port: int) -> "Process":
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("wb")
        self._handle = subprocess.Popen(
            self.argv,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            cwd=str(self.cwd) if self.cwd else None,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        wait_for_port(port)
        return self

    @property
    def log(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def stop(self) -> None:
        if self._handle and self._handle.poll() is None:
            self._handle.terminate()
            try:
                self._handle.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._handle.kill()
        try:
            self._log.close()
        except Exception:
            pass


def make_certificate(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "2",
            "-subj", "/CN=one.google.com",
            "-addext", "subjectAltName=DNS:one.google.com",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def https_via_proxy(proxy_port: int, host: str, path: str, timeout: float = 15.0):
    context = ssl._create_unverified_context()  # noqa: S323 - fixture certificate
    conn = http.client.HTTPSConnection(
        "127.0.0.1", proxy_port, context=context, timeout=timeout
    )
    try:
        conn.set_tunnel(host, 443)
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def mitmdump_available() -> bool:
    return shutil.which("mitmdump") is not None or (
        (Path(sys.prefix) / "bin" / "mitmdump").exists()
    )


def mitmdump_binary() -> str:
    local = Path(sys.prefix) / "bin" / "mitmdump"
    return str(local) if local.exists() else "mitmdump"


def mihomo_binary() -> str | None:
    return shutil.which("mihomo")


def openssl_available() -> bool:
    return shutil.which("openssl") is not None
