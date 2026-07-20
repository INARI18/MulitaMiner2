"""Scanner registry. Adding a scanner = one module + one prompt + one entry here."""
from mulitaminer2.scanners.openvas import PROFILE as OPENVAS
from mulitaminer2.scanners.profile import ScannerProfile
from mulitaminer2.scanners.tenable import PROFILE as TENABLE

SCANNERS: dict[str, ScannerProfile] = {
    OPENVAS.name: OPENVAS,
    TENABLE.name: TENABLE,
}


def get_scanner(name: str) -> ScannerProfile:
    try:
        return SCANNERS[name.lower()]
    except KeyError:
        raise ValueError(f"Unknown scanner '{name}'. Available: {sorted(SCANNERS)}")
