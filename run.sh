#!/usr/bin/env bash
# Start the G1 ACQ sidecar.
#
#   ./run.sh                                     # listen on 0.0.0.0:8080
#   G1_AUTH=g1:change-me ./run.sh                # require proxy credentials
#   G1_PORT=9090 ./run.sh                        # different port
#   G1_UPSTREAM=http://127.0.0.1:7890 ./run.sh   # reuse a local Clash node
#
# Environment:
#   G1_PORT      listen port                    (default 8080)
#   G1_BIND      listen address                 (default: all interfaces)
#   G1_STATE     state file                     (default ~/.g1-acq/state.json)
#   G1_TARGET    override the 2TB target SKU    (default from g1acq/config.py)
#   G1_AUTH      user:password for proxy auth   (recommended off-loopback)
#   G1_UPSTREAM  upstream proxy to chain through (optional, see the warning)
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python3
fi

args=(serve --port "${G1_PORT:-8080}")
if [[ -n "${G1_BIND:-}" ]]; then
  args+=(--bind "$G1_BIND")
fi
if [[ -n "${G1_UPSTREAM:-}" ]]; then
  args+=(--upstream "$G1_UPSTREAM")
  cat >&2 <<'WARN'
[g1-acq] note: the upstream must NOT route one.google.com back here, or the
[g1-acq]       two proxies will forward the request to each other in a loop.
[g1-acq]       If you point this at a local Clash, give that profile
[g1-acq]       `DOMAIN,one.google.com,DIRECT` (or use a separate profile).
WARN
fi
if [[ -n "${G1_TARGET:-}" ]]; then
  args+=(--target "$G1_TARGET")
fi
if [[ -n "${G1_AUTH:-}" ]]; then
  args+=(--auth "$G1_AUTH")
fi

exec "$PYTHON" -m g1acq "${args[@]}" --state "${G1_STATE:-$HOME/.g1-acq/state.json}"
