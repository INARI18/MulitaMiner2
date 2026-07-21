"""Export seam: `--export <name>` resolves a deterministic exporter from this
registry. Adding a format: write `to_<fmt>` in a module here, decorate with
@register("<fmt>"), import the module below."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from mulitaminer.models import VulnRecord


class Exporter(Protocol):
    def __call__(
        self, records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path
    ) -> Path: ...


EXPORTERS: dict[str, Exporter] = {}
DESCRIPTIONS: dict[str, str] = {}


def register(name: str, description: str = "") -> Callable[[Exporter], Exporter]:
    def wrap(fn: Exporter) -> Exporter:
        EXPORTERS[name] = fn
        DESCRIPTIONS[name] = description
        return fn

    return wrap


def get_exporter(name: str) -> Exporter:
    try:
        return EXPORTERS[name.lower()]
    except KeyError:
        raise ValueError(f"Unknown export format '{name}'. Available: {sorted(EXPORTERS)}")


from mulitaminer.exporters import cais, csaf, generic, sarif, tabular  # noqa: E402,F401 — populate registry
