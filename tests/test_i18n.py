"""The message catalogue: both languages, complete, and actually used."""

from __future__ import annotations

import json
import re

import pytest

from g1acq import i18n


def test_every_message_has_both_languages():
    for key, value in i18n.MESSAGES.items():
        assert isinstance(value, tuple) and len(value) == 2, key
        zh, en = value
        assert zh.strip(), f"{key} has no Chinese text"
        assert en.strip(), f"{key} has no English text"


def test_placeholders_agree_between_languages():
    """A format field present in one language must exist in the other."""
    for key, (zh, en) in i18n.MESSAGES.items():
        fields_zh = set(re.findall(r"\{(\w+)\}", zh))
        fields_en = set(re.findall(r"\{(\w+)\}", en))
        assert fields_zh == fields_en, f"{key}: {fields_zh} vs {fields_en}"


def test_translation_picks_the_requested_language():
    assert i18n.t("doctor.clean", lang="zh") == "没有发现明显问题。"
    assert i18n.t("doctor.clean", lang="en") == "No obvious problems found."
    # anything unrecognised falls back to the default instead of raising
    assert i18n.t("doctor.clean", lang="fr") == "没有发现明显问题。"


def test_placeholders_are_filled():
    zh = i18n.t("cli.state_path", lang="zh", path="/tmp/x")
    en = i18n.t("cli.state_path", lang="en", path="/tmp/x")
    assert "/tmp/x" in zh and "/tmp/x" in en
    assert "{" not in zh and "{" not in en


def test_unknown_key_is_loud():
    with pytest.raises(KeyError):
        i18n.t("no.such.key")


def test_language_follows_the_environment(monkeypatch):
    monkeypatch.setenv("G1_LANG", "en")
    assert i18n.set_language(None) == "en"
    assert i18n.current_language() == "en"
    monkeypatch.delenv("G1_LANG")
    assert i18n.set_language(None) == "zh"


def test_console_page_renders_in_both_languages():
    from g1acq.setup_console import SetupConsole
    from g1acq.store import MemoryStore

    console = SetupConsole(MemoryStore(), port=8099, server_host="192.168.2.57")
    for lang, marker in (("zh", "安装控制台"), ("en", "setup console")):
        html = console._page(lang).decode()
        assert marker in html
        assert not re.findall(r"\{\{[^}]+\}\}", html), f"{lang} left placeholders behind"
        assert "192.168.2.57:8080" in html
        assert "one.google.com" in html
        # No field may survive in the markup. The <script> block legitimately
        # carries {count} as a runtime template for the browser to substitute.
        markup = html.split("<script>")[0]
        assert not re.findall(r"\{[a-z_]+\}", markup), "unfilled field in markup"
        assert "{count}" in html, "the JS template should still be there"


def test_doctor_report_renders_in_both_languages(tmp_path):
    from g1acq import doctor

    for lang, marker in (("zh", "自检报告"), ("en", "self-check")):
        checks = doctor.collect(
            state_path=tmp_path / "absent.json", sidecar_port=1, console_port=0,
            confdir=str(tmp_path), lang=lang,
        )
        text = doctor.render(checks, lang=lang)
        assert marker in text
        # the report must stay pasteable: no untranslated braces, no crash
        assert "{" not in text.replace("{}", "")


def test_console_status_json_is_language_neutral():
    """Status keys are machine-readable and must not change with the language."""
    from g1acq.setup_console import SetupConsole
    from g1acq.store import MemoryStore

    console = SetupConsole(MemoryStore(), port=8099, server_host="192.168.2.57")
    payload = console._status()
    assert json.loads(json.dumps(payload)) == payload
    for key in ("server", "port", "scanned_responses", "last_test_status", "hit_count"):
        assert key in payload
