"""Generate a ready-to-import Clash profile.

Handing a user a template with ``192.168.1.10`` in it was the single biggest
source of support load: the address changes with the network, and nobody
enjoys editing YAML on a phone.  The console asks this module instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE_PATH = Path(__file__).with_name("profile.template.yaml")

MODE_G1_ONLY = "g1"
MODE_SUBSCRIPTION = "sub"

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+$")
_URL_RE = re.compile(r"^https?://\S+$")
_AUTH_RE = re.compile(r"^[^:\s]+:[^\s]+$")


class ProfileError(ValueError):
    """User-facing validation error."""


@dataclass
class ProfileOptions:
    server: str
    port: int = 8080
    mode: str = MODE_G1_ONLY
    subscription: str = ""
    # "user:password" — only used when the sidecar runs with G1_AUTH.
    auth: str = ""
    mixed_port: int = 7890
    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.server or not _HOST_RE.match(self.server):
            raise ProfileError(f"服务器地址不合法：{self.server!r}")
        if not 1 <= int(self.port) <= 65535:
            raise ProfileError(f"端口不合法：{self.port}")
        if self.mode not in (MODE_G1_ONLY, MODE_SUBSCRIPTION):
            raise ProfileError(f"模式不合法：{self.mode!r}")
        if self.mode == MODE_SUBSCRIPTION and not _URL_RE.match(self.subscription or ""):
            raise ProfileError("订阅版需要填入 http(s) 开头的订阅链接")
        if self.auth and not _AUTH_RE.match(self.auth):
            raise ProfileError("认证信息要写成 用户名:密码")


def _proxy_block(options: ProfileOptions) -> str:
    lines = [
        "  - name: \"G1-MITM\"",
        "    type: http",
        f"    server: {options.server}",
        f"    port: {int(options.port)}",
        "    tls: false",
    ]
    if options.auth:
        user, _, password = options.auth.partition(":")
        lines.append(f"    username: \"{user}\"")
        lines.append(f"    password: \"{password}\"")
    return "\n".join(lines)


_G1_GROUP = """  - name: "G1"
    type: select
    proxies:
      - "G1-MITM"
      - DIRECT"""

_QUIC_GUARD = "  - AND,((NETWORK,udp),(DST-PORT,443),(DOMAIN,one.google.com)),REJECT-DROP"

_LOCAL_RULES = """  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR6,fc00::/7,DIRECT,no-resolve"""


def _providers_block(options: ProfileOptions) -> str:
    if options.mode != MODE_SUBSCRIPTION:
        return ""
    return (
        "proxy-providers:\n"
        "  my-sub:\n"
        "    type: http\n"
        f"    url: \"{options.subscription}\"\n"
        "    proxy: DIRECT          # 首次拉订阅时还没有节点可用，必须直连\n"
        "    interval: 86400\n"
        "    path: ./providers/my-sub.yaml\n"
        "    health-check:\n"
        "      enable: true\n"
        "      url: https://www.gstatic.com/generate_204\n"
        "      interval: 300\n"
    )


def _groups_block(options: ProfileOptions) -> str:
    if options.mode != MODE_SUBSCRIPTION:
        return _G1_GROUP
    return "\n".join(
        [
            '  - name: "PROXY"',
            "    type: select",
            "    proxies:",
            '      - "AUTO"          # 默认走你自己的节点，不是旁路',
            '      - "DIRECT"',
            '  - name: "AUTO"',
            "    type: url-test",
            "    use:",
            '      - "my-sub"',
            "    url: https://www.gstatic.com/generate_204",
            "    interval: 300",
            _G1_GROUP,
        ]
    )


def _rules_block(options: ProfileOptions) -> str:
    head = "\n".join(
        [
            _QUIC_GUARD,
            "  - DOMAIN,one.google.com,G1",
            "  - DOMAIN-SUFFIX,one.google.com,G1",
            _LOCAL_RULES,
        ]
    )
    tail = "  - MATCH,PROXY" if options.mode == MODE_SUBSCRIPTION else "  - MATCH,DIRECT"
    return head + "\n" + tail


def render(options: ProfileOptions) -> str:
    """Return the finished YAML text."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    mode_label = (
        "带着你自己的节点（订阅）" if options.mode == MODE_SUBSCRIPTION
        else "只做 G1，其它流量直连"
    )
    replacements = {
        "{{GENERATED}}": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "{{SERVER}}": options.server,
        "{{PORT}}": str(int(options.port)),
        "{{MIXED_PORT}}": str(int(options.mixed_port)),
        "{{MODE_LABEL}}": mode_label,
        "{{PROVIDERS}}": _providers_block(options),
        "{{PROXIES}}": _proxy_block(options),
        "{{GROUPS}}": _groups_block(options),
        "{{RULES}}": _rules_block(options),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", template)
    if leftover:  # pragma: no cover - guards against template drift
        raise ProfileError(f"模板里有没替换的占位符：{leftover}")
    return template
