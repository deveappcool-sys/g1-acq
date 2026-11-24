"""The self-check report is what a stranger pastes into an issue."""

from __future__ import annotations

import json
import socket

from g1acq import config, doctor
from g1acq.app import G1App
from g1acq.store import FileStore


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_report_labels_every_check(tmp_path):
    state = tmp_path / "state.json"
    app = G1App(FileStore(state))
    app.on_response("https://one.google.com/ai?x=1", json.dumps(["g1.ios.2tb.m"]))

    checks = doctor.collect(
        state_path=state,
        sidecar_port=_free_port(),      # nothing listening -> bad
        console_port=0,
        confdir=str(tmp_path / "nope"),
    )
    text = doctor.render(checks, state_path=state)

    assert "G1 ACQ 自检报告" in text
    for check in checks:
        assert f"{check.marker} {check.label}:" in text

    labels = {c.label: c for c in checks}
    assert labels["状态文件"].status == doctor.OK
    assert labels["旁路端口"].status == doctor.BAD
    assert labels["根证书"].status == doctor.BAD
    assert labels["最近改写"].status == doctor.OK
    assert "需要处理" in text


def test_report_never_leaks_private_material(tmp_path):
    state = tmp_path / "state.json"
    app = G1App(FileStore(state))
    app.on_response("https://one.google.com/ai?x=1", json.dumps(["g1.ios.2tb.m"]))
    text = doctor.render(
        doctor.collect(state_path=state, sidecar_port=_free_port(), confdir=str(tmp_path)),
        state_path=state,
    )
    # no certificate body, no account data, no response bodies
    assert "BEGIN CERTIFICATE" not in text
    assert "PRIVATE KEY" not in text


def test_missing_state_is_reported_not_crashed(tmp_path):
    checks = doctor.collect(
        state_path=tmp_path / "absent.json", sidecar_port=_free_port(), console_port=0
    )
    labels = {c.label: c for c in checks}
    assert labels["状态文件"].status == doctor.BAD


def test_collect_reports_the_collector_version(tmp_path):
    checks = doctor.collect(
        state_path=tmp_path / "absent.json", sidecar_port=_free_port(), console_port=0
    )
    version = next(c for c in checks if c.label == "版本")
    assert config.COLLECTOR_VERSION in version.detail
