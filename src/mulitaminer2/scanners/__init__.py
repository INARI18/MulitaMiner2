"""Scanner registry, loaded from JSON configs (see engine.py for the format).

Built-in scanners live in `scanners/configs/`. Users plug new scanners with no
Python: drop `<name>.json` + its prompt into a directory and point the
MULITAMINER2_SCANNERS_DIR env var at it (same-name configs override built-ins).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from mulitaminer2.scanners.engine import load_profile
from mulitaminer2.scanners.profile import ScannerProfile

_BUILTIN_DIR = Path(__file__).parent / "configs"


@lru_cache
def _registry(extra_dir: str | None) -> dict[str, ScannerProfile]:
    profiles: dict[str, ScannerProfile] = {}
    dirs = [_BUILTIN_DIR] + ([Path(extra_dir)] if extra_dir else [])
    for directory in dirs:
        for config in sorted(directory.glob("*.json")):
            profile = load_profile(config)
            profiles[profile.name] = profile
    return profiles


def all_scanners() -> dict[str, ScannerProfile]:
    return _registry(os.getenv("MULITAMINER2_SCANNERS_DIR"))


def get_scanner(name: str) -> ScannerProfile:
    scanners = all_scanners()
    try:
        return scanners[name.lower()]
    except KeyError:
        raise ValueError(f"Unknown scanner '{name}'. Available: {sorted(scanners)}")
