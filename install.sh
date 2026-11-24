#!/usr/bin/env bash
# G1 ACQ · one-command install.
#
#   curl -fsSL https://raw.githubusercontent.com/xulu1998/g1-acq/main/install.sh | bash
#
# or, from a checkout:
#
#   ./install.sh
#
# What it does:
#   1. finds a Python >= 3.12
#   2. creates .venv and installs mitmproxy + segno
#   3. registers a background service (launchd on macOS, systemd on Linux,
#      nohup as a fallback) so the sidecar survives logout and reboots
#   4. prints the setup console address and a QR code for the phone
#
# Environment:
#   G1_REPO       git URL to clone from when run outside a checkout
#   G1_HOME       where to clone / install (default ~/.g1-acq/src)
#   G1_NO_SERVICE 1 = install files only, do not register a service
#   G1_AUTH       user:password, only needed if the sidecar is exposed
set -euo pipefail

G1_REPO="${G1_REPO:-https://github.com/xulu1998/g1-acq.git}"
G1_HOME="${G1_HOME:-$HOME/.g1-acq/src}"
LABEL="com.g1acq.sidecar"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m[!] %s\033[0m\n' "$*" >&2; }
die() { printf '\033[31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. locate
if [[ -f "${BASH_SOURCE[0]:-}" ]]; then
  SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  SELF_DIR=""
fi

if [[ -n "$SELF_DIR" && -f "$SELF_DIR/g1_addon.py" ]]; then
  REPO_DIR="$SELF_DIR"
  say "使用当前目录：$REPO_DIR"
else
  say "没有找到项目代码，克隆到 $G1_HOME"
  command -v git >/dev/null 2>&1 || die "需要 git 才能自动下载项目"
  if [[ -d "$G1_HOME/.git" ]]; then
    git -C "$G1_HOME" pull --ff-only
  else
    mkdir -p "$(dirname "$G1_HOME")"
    git clone --depth 1 "$G1_REPO" "$G1_HOME"
  fi
  REPO_DIR="$G1_HOME"
fi
cd "$REPO_DIR"
[[ -f g1_addon.py ]] || die "目录里没有 g1_addon.py，安装目录不对：$REPO_DIR"

# ---------------------------------------------------------------- 1. python
say "检查 Python"
PYTHON=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      PYTHON="$(command -v "$candidate")"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]] && command -v uv >/dev/null 2>&1; then
  say "本机没有 Python 3.12，用 uv 装一个"
  uv python install 3.12 >/dev/null 2>&1 || true
  PYTHON="$(uv python find 3.12 2>/dev/null || true)"
fi
[[ -n "$PYTHON" ]] || die "需要 Python 3.12 或更新版本（mitmproxy 12 的要求）"
"$PYTHON" -V

# ---------------------------------------------------------------- 2. deps
say "安装依赖（第一次会下载 mitmproxy，约 50 MB）"
if command -v uv >/dev/null 2>&1; then
  uv venv --python "$PYTHON" .venv >/dev/null 2>&1 || true
  uv pip install --python .venv/bin/python -r requirements.txt >/dev/null
else
  [[ -x .venv/bin/python ]] || "$PYTHON" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi
.venv/bin/python -c "import mitmproxy, segno" || die "依赖安装失败"

# ---------------------------------------------------------------- 3. service
install_service() {
  case "$(uname -s)" in
    Darwin)
      local plist="$HOME/Library/LaunchAgents/$LABEL.plist"
      mkdir -p "$(dirname "$plist")" "$HOME/Library/Logs"
      cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$REPO_DIR/.venv/bin/python</string>
    <string>-m</string><string>g1acq</string><string>serve</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO_DIR</string>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/g1-acq.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/g1-acq.log</string>
</dict>
</plist>
PLIST
      # bootout 之后 launchd 需要一点时间释放这个 label，立刻 bootstrap
      # 会返回 EIO（5）；重试几次即可，重试期间服务仍是可用的旧进程。
      launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
      local ok=0
      for _ in 1 2 3 4 5 6; do
        sleep 1
        if launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null; then ok=1; break; fi
      done
      if [[ "$ok" != "1" ]]; then
        warn "launchctl 注册失败，先用 nohup 起一个进程；请稍后重跑 ./install.sh"
        PYTHONUNBUFFERED=1 nohup "$REPO_DIR/.venv/bin/python" -m g1acq serve \
          >> "$HOME/Library/Logs/g1-acq.log" 2>&1 &
      fi
      echo "    launchd: $plist"
      echo "    日志:    tail -f ~/Library/Logs/g1-acq.log"
      ;;
    Linux)
      local unit="$HOME/.config/systemd/user/g1-acq.service"
      mkdir -p "$(dirname "$unit")"
      cat > "$unit" <<UNIT
[Unit]
Description=G1 ACQ sidecar
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$REPO_DIR/.venv/bin/python -m g1acq serve
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
      if command -v systemctl >/dev/null 2>&1; then
        systemctl --user daemon-reload
        systemctl --user enable --now g1-acq.service
        echo "    systemd: $unit"
        echo "    日志:    journalctl --user -u g1-acq -f"
      else
        warn "没有 systemd，用 nohup 启动（重启后需要手动再跑一次）"
        pkill -f "g1_addon.py" 2>/dev/null || true
        PYTHONUNBUFFERED=1 nohup "$REPO_DIR/.venv/bin/python" -m g1acq serve \
          >> "$HOME/.g1-acq/sidecar.log" 2>&1 &
      fi
      ;;
    *)
      warn "未识别的系统：只安装文件，不注册服务"
      ;;
  esac
}

if [[ "${G1_NO_SERVICE:-0}" == "1" ]]; then
  say "跳过服务注册（G1_NO_SERVICE=1）"
else
  say "注册后台服务（开机自启，崩溃自动重启）"
  pkill -f "g1_addon.py" 2>/dev/null || true
  install_service
  sleep 4
fi

# ---------------------------------------------------------------- 4. verify
say "自检"
.venv/bin/python -m g1acq doctor --state "${HOME}/.g1-acq/state.json" || true

say "下一步：手机连同一个 Wi-Fi，扫下面的码"
if ! .venv/bin/python -m g1acq url; then
  warn "没能检测到局域网地址；手动打开 http://<这台机器的IP>:8090/"
fi

cat <<'DONE'

  手机上按这个顺序做（顺序很重要，证书没装好之前不要先连 Clash）：

    1. 打开上面的控制台地址（或扫码）
    2. 点「下载证书」→ 安装描述文件 → 到
       设置 → 通用 → 关于本机 → 证书信任设置 打开「完全信任」
    3. 回控制台，把 Clash 配置地址复制到 Clash「从 URL 导入」
       （页面上也有二维码；不填订阅就是「只做 G1」的版本）
    4. Clash 选中该配置并连接
    5. 打开 Google One → 点一个方案 → 看 App Store 弹窗里的价格

  控制台上「最近改写」出现数字，就说明改写生效了。

  出问题先跑：.venv/bin/python -m g1acq doctor
DONE
