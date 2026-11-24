"""Static checks for the shipped Clash profile.

These catch the mistakes that silently break the feature: a rule pointing at a
proxy that does not exist, the MATCH rule swallowing one.google.com first, or
the snippet drifting away from the full profile.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "clash" / "g1-acq.yaml"
SNIPPET = ROOT / "clash" / "g1-acq.snippet.yaml"

yaml = pytest.importorskip("yaml")

BUILTIN_POLICIES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}
SIDECAR = "G1-MITM"
GROUP = "G1"


@pytest.fixture(scope="module")
def profile() -> dict:
    return yaml.safe_load(PROFILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def snippet() -> dict:
    return yaml.safe_load(SNIPPET.read_text(encoding="utf-8"))


def split_rule(rule: str) -> tuple[str, str]:
    """Split ``TYPE,payload,POLICY`` at the commas outside parentheses."""
    parts: list[str] = []
    depth = 0
    current = ""
    for character in rule:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += character
    parts.append(current)
    return parts[0], parts[-1]


def names(config: dict) -> set[str]:
    return {proxy["name"] for proxy in config.get("proxies", [])} | {
        group["name"] for group in config.get("proxy-groups", [])
    }


def test_profile_declares_the_sections_clients_need(profile):
    for key in ("proxies", "proxy-groups", "rules", "dns", "sniffer"):
        assert key in profile, f"missing top-level section {key}"
    assert profile["mode"] == "rule"


def test_every_rule_target_resolves(profile):
    known = names(profile) | BUILTIN_POLICIES
    for rule in profile["rules"]:
        kind, policy = split_rule(rule)
        assert kind, f"rule without a type: {rule!r}"
        assert policy in known, f"rule {rule!r} points at unknown policy {policy!r}"


def test_one_google_reaches_the_sidecar(profile):
    rules = profile["rules"]
    domain_rules = [rule for rule in rules if rule.startswith("DOMAIN,one.google.com,")]
    assert domain_rules, "one.google.com must have an explicit DOMAIN rule"
    assert all(split_rule(rule)[1] == GROUP for rule in domain_rules)

    match_index = next(index for index, rule in enumerate(rules) if rule.startswith("MATCH,"))
    for index, rule in enumerate(rules):
        if "one.google.com" in rule:
            assert index < match_index, "one.google.com rules must precede MATCH"


def test_quic_guard_runs_first_and_is_scoped(profile):
    first = profile["rules"][0]
    kind, policy = split_rule(first)
    assert kind == "AND"
    assert policy == "REJECT-DROP"
    assert "(NETWORK,udp)" in first
    assert "(DST-PORT,443)" in first
    assert "(DOMAIN,one.google.com)" in first
    assert profile["rules"][1].startswith("DOMAIN,one.google.com,")


def test_sidecar_proxy_is_a_plain_http_proxy(profile):
    proxy = next(item for item in profile["proxies"] if item["name"] == SIDECAR)
    assert proxy["type"] == "http"
    assert isinstance(proxy["port"], int)
    assert proxy.get("tls") in (False, None), (
        "the sidecar hop only carries CONNECT; enabling upstream TLS here would "
        "make mihomo speak TLS to mitmproxy's plain listener"
    )


def test_fake_ip_keeps_the_domain_visible(profile):
    # DOMAIN rules are only reliable if the proxy still knows the hostname.
    assert profile["dns"]["enhanced-mode"] == "fake-ip"
    assert profile["sniffer"]["enable"] is True


def test_snippet_is_a_subset_of_the_profile(profile, snippet):
    assert snippet["rules"] == profile["rules"][: len(snippet["rules"])]
    profile_proxies = {item["name"]: item for item in profile["proxies"]}
    for proxy in snippet["proxies"]:
        assert profile_proxies[proxy["name"]]["type"] == proxy["type"]
        assert profile_proxies[proxy["name"]]["port"] == proxy["port"]
    assert snippet["proxy-groups"][0]["name"] == GROUP
    assert snippet["proxy-groups"][0]["type"] == "select"
    assert SIDECAR in snippet["proxy-groups"][0]["proxies"]


@pytest.mark.e2e
def test_mihomo_accepts_the_shipped_profile(tmp_path):
    binary = shutil.which("mihomo")
    if not binary:
        pytest.skip("mihomo binary not installed")
    target = tmp_path / "config.yaml"
    target.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        [binary, "-t", "-d", str(tmp_path), "-f", str(target)],
        capture_output=True,
        text=True,
    )
    assert "test is successful" in result.stdout + result.stderr, (
        result.stdout + result.stderr
    )
