"""``g1-acq doctor`` — one command that answers "why isn't it working?".

The people running this project install it on their own machine; when something
goes wrong they cannot see the logs and do not know which of the five moving
parts is at fault.  The report this produces is meant to be pasted into an
issue, so it must be complete, short and free of anything private.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from . import ca, config, network
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
) -> list[Check]:
    checks: list[Check] = []
    path = Path(os.path.expanduser(str(state_path)))

    sidecar_up = port_open("127.0.0.1", sidecar_port)
    checks.append(Check(
        "旁路端口", OK if sidecar_up else BAD,
        f"127.0.0.1:{sidecar_port} " + ("可连接" if sidecar_up else "连不上（服务没在跑？）"),
    ))
    if console_port:
        console_up = port_open("127.0.0.1", console_port)
        checks.append(Check(
            "安装控制台", OK if console_up else INFO,
            f"127.0.0.1:{console_port} " + ("可连接" if console_up else "未启用"),
        ))

    if path.exists():
        stat = path.stat()
        age = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
        checks.append(Check("状态文件", OK, f"{path}（{stat.st_size} 字节，最后写入 {age}）"))
    else:
        checks.append(Check("状态文件", BAD, f"{path} 不存在：还没收到过 one.google.com 的响应"))

    try:
        report = build_report(FileStore(path), config.REPORT_ROOT + "?format=json")
        import json

        data = json.loads(report.body)
        scan, test = data["scan"], data["test"]
        checks.append(Check(
            "采集", OK if scan["scannedResponses"] else INFO,
            f"扫描 {scan['scannedResponses']} 个响应，采集 {len(scan['skus'])} 个编号，"
            f"最近写入 {scan['updatedAt'] or '无'}"
        ))
        if test["status"]:
            checks.append(Check(
                "最近改写", OK,
                f"{test['status']} · {test['hitCount']} 处（其中 2TB {test['annualHitCount']}）"
                f" · {test['updatedAt']}"
            ))
        else:
            ios = [r["id"] for r in scan["skus"] if r["id"].startswith("g1.ios.")]
            checks.append(Check(
                "最近改写", INFO,
                "还没有走到 /ai? 路径" + ("（已见到 iOS 编号，说明入口对了）" if ios else "")
            ))
    except Exception as error:  # pragma: no cover - defensive
        checks.append(Check("状态文件读取", BAD, repr(error)))

    try:
        checks.append(Check("根证书", OK, f"{ca.fingerprint(confdir)}"))
    except ca.MissingCertificate:
        checks.append(Check("根证书", BAD, "还没生成：启动服务一次会让 mitmproxy 创建它"))
    except Exception as error:  # pragma: no cover
        checks.append(Check("根证书", BAD, repr(error)))

    addresses = network.lan_addresses()
    checks.append(Check(
        "本机地址", OK if addresses else BAD,
        " / ".join(addresses) if addresses else "没检测到局域网地址"
    ))
    checks.append(Check(
        "配置里的地址", INFO,
        f"生成配置时应当填 {addresses[0] if addresses else '?'}；换过 Wi-Fi 就要重新生成"
    ))

    try:
        import importlib.metadata as metadata

        checks.append(Check("mitmproxy", INFO, metadata.version("mitmproxy")))
    except Exception:  # pragma: no cover
        checks.append(Check("mitmproxy", INFO, "未知"))

    checks.append(Check("版本", INFO, f"{config.PROJECT_VERSION} / {config.COLLECTOR_VERSION}"))
    return checks


def render(checks: list[Check], *, state_path: str | os.PathLike[str]) -> str:
    lines = ["G1 ACQ 自检报告", "=" * 40]
    for check in checks:
        lines.append(f"{check.marker} {check.label}: {check.detail}")
    problems = [c for c in checks if c.status == BAD]
    lines.append("=" * 40)
    if problems:
        lines.append("需要处理：")
        for check in problems:
            lines.append(f"  - {check.label}: {check.detail}")
    else:
        lines.append("没有发现明显问题。")
    lines.append("")
    lines.append("排错时把上面这段完整贴出来即可（不含任何证书私钥或账号信息）。")
    return "\n".join(lines)
