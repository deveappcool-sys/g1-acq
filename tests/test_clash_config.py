"""Invariants that keep a generated profile importable.

These are the mistakes that silently break the feature: a rule pointing at a
proxy that does not exist, a group member that was renamed, or one.google.com
being swallowed by the catch-all rule.
"""

from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

from g1acq import profile  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNIPPET = ROOT / "clash" / "g1-acq.snippet.yaml"

BUILTIN_POLICIES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}
TRAILING_FLAGS = {"no-resolve", "src"}

MODES = {
    "g1": profile.ProfileOptions(server="192.168.2.57"),
    "sub": profile.ProfileOptions(server="192.168.2.57", mode=profile.MODE_SUBSCRIPTION,
                                  subscription="https://example.com/sub"),
    "auth": profile.ProfileOptions(server="192.168.2.57", auth="g1:pw"),
}


def split_rule(rule: str) -> tuple[str, str]:
    """Return ``(TYPE, POLICY)`` from ``TYPE,payload[,params],POLICY[,flags]``."""
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
    while len(parts) > 2 and parts[-1] in TRAILING_FLAGS:
        parts.pop()
    return parts[0], parts[-1]


def names(config: dict) -> set[str]:
    return {p["name"] for p in config.get("proxies", [])} | {
        g["name"] for g in config.get("proxy-groups", [])}


@pytest.mark.parametrize("label", sorted(MODES))
def test_every_rule_target_resolves(label):
    data = yaml.safe_load(profile.render(MODES[label]))
    known = names(data) | BUILTIN_POLICIES
    for rule in data["rules"]:
        kind, policy = split_rule(rule)
        assert kind, f"rule without a type: {rule!r}"
        assert policy in known, f"{label}: {rule!r} -> unknown policy {policy!r}"


@pytest.mark.parametrize("label", sorted(MODES))
def test_every_group_member_resolves(label):
    """A renamed proxy is the classic 'mihomo refuses to start' mistake."""
    data = yaml.safe_load(profile.render(MODES[label]))
    known = names(data) | BUILTIN_POLICIES
    for group in data["proxy-groups"]:
        for member in group.get("proxies", []):
            assert member in known, f"{label}: group {group['name']} -> {member}"
    if "proxy-providers" in data:
        providers = set(data["proxy-providers"])
        for group in data["proxy-groups"]:
            for used in group.get("use", []):
                assert used in providers, f"{label}: group {group['name']} -> provider {used}"


@pytest.mark.parametrize("label", sorted(MODES))
def test_one_google_is_routed_to_the_sidecar_before_the_catch_all(label):
    data = yaml.safe_load(profile.render(MODES[label]))
    rules = data["rules"]
    match_index = next(i for i, r in enumerate(rules) if r.startswith("MATCH,"))
    resolved = [r for r in rules if r.startswith("DOMAIN,one.google.com,")]
    assert resolved, "one.google.com needs an explicit DOMAIN rule"
    assert split_rule(resolved[0])[1] == "G1"
    for index, rule in enumerate(rules):
        if "one.google.com" in rule:
            assert index < match_index


@pytest.mark.parametrize("label", sorted(MODES))
def test_quic_guard_runs_first_and_is_scoped(label):
    rules = yaml.safe_load(profile.render(MODES[label]))["rules"]
    first = rules[0]
    kind, policy = split_rule(first)
    assert kind == "AND" and policy == "REJECT-DROP"
    assert "(NETWORK,udp)" in first and "(DST-PORT,443)" in first
    assert "(DOMAIN,one.google.com)" in first


@pytest.mark.parametrize("label", sorted(MODES))
def test_sidecar_proxy_is_a_plain_http_proxy(label):
    data = yaml.safe_load(profile.render(MODES[label]))
    proxy = next(p for p in data["proxies"] if p["name"] == "G1-MITM")
    assert proxy["type"] == "http"
    assert proxy["tls"] is False
    assert "udp" not in proxy, "udp is not an http-proxy option"


def test_fake_ip_and_quic_sniffing_are_enabled():
    data = yaml.safe_load(profile.render(MODES["g1"]))
    assert data["dns"]["enhanced-mode"] == "fake-ip"
    assert data["sniffer"]["enable"] is True
    assert 443 in data["sniffer"]["sniff"]["QUIC"]["ports"]


def test_manual_snippet_matches_the_generated_rules():
    snippet = yaml.safe_load(SNIPPET.read_text(encoding="utf-8"))
    generated = yaml.safe_load(profile.render(MODES["g1"]))
    assert snippet["rules"] == generated["rules"][: len(snippet["rules"])]
    assert snippet["proxy-groups"][0]["name"] == "G1"
    assert snippet["proxies"][0]["type"] == "http"
