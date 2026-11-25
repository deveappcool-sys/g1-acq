"""Message catalogue.

The project is Chinese-first: logs, the console and the self-check all speak
Chinese by default.  English is a full alternative, not an afterthought, so the
strings live in one table instead of being scattered through the code.

Language resolution, in order:
  1. an explicit ``lang=`` argument (the console passes it per request)
  2. ``G1_LANG`` in the environment
  3. ``zh``

Key/value diagnostics (``status=new-skus addedCount=11``) are deliberately *not*
translated: they are grepped, parsed and compared across versions, and changing
them per language would break that.
"""

from __future__ import annotations

import os

LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"

_current = DEFAULT_LANGUAGE


def normalize(value: str | None) -> str:
    """Map anything to a supported language code, falling back to the default."""
    text = (value or "").strip().lower()
    if text.startswith("en"):
        return "en"
    if text.startswith("zh") or text.startswith("cn"):
        return "zh"
    return DEFAULT_LANGUAGE


def set_language(value: str | None) -> str:
    """Set the process-wide default and return the resolved code."""
    global _current
    if value:
        _current = normalize(value)
    else:
        _current = normalize(os.environ.get("G1_LANG"))
    return _current


def current_language() -> str:
    return _current


# key -> (zh, en)
MESSAGES: dict[str, tuple[str, str]] = {
    # ------------------------------------------------------------------ doctor
    "doctor.title": ("G1 ACQ 自检报告", "G1 ACQ self-check"),
    "doctor.problem_heading": ("需要处理：", "Needs attention:"),
    "doctor.clean": ("没有发现明显问题。", "No obvious problems found."),
    "doctor.footer": (
        "排错时把上面这段完整贴出来即可（不含任何证书私钥或账号信息）。",
        "Paste the block above into a bug report "
        "(it contains no private key and no account data).",
    ),
    "doctor.sidecar": ("旁路端口", "sidecar port"),
    "doctor.sidecar.up": ("可连接", "reachable"),
    "doctor.sidecar.down": ("连不上（服务没在跑？）", "unreachable — is the service running?"),
    "doctor.console": ("安装控制台", "setup console"),
    "doctor.console.up": ("可连接", "reachable"),
    "doctor.console.off": ("未启用", "disabled"),
    "doctor.state": ("状态文件", "state file"),
    "doctor.state.missing": (
        "{path} 不存在：还没收到过 one.google.com 的响应",
        "{path} does not exist yet — no one.google.com response has arrived",
    ),
    "doctor.state.read_error": ("状态文件读取", "reading the state file"),
    "doctor.collect": ("采集", "collection"),
    "doctor.collect.detail": (
        "扫描 {scanned} 个响应，采集 {candidates} 个编号，最近写入 {at}",
        "scanned {scanned} responses, collected {candidates} IDs, last write {at}",
    ),
    "doctor.rewrite": ("最近改写", "last rewrite"),
    "doctor.rewrite.detail": (
        "{status} · {hits} 处（其中 2TB {annual}） · {at}",
        "{status} · {hits} replacements (2TB: {annual}) · {at}",
    ),
    "doctor.rewrite.none": ("还没有走到 /ai? 路径", "no /ai? request seen yet"),
    "doctor.rewrite.none_ios": (
        "还没有走到 /ai? 路径（已见到 iOS 编号，说明入口对了）",
        "no /ai? request yet (iOS product IDs already seen, so the entrance is right)",
    ),
    "doctor.ca": ("根证书", "root CA"),
    "doctor.ca.missing": (
        "还没生成：启动服务一次会让 mitmproxy 创建它",
        "not created yet — start the service once and mitmproxy will make it",
    ),
    "doctor.address": ("本机地址", "LAN address"),
    "doctor.address.none": ("没检测到局域网地址", "no LAN address detected"),
    "doctor.profile_address": ("配置里的地址", "address in the profile"),
    "doctor.profile_address.detail": (
        "生成配置时应当填 {address}；换过 Wi-Fi 就要重新生成",
        "the profile should contain {address}; re-generate it after a network change",
    ),
    "doctor.version": ("版本", "version"),

    # --------------------------------------------------------------------- cli
    "cli.bad_auth": ("--auth 要写成 用户名:密码", "--auth must look like user:password"),
    "cli.bad_target": ("目标 SKU 不合法：{target!r}", "invalid target SKU: {target!r}"),
    "cli.no_auth_warning": (
        "[g1-acq] 警告：没设 --auth，任何能连上这个端口的人都能拿它当代理，"
        "也能读和清空报告。\n"
        "[g1-acq]       除非只监听本机，否则建议加 --auth 用户名:密码，"
        "并在 Clash 的 G1-MITM 里填同样的凭据。",
        "[g1-acq] warning: no --auth set; anyone who can reach this port can use it "
        "as a proxy and read or clear the report.\n"
        "[g1-acq]          add --auth user:password (and matching credentials to the "
        "Clash G1-MITM proxy) unless it listens on loopback only.",
    ),
    "cli.state_path": ("[g1-acq] 状态文件: {path}", "[g1-acq] state: {path}"),
    "cli.exec": ("[g1-acq] 执行: {command}", "[g1-acq] exec: {command}"),
    "cli.no_mitmdump": (
        "找不到 mitmdump。先装依赖：\n  pip install mitmproxy\n"
        "或者在项目的虚拟环境里运行这条命令。",
        "mitmdump not found. Install the dependencies first:\n  pip install mitmproxy\n"
        "or run this command inside the project virtualenv.",
    ),
    "cli.no_state": ("[g1-acq] 还没有状态文件：{path}", "[g1-acq] no state file yet at {path}"),
    "cli.nothing_to_clear": ("没有可清理的记录。", "Nothing to clear."),
    "cli.no_lan": (
        "没检测到局域网地址：这台机器现在没有连上任何网络？",
        "No LAN address detected — is this machine offline?",
    ),
    "cli.console_hint": ("手机先打开这个（装证书 + 导配置）：", "Open this on the phone first "
                         "(certificate + profile):"),
    "cli.clash_hint": ("Clash 也可以直接用「从 URL 导入」这个地址：",
                       "Or paste this into Clash's \"import from URL\":"),
    "cli.ca_not_found": (
        "在 {path} 找不到根证书。先启动一次服务，mitmproxy 会创建它。",
        "CA not found at {path}. Start the sidecar once; mitmproxy creates it.",
    ),
    "cli.ca_wrote": ("已写出 {path}（{size} 字节）", "wrote {path} ({size} bytes)"),

    # ------------------------------------------------------------------- logs
    "log.console_ready": ("[g1-acq] 安装控制台: {url}", "[g1-acq] setup console: {url}"),
    "log.console_failed": (
        "[g1-acq] 安装控制台未启动（端口 {port} 被占用）: {error}",
        "[g1-acq] setup console not started (port {port} busy): {error}",
    ),
    "log.invalid_option": (
        "[g1-acq] 选项不合法，改用默认值: {error}",
        "[g1-acq] invalid option, using defaults: {error}",
    ),
    "log.collect_unavailable": ("[g1-acq] SKU 采集不可用", "[g1-acq] SKU collection unavailable"),
    "log.rewrite_unavailable": ("[g1-acq] 改写不可用: {error}", "[g1-acq] rewrite unavailable: {error}"),
    "log.record_unavailable": ("[g1-acq] 本地记录不可用", "[g1-acq] local record unavailable"),
    "log.record_write_failed": ("[g1-acq] 本地记录写入失败", "[g1-acq] local record write failed"),
    "log.report_failed": ("[g1-sku-report] 报告生成失败: {error}",
                          "[g1-sku-report] report failed: {error}"),
    "log.ready": (
        "[g1-acq] {version} 就绪: target={target} state={state}",
        "[g1-acq] {version} ready: target={target} state={state}",
    ),

    # ---------------------------------------------------------------- console
    "ui.title": ("G1 ACQ 安装控制台", "G1 ACQ setup console"),
    "ui.subtitle": ("这里的东西都由这台机器实时生成，不需要手改配置。",
                    "Everything here is generated live on this machine; no hand-editing."),
    "ui.step1": ("第一步 · 安装证书", "Step 1 · Install the certificate"),
    "ui.step1.body": (
        "手机需要信任这张证书，旁路才能读到 one.google.com 的响应。下载后到 "
        "<b>设置 → 通用 → VPN 与设备管理</b> 安装，再到 "
        "<b>设置 → 通用 → 关于本机 → 证书信任设置</b> 打开完全信任。",
        "The phone must trust this certificate before the sidecar can read one.google.com "
        "responses. Download it, install it from <b>Settings → General → VPN &amp; "
        "Device Management</b>, then enable full trust under <b>Settings → General → "
        "About → Certificate Trust Settings</b>.",
    ),
    "ui.download_profile": ("下载证书（.mobileconfig）", "Download certificate (.mobileconfig)"),
    "ui.download_cer": ("下载 .cer", "Download .cer"),
    "ui.fingerprint": ("证书 SHA-256：", "Certificate SHA-256: "),
    "ui.step2": ("第二步 · 导入 Clash 配置", "Step 2 · Import the Clash profile"),
    "ui.step2.body": ("旁路地址已经写进配置：", "The sidecar address is already in the profile: "),
    "ui.g1_only": ("只做 G1（其它直连）", "G1 only (everything else direct)"),
    "ui.g1_only.note": ("适合先在手机上把链路走通，不需要任何机场节点。",
                        "Good for getting the path working first; needs no proxy nodes."),
    "ui.sub_placeholder": (
        "可选：粘贴你的机场订阅链接，生成带节点的完整配置",
        "Optional: paste your subscription URL to get a profile with your own nodes",
    ),
    "ui.sub_button": ("生成带订阅的配置", "Generate with subscription"),
    "ui.step2.hint": (
        "订阅链接只在这台机器上使用，不会上传。生成的配置可以直接用 Clash "
        "「从 URL 导入」——把下面的地址复制过去，或者用手机扫二维码。",
        "The subscription URL is only used on this machine and is never uploaded. "
        "Import the generated profile with Clash's \"from URL\" — copy the address "
        "below or scan the QR code.",
    ),
    "ui.step3": ("第三步 · 看状态", "Step 3 · Status"),
    "ui.footer": (
        "这个页面只在你自己的局域网内可访问。用完可以关掉：<code>serve --console 0</code>。",
        "This page is only reachable on your own LAN. Turn it off with "
        "<code>serve --console 0</code>.",
    ),
    "ui.loading": ("读取中…", "loading…"),
    "ui.kv.server": ("旁路", "sidecar"),
    "ui.kv.address": ("本机地址", "LAN address"),
    "ui.kv.clients": ("手机连过", "phone connected"),
    "ui.kv.clients.never": ("还没有", "not yet"),
    "ui.kv.clients.times": ("{count} 次连接", "{count} connections"),
    "ui.kv.scanned": ("已扫描响应", "responses scanned"),
    "ui.kv.candidates": ("采集到的编号", "product IDs collected"),
    "ui.kv.last": ("最近改写", "last rewrite"),
    "ui.kv.last.none": ("还没有", "none yet"),
    "ui.kv.last.at": ("最近改写时间", "last rewrite at"),
    "ui.hint.none": (
        "还没有手机连过来。确认手机和这台机器在同一个 Wi-Fi，"
        "并且 Clash 已导入上面的配置并连接。",
        "No phone has connected yet. Check that the phone is on the same Wi-Fi and that "
        "Clash has imported the profile above and is connected.",
    ),
    "ui.hint.connected": (
        "手机已经连上，但还没抓到 one.google.com 的改写请求。打开 Google One 点一个方案试试。",
        "The phone is connected but no one.google.com rewrite has been seen. Open Google "
        "One and tap a plan.",
    ),
    "ui.hint.rewritten": (
        "改写已经生效，去看 App Store 弹出的购买面板里的商品和价格。",
        "The rewrite is live — check the product and price in the App Store purchase sheet.",
    ),
    "ui.ca_missing": (
        "证书还没生成：先启动一次服务，mitmproxy 会创建它。",
        "The certificate does not exist yet — start the sidecar once and mitmproxy "
        "will create it.",
    ),
}


def t(key: str, *, lang: str | None = None, **fields) -> str:
    """Look up ``key`` in ``lang`` (defaults to the current language)."""
    try:
        zh, en = MESSAGES[key]
    except KeyError:  # pragma: no cover - a typo should be loud in tests
        raise KeyError(f"unknown message key: {key}") from None
    template = en if normalize(lang or _current) == "en" else zh
    return template.format(**fields) if fields else template


set_language(os.environ.get("G1_LANG"))
