"""G1 ACQ — Google One SKU rewrite sidecar for Clash / mihomo.

Clash decides *where* ``one.google.com`` goes; this package is the component
that terminates that TLS session, applies the three-tier SKU mapping, keeps the
passive SKU inventory and serves the local report.
"""

from .config import COLLECTOR_VERSION, PROJECT_VERSION, REPORT_VERSION

__version__ = PROJECT_VERSION

__all__ = ["COLLECTOR_VERSION", "PROJECT_VERSION", "REPORT_VERSION", "__version__"]
