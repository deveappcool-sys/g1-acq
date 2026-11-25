"""``g1-acq doctor`` — one command that answers "why isn't it working?".

The people running this project install it on their own machine; when something
goes wrong they cannot see the logs and do not know which of the five moving
parts is at fault.  The report this produces is meant to be pasted into an
issue, so it must be complete, short and free of anything private.
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from . import ca, config, i18n, network
from .report import build_report
from .store import FileStore

OK = "ok"
BAD = "bad"
INFO = "info"


@dataclass
class Check:
    label: str
    status: str
    detail: str

    @property
    def marker(self) -> str:
        return {OK: "✔", BAD: "✖", INFO: "·"}[self.status]


def port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def collect(
    *,
    state_path: str | os.PathLike[str],
    sidecar_port: int = 8080,
    console_port: int = 8090,
    confdir: str | None = None,
    lang: str | None = None,
) -> list[Check]:
    lang = i18n.normalize(lang or i18n.current_language())
    t = lambda key, **kw: i18n.t(key, lang=lang, **kw)  # noqa: E731

    checks: list[Check] = []
    path = Path(os.path.expanduser(str(state_path)))

    sidecar_up = port_open("127.0.0.1", sidecar_port)
    checks.append(Check(
        t("doctor.sidecar"),
        OK if sidecar_up else BAD,
        f"127.0.0.1:{sidecar_port} " + t("doctor.sidecar.up" if sidecar_up else "doctor.sidecar.down"),
    ))
    if console_port:
        console_up = port_open("127.0.0.1", console_port)
        checks.append(Check(
            t("doctor.console"),
            OK if console_up else INFO,
            f"127.0.0.1:{console_port} " + t("doctor.console.up" if console_up else "doctor.console.off"),
        ))

    if path.exists():
        stat = path.stat()
        age = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
        checks.append(Check(t("doctor.state"), OK, f"{path} ({stat.st_size} bytes, {age})"))
    else:
        checks.append(Check(t("doctor.state"), BAD, t("doctor.state.missing", path=path)))

    try:
        report = build_report(FileStore(path), config.REPORT_ROOT + "?format=json")
        data = json.loads(report.body)
        scan, test = data["scan"], data["test"]
        checks.append(Check(
            t("doctor.collect"),
            OK if scan["scannedResponses"] else INFO,
            t("doctor.collect.detail", scanned=scan["scannedResponses"],
              candidates=len(scan["skus"]), at=scan["updatedAt"] or "-"),
        ))
        if test["status"]:
            checks.append(Check(
                t("doctor.rewrite"), OK,
                t("doctor.rewrite.detail", status=test["status"], hits=test["hitCount"],
                  annual=test["annualHitCount"], at=test["updatedAt"]),
            ))
        else:
            has_ios = any(r["id"].startswith("g1.ios.") for r in scan["skus"])
            checks.append(Check(
                t("doctor.rewrite"), INFO,
                t("doctor.rewrite.none_ios" if has_ios else "doctor.rewrite.none"),
            ))
    except Exception as error:  # pragma: no cover - defensive
        checks.append(Check(t("doctor.state.read_error"), BAD, repr(error)))

    try:
        checks.append(Check(t("doctor.ca"), OK, ca.fingerprint(confdir)))
    except ca.MissingCertificate:
        checks.append(Check(t("doctor.ca"), BAD, t("doctor.ca.missing")))
    except Exception as error:  # pragma: no cover
        checks.append(Check(t("doctor.ca"), BAD, repr(error)))

    addresses = network.lan_addresses()
    checks.append(Check(
        t("doctor.address"), OK if addresses else BAD,
        " / ".join(addresses) if addresses else t("doctor.address.none"),
    ))
    checks.append(Check(
        t("doctor.profile_address"), INFO,
        t("doctor.profile_address.detail", address=addresses[0] if addresses else "?"),
    ))

    try:
        import importlib.metadata as metadata

        checks.append(Check("mitmproxy", INFO, metadata.version("mitmproxy")))
    except Exception:  # pragma: no cover
        checks.append(Check("mitmproxy", INFO, "unknown"))

    checks.append(Check(
        t("doctor.version"), INFO, f"{config.PROJECT_VERSION} / {config.COLLECTOR_VERSION}"
    ))
    return checks


def render(checks: list[Check], *, state_path: str | os.PathLike[str] | None = None,
           lang: str | None = None) -> str:
    lang = i18n.normalize(lang or i18n.current_language())
    t = lambda key, **kw: i18n.t(key, lang=lang, **kw)  # noqa: E731
    del state_path  # kept for call-site compatibility

    lines = [t("doctor.title"), "=" * 40]
    for check in checks:
        lines.append(f"{check.marker} {check.label}: {check.detail}")
    problems = [c for c in checks if c.status == BAD]
    lines.append("=" * 40)
    if problems:
        lines.append(t("doctor.problem_heading"))
        for check in problems:
            lines.append(f"  - {check.label}: {check.detail}")
    else:
        lines.append(t("doctor.clean"))
    lines.append("")
    lines.append(t("doctor.footer"))
    return "\n".join(lines)
