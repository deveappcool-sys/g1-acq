"""The setup console: what a stranger sees first."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

import pytest

yaml = pytest.importorskip("yaml")

from g1acq import ca  # noqa: E402
from g1acq.app import G1App  # noqa: E402
from g1acq.setup_console import SetupConsole  # noqa: E402
from g1acq.store import MemoryStore  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def ca_dir(tmp_path):
    """A throwaway 'mitmproxy' CA so the console can serve it."""
    import datetime as dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "g1-acq test ca")])
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    (tmp_path / ca.CA_FILENAME).write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )
    return tmp_path


@pytest.fixture()
def console(ca_dir):
    store = MemoryStore()
    instance = SetupConsole(store, port=_free_port(), sidecar_port=8080,
                            confdir=str(ca_dir), server_host="192.168.2.57")
    instance.start()
    yield instance, store
    instance.stop()


def _get(console, path: str) -> tuple[int, str, bytes]:
    url = f"http://127.0.0.1:{console.port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()


def test_page_shows_the_current_address(console):
    instance, _ = console
    status, content_type, body = _get(instance, "/")
    assert status == 200
    assert content_type.startswith("text/html")
    text = body.decode()
    assert "192.168.2.57:8080" in text
    assert "安装证书" in text and "导入 Clash 配置" in text


def test_clash_profile_endpoint_returns_importable_yaml(console):
    instance, _ = console
    status, content_type, body = _get(instance, "/clash.yaml?mode=g1")
    assert status == 200
    assert "yaml" in content_type
    data = yaml.safe_load(body)
    assert data["proxies"][0]["server"] == "192.168.2.57"
    assert "DOMAIN,one.google.com,G1" in data["rules"]


def test_subscription_mode_is_passed_through(console):
    instance, _ = console
    url = "/clash.yaml?mode=sub&sub=" + urllib.request.quote("https://example.com/s?t=1")
    status, _, body = _get(instance, url)
    assert status == 200
    assert "example.com/s?t=1" in body.decode()


def test_subscription_mode_without_url_is_a_400(console):
    instance, _ = console
    status, _, body = _get(instance, "/clash.yaml?mode=sub")
    assert status == 400
    assert "订阅" in body.decode()


def test_certificate_endpoints_use_the_types_ios_needs(console):
    instance, _ = console
    status, content_type, body = _get(instance, "/ca.cer")
    assert status == 200
    assert content_type == ca.CER_MIME
    assert body[:1] == b"\x30"  # DER SEQUENCE, not PEM text

    status, content_type, body = _get(instance, "/ca.mobileconfig")
    assert status == 200
    assert content_type == ca.MOBILECONFIG_MIME
    assert b"com.apple.security.root" in body


def test_status_json_reflects_real_state(console):
    instance, store = console
    app = G1App(store)
    app.on_response(
        "https://one.google.com/ai?x=1",
        json.dumps(["g1.ios.2tb.m", "g1.ios.20tb.m.v2"]),
    )
    status, content_type, body = _get(instance, "/status.json")
    assert status == 200
    payload = json.loads(body)
    assert payload["scanned_responses"] >= 1
    assert payload["candidates"] == 2
    assert payload["last_test_status"] == "rewritten"
    assert payload["hit_count"] == 2
    assert payload["ca_fingerprint"]
    assert payload["lan_ips"]


def test_qr_endpoint_returns_svg_or_404(console):
    instance, _ = console
    status, content_type, body = _get(instance, "/qr.svg?d=http%3A%2F%2Fexample.com")
    if status == 200:
        assert "svg" in content_type
        assert b"<svg" in body
    else:  # segno is optional
        assert status == 404


def test_unknown_path_is_404(console):
    instance, _ = console
    status, _, _ = _get(instance, "/etc/passwd")
    assert status == 404


def test_missing_certificate_is_reported_not_crashed(tmp_path):
    instance = SetupConsole(MemoryStore(), port=_free_port(), confdir=str(tmp_path))
    instance.start()
    try:
        status, _, body = _get(instance, "/ca.cer")
        assert status == 503
        assert b"mitmproxy" in body
    finally:
        instance.stop()


def test_console_can_be_disabled():
    instance = SetupConsole(MemoryStore(), port=0)
    instance.start()
    assert instance._httpd is None
    instance.stop()
