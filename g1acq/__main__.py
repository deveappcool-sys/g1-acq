"""Command line entry point.

    python -m g1acq serve                     # start the sidecar (mitmdump)
    python -m g1acq report --state FILE       # JSON export of the local state
    python -m g1acq report --state FILE --html
    python -m g1acq clear  --state FILE       # reset both keys

``serve`` never touches the network itself; it only builds the mitmdump
command line from :mod:`g1acq.launch`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import config, doctor, launch, network
from .report import build_report
from .store import FileStore


def _serve(args: argparse.Namespace) -> int:
    try:
        auth = launch.validate_auth(args.auth)
        # Fail here with a readable message instead of inside mitmdump.
        config.Settings(target=args.target)
    except ValueError as error:
        print(f"[g1-acq] {error}", file=sys.stderr)
        return 2
    if not auth:
        print(
            "[g1-acq] warning: no --auth set; anyone who can reach this port can "
            "use it as a proxy and read or clear the report.\n"
            "[g1-acq]          add --auth user:password (and matching credentials "
            "to the Clash G1-MITM proxy) unless it listens on loopback only.",
            file=sys.stderr,
        )
    options = launch.LaunchOptions(
        port=args.port,
        state=args.state,
        target=args.target,
        upstream=args.upstream,
        bind=args.bind,
        auth=auth,
        console=args.console,
    )
    mitmdump = shutil.which("mitmdump")
    if mitmdump is None:
        # A virtualenv invoked through its interpreter does not put its bin/
        # on PATH, so look next to the running interpreter as well.
        sibling = Path(sys.executable).with_name("mitmdump")
        if sibling.exists():
            mitmdump = str(sibling)
    if mitmdump is None:
        print(
            "mitmdump not found. Install the sidecar dependencies first:\n"
            "  pip install mitmproxy\n"
            "or run this command inside the project virtualenv.",
            file=sys.stderr,
        )
        return 2
    argv = launch.build_argv(options, mitmdump=mitmdump)
    print(f"[g1-acq] state: {launch.state_path(options.state)}", file=sys.stderr)
    print(f"[g1-acq] exec: {launch.describe(argv)}", file=sys.stderr)
    os.execv(mitmdump, argv)
    return 0  # pragma: no cover


def _state_parser(sub: argparse.ArgumentParser, with_target: bool) -> None:
    sub.add_argument(
        "--state",
        default=launch.DEFAULT_STATE,
        help=f"state file path (default: {launch.DEFAULT_STATE})",
    )
    if with_target:
        sub.add_argument(
            "--target",
            default=config.DEFAULT_TARGET,
            help=f"2TB target SKU (default: {config.DEFAULT_TARGET})",
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m g1acq", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="action", required=True)

    serve = sub.add_parser("serve", help="run the mitmproxy sidecar")
    serve.add_argument("--port", type=int, default=launch.DEFAULT_PORT)
    serve.add_argument("--bind", default="", help="listen address (default: all)")
    serve.add_argument(
        "--console",
        type=int,
        default=launch.DEFAULT_CONSOLE_PORT,
        help=f"setup console port, 0 disables it (default: {launch.DEFAULT_CONSOLE_PORT})",
    )
    serve.add_argument(
        "--auth",
        default="",
        help="require proxy authentication (user:password); strongly recommended "
        "when the sidecar is reachable from other devices",
    )
    serve.add_argument(
        "--upstream",
        default="",
        help="chain through an existing proxy, e.g. http://127.0.0.1:7890",
    )
    _state_parser(serve, with_target=True)
    serve.set_defaults(handler=_serve)

    report = sub.add_parser("report", help="print the stored report")
    report.add_argument("--html", action="store_true", help="render HTML instead of JSON")
    _state_parser(report, with_target=True)
    report.set_defaults(handler=_report)

    clear = sub.add_parser("clear", help="clear both local records")
    _state_parser(clear, with_target=False)
    clear.set_defaults(handler=_clear)

    doctor_cmd = sub.add_parser("doctor", help="print a copy-pasteable self-check report")
    doctor_cmd.add_argument("--sidecar-port", type=int, default=launch.DEFAULT_PORT)
    doctor_cmd.add_argument("--console-port", type=int, default=launch.DEFAULT_CONSOLE_PORT)
    doctor_cmd.add_argument("--confdir", default="~/.mitmproxy")
    _state_parser(doctor_cmd, with_target=False)
    doctor_cmd.set_defaults(handler=_doctor)

    url = sub.add_parser("url", help="print the setup console address and a QR code")
    url.add_argument("--console-port", type=int, default=launch.DEFAULT_CONSOLE_PORT)
    url.set_defaults(handler=_url)

    ca = sub.add_parser(
        "ca",
        help="export the mitmproxy root CA in DER form (what iOS/Android installs)",
    )
    ca.add_argument(
        "--confdir",
        default="~/.mitmproxy",
        help="mitmproxy confdir holding mitmproxy-ca-cert.pem (default: ~/.mitmproxy)",
    )
    ca.add_argument(
        "--out",
        default="g1-acq-ca.der",
        help="output file (default: g1-acq-ca.der)",
    )
    ca.set_defaults(handler=_ca)
    return parser


def _load(args: argparse.Namespace) -> tuple[FileStore, str]:
    path = os.path.abspath(os.path.expanduser(args.state))
    if not os.path.exists(path):
        print(f"[g1-acq] no state file yet at {path}", file=sys.stderr)
    return FileStore(path), path


def _report(args: argparse.Namespace) -> int:
    store, _ = _load(args)
    url = config.REPORT_ROOT + ("" if args.html else "?format=json")
    try:
        response = build_report(store, url, settings=config.Settings(target=args.target))
    except ValueError as error:
        print(f"invalid target: {error}", file=sys.stderr)
        return 2
    print(response.body)
    return 0


def _clear(args: argparse.Namespace) -> int:
    store, path = _load(args)
    if not os.path.exists(path):
        print("没有可清理的记录。")
        return 0
    response = build_report(store, config.REPORT_ROOT + "?clear=1")
    print(response.body.split("<p>")[1].split("</p>")[0] if "<p>" in response.body else "cleared")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    checks = doctor.collect(
        state_path=args.state,
        sidecar_port=args.sidecar_port,
        console_port=args.console_port,
        confdir=args.confdir,
    )
    print(doctor.render(checks, state_path=args.state))
    return 0 if not any(c.status == doctor.BAD for c in checks) else 1


def _url(args: argparse.Namespace) -> int:
    address = network.primary_address()
    if not address:
        print("没检测到局域网地址：这台机器现在没有连上任何网络？", file=sys.stderr)
        return 2
    url = f"http://{address}:{args.console_port}/"
    print(url)
    try:
        import segno

        segno.make(url, error="m").terminal(compact=True)
    except Exception:  # QR is a convenience, never a requirement
        pass
    return 0


def _ca(args: argparse.Namespace) -> int:
    source = Path(os.path.expanduser(args.confdir)) / "mitmproxy-ca-cert.pem"
    if not source.exists():
        print(
            f"CA not found at {source}. Start the sidecar once; mitmproxy creates "
            "the CA on first run.",
            file=sys.stderr,
        )
        return 2
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
    except ImportError:  # pragma: no cover - mitmproxy always ships it
        print("cryptography is required; install mitmproxy first", file=sys.stderr)
        return 2
    certificate = x509.load_pem_x509_certificate(source.read_bytes())
    der = certificate.public_bytes(serialization.Encoding.DER)
    target = Path(os.path.expanduser(args.out))
    target.write_bytes(der)
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
    pretty = ":".join(fingerprint[i : i + 2] for i in range(0, len(fingerprint), 2))
    print(f"wrote {target} ({len(der)} bytes)")
    print(f"SHA-256 {pretty.upper()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
