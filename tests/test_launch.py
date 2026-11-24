"""The launcher must produce the flags documented in the README."""

from __future__ import annotations

import os

from g1acq import launch


def _pairs(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for index, item in enumerate(argv):
        if item == "--set" and index + 1 < len(argv):
            key, _, value = argv[index + 1].partition("=")
            out[key] = value
    return out


def test_defaults_listen_on_8080_and_only_intercept_one_google():
    argv = launch.build_argv(launch.LaunchOptions())
    assert argv[0] == "mitmdump"
    assert argv[argv.index("-p") + 1] == "8080"
    flags = _pairs(argv)
    assert flags["allow_hosts"] == launch.ALLOW_HOSTS
    assert flags["g1_state"].endswith("state.json")
    assert "g1_target" not in flags, "the default target must not be overridden"


def test_state_path_is_expanded_and_absolute():
    argv = launch.build_argv(launch.LaunchOptions(state="~/custom/state.json"))
    path = _pairs(argv)["g1_state"]
    assert os.path.isabs(path)
    assert not path.startswith("~")
    assert path.endswith("custom/state.json")


def test_upstream_chaining_is_optional():
    plain = " ".join(launch.build_argv(launch.LaunchOptions()))
    assert "--mode" not in plain

    chained = launch.build_argv(
        launch.LaunchOptions(upstream="http://127.0.0.1:7890")
    )
    assert chained[chained.index("--mode") + 1] == "upstream:http://127.0.0.1:7890"


def test_bind_and_target_overrides():
    argv = launch.build_argv(
        launch.LaunchOptions(bind="0.0.0.0", target="g1.2tb.ai.custom_ip_90p")
    )
    assert argv[argv.index("--listen-host") + 1] == "0.0.0.0"
    assert _pairs(argv)["g1_target"] == "g1.2tb.ai.custom_ip_90p"


def test_allow_hosts_can_be_disabled_explicitly():
    argv = launch.build_argv(launch.LaunchOptions(allow_hosts=""))
    assert "allow_hosts" not in _pairs(argv)


def test_extra_flags_are_appended_verbatim():
    argv = launch.build_argv(
        launch.LaunchOptions(extra=("--set", "confdir=/tmp/mitm"))
    )
    assert argv[-2:] == ["--set", "confdir=/tmp/mitm"]


def test_auth_is_forwarded_as_proxyauth():
    argv = launch.build_argv(launch.LaunchOptions(auth="g1:s3cret"))
    assert _pairs(argv)["proxyauth"] == "g1:s3cret"


def test_credentials_are_masked_in_the_echoed_command():
    argv = launch.build_argv(launch.LaunchOptions(auth="g1:s3cret"))
    printed = launch.describe(argv)
    assert "s3cret" not in printed
    assert "proxyauth=g1:***" in printed


def test_validate_auth_rejects_malformed_values():
    assert launch.validate_auth("") == ""
    assert launch.validate_auth("g1:pa:ss") == "g1:pa:ss"
    for bad in ("nocolon", ":nouser", "user:"):
        try:
            launch.validate_auth(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should have been rejected")


def test_serve_refuses_an_invalid_target_before_starting(monkeypatch):
    from g1acq import __main__ as cli

    rc = cli.main(["serve", "--target", "not a sku!"])
    assert rc == 2
