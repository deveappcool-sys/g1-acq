"""Root-CA export shared by the CLI and the setup console.

iOS only offers to *install* a profile when the file arrives as
``application/x-x509-ca-cert``; the same certificate served as
``application/octet-stream`` silently lands in the Files app and the install
prompt never appears.  That single mismatch cost more debugging time than
anything else in this project, so the MIME type and the DER encoding live in
one place.
"""

from __future__ import annotations

import os
import plistlib
import uuid
from pathlib import Path

DEFAULT_CONFDIR = "~/.mitmproxy"
CA_FILENAME = "mitmproxy-ca-cert.pem"

CER_MIME = "application/x-x509-ca-cert"
MOBILECONFIG_MIME = "application/x-apple-aspen-config"


class MissingCertificate(RuntimeError):
    """The sidecar has not run yet, so mitmproxy has not created its CA."""


def confdir(value: str | os.PathLike[str] | None = None) -> Path:
    return Path(os.path.expanduser(str(value) if value else DEFAULT_CONFDIR))


def load_pem(directory: str | os.PathLike[str] | None = None) -> bytes:
    pem = confdir(directory) / CA_FILENAME
    if not pem.exists():
        raise MissingCertificate(
            f"{pem} not found; start the sidecar once so mitmproxy creates its CA"
        )
    return pem.read_bytes()


def der_bytes(directory: str | os.PathLike[str] | None = None) -> bytes:
    """The certificate in DER form, which every iOS/Android installer accepts."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    certificate = x509.load_pem_x509_certificate(load_pem(directory))
    return certificate.public_bytes(serialization.Encoding.DER)


def fingerprint(directory: str | os.PathLike[str] | None = None) -> str:
    """SHA-256 of the CA certificate, so a user can compare it on the phone."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    certificate = x509.load_pem_x509_certificate(load_pem(directory))
    digest = certificate.fingerprint(hashes.SHA256()).hex()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2)).upper()


def mobileconfig(directory: str | os.PathLike[str] | None = None) -> bytes:
    """A configuration profile wrapping the CA.

    Some iOS builds refuse a bare ``.cer`` but always accept a profile, so this
    is the fallback the console offers.
    """
    certificate = der_bytes(directory)
    profile = {
        "PayloadContent": [
            {
                "PayloadCertificateFileName": "g1-acq-ca.cer",
                "PayloadContent": certificate,
                "PayloadDescription": "G1 ACQ sidecar root certificate",
                "PayloadDisplayName": "G1 ACQ Root CA",
                "PayloadIdentifier": "com.g1acq.ca.root",
                "PayloadType": "com.apple.security.root",
                "PayloadUUID": str(uuid.uuid4()).upper(),
                "PayloadVersion": 1,
            }
        ],
        "PayloadDisplayName": "G1 ACQ Root CA",
        "PayloadDescription": "Lets the G1 ACQ sidecar read and rewrite one.google.com",
        "PayloadIdentifier": "com.g1acq.profile",
        "PayloadOrganization": "g1-acq",
        "PayloadType": "Configuration",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1,
    }
    return plistlib.dumps(profile)
