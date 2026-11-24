"""Address detection: the profile must never ship a stale IP."""

from __future__ import annotations

from g1acq import network


def test_private_ranges_are_recognised():
    for address in ("192.168.2.57", "10.0.0.5", "172.16.4.1", "172.31.255.254"):
        assert network.is_private_ipv4(address), address


def test_public_addresses_are_not_private():
    for address in ("8.8.8.8", "1.1.1.1", "172.32.0.1", "203.0.113.9"):
        assert not network.is_private_ipv4(address), address


def test_lan_addresses_are_private_and_deduplicated():
    addresses = network.lan_addresses()
    assert len(addresses) == len(set(addresses))
    assert all(network.is_private_ipv4(a) for a in addresses)


def test_primary_address_matches_first_entry():
    addresses = network.lan_addresses()
    assert network.primary_address() == (addresses[0] if addresses else None)
