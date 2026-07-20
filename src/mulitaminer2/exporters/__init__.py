"""Export seam: `--export <name>` resolves an exporter from this registry.

An exporter is a deterministic mapping from validated VulnRecords to a target
format — never an LLM concern (the OUTPUT_STANDARDS lesson from v1: extraction
and serialization must not mix; CAIS-as-a-prompt was the cautionary tale).

Adding a format: write `to_<fmt>` in a module here, decorate with
@register("<fmt>"), import the module below.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from mulitaminer2.models import VulnRecord


class Exporter(Protocol):
    def __call__(
        self, records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path
    ) -> Path: ...


EXPORTERS: dict[str, Exporter] = {}


def register(name: str) -> Callable[[Exporter], Exporter]:
    def wrap(fn: Exporter) -> Exporter:
        EXPORTERS[name] = fn
        return fn

    return wrap


def get_exporter(name: str) -> Exporter:
    try:
        return EXPORTERS[name.lower()]
    except KeyError:
        raise ValueError(f"Unknown export format '{name}'. Available: {sorted(EXPORTERS)}")


from mulitaminer2.exporters import generic, sarif, tabular  # noqa: E402,F401 — populate registry
