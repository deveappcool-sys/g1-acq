"""Clash profile generation — the piece that removes the manual YAML editing."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

yaml = pytest.importorskip("yaml")

from g1acq import profile  # noqa: E402

SERVER = "192.168.2.57"


def _render(**kwargs) -> str:
    return profile.render(profile.ProfileOptions(server=SERVER, **kwargs))


def test_g1_only_profile_has_the_rules_that_matter():
    text = _render()
    data = yaml.safe_load(text)

    assert data["proxies"][0]["server"] == SERVER
    assert data["proxies"][0]["type"] == "http"
    assert data["proxies"][0]["port"] == 8080

    rules = data["rules"]
    assert rules[0].startswith("AND,((NETWORK,udp),(DST-PORT,443)")
    assert rules[0].endswith("REJECT-DROP")
    assert "DOMAIN,one.google.com,G1" in rules
    # one.google.com must be decided before the catch-all.
    assert rules.index("DOMAIN,one.google.com,G1") < rules.index("MATCH,DIRECT")
    assert data["proxy-groups"][0]["name"] == "G1"


def test_g1_only_profile_needs_no_subscription():
    data = yaml.safe_load(_render())
    assert "proxy-providers" not in data
    assert data["rules"][-1] == "MATCH,DIRECT"


def test_subscription_profile_keeps_other_traffic_on_the_users_nodes():
    text = _render(mode=profile.MODE_SUBSCRIPTION, subscription="https://example.com/sub?token=x")
    data = yaml.safe_load(text)

    assert data["proxy-providers"]["my-sub"]["url"] == "https://example.com/sub?token=x"
    assert data["proxy-providers"]["my-sub"]["proxy"] == "DIRECT"
    # PROXY must default to the user's own nodes, never to the sidecar.
    proxy_group = next(g for g in data["proxy-groups"] if g["name"] == "PROXY")
    assert proxy_group["proxies"][0] == "AUTO"
    assert data["rules"][-1] == "MATCH,PROXY"


def test_subscription_mode_requires_a_url():
    with pytest.raises(profile.ProfileError):
        profile.render(profile.ProfileOptions(
            server=SERVER, mode=profile.MODE_SUBSCRIPTION, subscription="not-a-url"))


def test_credentials_are_embedded_when_the_sidecar_requires_auth():
    data = yaml.safe_load(_render(auth="g1:s3cret"))
    proxy = data["proxies"][0]
    assert proxy["username"] == "g1"
    assert proxy["password"] == "s3cret"


def test_no_credentials_by_default():
    data = yaml.safe_load(_render())
    assert "username" not in data["proxies"][0]


@pytest.mark.parametrize("bad", ["", "has space", "a/b", "中文"])
def test_invalid_server_is_rejected(bad):
    with pytest.raises(profile.ProfileError):
        profile.ProfileOptions(server=bad)


@pytest.mark.parametrize("port", [0, -1, 70000])
def test_invalid_port_is_rejected(port):
    with pytest.raises(profile.ProfileError):
        profile.ProfileOptions(server=SERVER, port=port)


def test_no_placeholder_survives_rendering():
    text = _render()
    assert not re.search(r"\{\{[A-Z_]+\}\}", text)
    assert SERVER in text


@pytest.mark.e2e
@pytest.mark.parametrize("mode", [profile.MODE_G1_ONLY, profile.MODE_SUBSCRIPTION])
def test_mihomo_accepts_the_generated_profile(mode, tmp_path):
    binary = shutil.which("mihomo")
    if not binary:
        pytest.skip("mihomo binary not installed")
    options = profile.ProfileOptions(server=SERVER, mode=mode,
                                     subscription="https://example.com/sub")
    target = tmp_path / "config.yaml"
    target.write_text(profile.render(options), encoding="utf-8")
    result = subprocess.run([binary, "-t", "-d", str(tmp_path), "-f", str(target)],
                            capture_output=True, text=True)
    assert "test is successful" in result.stdout + result.stderr, result.stdout + result.stderr
