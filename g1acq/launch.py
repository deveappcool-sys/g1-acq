"""Command construction for the sidecar process.

One definition of the mitmdump flags, so ``python -m g1acq serve``, ``run.sh``
and the end-to-end test cannot drift apart.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STATE = "~/.g1-acq/state.json"
DEFAULT_PORT = 8080
# Only this host is decrypted; anything else is tunnelled untouched.
ALLOW_HOSTS = r"^one\.google\.com(:\d+)?$"
ADDON = str(Path(__file__).resolve().parents[1] / "g1_addon.py")


@dataclass
class LaunchOptions:
    port: int = DEFAULT_PORT
    state: str = DEFAULT_STATE
    target: str = ""
    upstream: str = ""
    bind: str = ""
    allow_hosts: str = ALLOW_HOSTS
    addon: str = field(default=ADDON)
    extra: tuple[str, ...] = ()


def state_path(value: str) -> str:
    return os.path.abspath(os.path.expanduser(value or DEFAULT_STATE))


def build_argv(options: LaunchOptions, *, mitmdump: str = "mitmdump") -> list[str]:
    argv = [mitmdump, "-s", options.addon, "-p", str(options.port)]
    if options.bind:
        argv += ["--listen-host", options.bind]
    if options.upstream:
        # Chain through an existing proxy so the sidecar does not need its own
        # route to Google (e.g. a Clash mixed-port on the same machine).
        argv += ["--mode", f"upstream:{options.upstream}"]
    if options.allow_hosts:
        argv += ["--set", f"allow_hosts={options.allow_hosts}"]
    argv += ["--set", f"g1_state={state_path(options.state)}"]
    if options.target:
        argv += ["--set", f"g1_target={options.target}"]
    argv += list(options.extra)
    return argv


def describe(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit("use `python -m g1acq serve` instead")
