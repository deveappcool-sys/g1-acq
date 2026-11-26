#!/usr/bin/env bash
# 查看本机采集到的档位与折扣（纯本地，不需要网络、不需要手机）
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
exec "$PY" -m g1acq catalog "$@"
