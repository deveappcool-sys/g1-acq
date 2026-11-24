"""Local network discovery.

The Clash profile has to contain the address the phone will dial, and that
address changes whenever the machine joins a different network.  The setup
console therefore asks this module, never the user.
"""

from __future__ import annotations

import socket
import struct
import sys
from typing import Iterator

_PRIVATE_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                     "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")


def is_private_ipv4(address: str) -> bool:
    return address.startswith(_PRIVATE_PREFIXES)


def _interface_addresses() -> Iterator[str]:
    """Yield IPv4 addresses bound to real interfaces (Unix only)."""
    if sys.platform == "win32":  # pragma: no cover - the sidecar targets macOS/Linux
        return
    try:
        import fcntl
    except ImportError:  # pragma: no cover
        return

    for _index, name in socket.if_nameindex():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                packed = fcntl.ioctl(
                    sock.fileno(), 0x8915, struct.pack("256s", name[:15].encode())
                )  # SIOCGIFADDR
        except OSError:
            continue
        yield socket.inet_ntoa(packed[20:24])


def _default_route_address() -> str | None:
    """Address the kernel would use for outbound traffic (no packet sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("203.0.113.1", 9))  # TEST-NET-3, never routed
            return sock.getsockname()[0]
    except OSError:
        return None


def lan_addresses() -> list[str]:
    """Private IPv4 addresses this host can be reached on, best first."""
    found: list[str] = []
    primary = _default_route_address()
    if primary and is_private_ipv4(primary):
        found.append(primary)
    for address in _interface_addresses():
        if is_private_ipv4(address) and address not in found:
            found.append(address)
    return found


def primary_address() -> str | None:
    addresses = lan_addresses()
    return addresses[0] if addresses else None
