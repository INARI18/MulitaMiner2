"""Tabular exporters: XLSX and CSV (thin wrappers over writers.py)."""
from __future__ import annotations

from pathlib import Path

from mulitaminer.exporters import register
from mulitaminer.models import VulnRecord
from mulitaminer.writers import write_csv, write_xlsx


@register("xlsx", "MulitaMiner records as a spreadsheet")
def to_xlsx(records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path) -> Path:
    # record_type is part of the Exporter protocol; output columns are the union
    # across scanners (writers.unified_columns), so it is not needed here.
    path = out_dir / "results.xlsx"
    write_xlsx(records, path)
    return path


@register("csv", "MulitaMiner records as CSV")
def to_csv(records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path) -> Path:
    path = out_dir / "results.csv"
    write_csv(records, path)
    return path
