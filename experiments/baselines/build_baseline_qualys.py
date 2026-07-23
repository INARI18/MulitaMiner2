"""Build the Qualys ground-truth baseline XLSX from a Qualys CSV report export.

The tool consumes baselines; it does not produce them. This derives the Qualys
baseline deterministically from the scanner's own CSV export, so its provenance
is "the Qualys CSV export via this script" instead of hand curation.

Usage:
    uv run python experiments/baselines/build_baseline_qualys.py <report.csv> <out.xlsx>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

from _baseline_schema import canonical_columns, reference_cell

SOURCE = "QUALYS"

# Qualys numeric severity (1-5) -> the record's severity tier. The tier is a
# pure function of the number (Vuln/Practice/Ig `Type` does not change it).
_SEVERITY = {"1": "INFO", "2": "LOW", "3": "MEDIUM", "4": "HIGH", "5": "CRITICAL"}


def _find_table(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    """Locate the vuln table (its header row starts with IP,DNS)."""
    for i, r in enumerate(rows):
        if r[:2] == ["IP", "DNS"]:
            return i, {h: j for j, h in enumerate(r)}
    raise ValueError("no 'IP','DNS' header row found; not a Qualys CSV export")


def _int_or_none(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def build(csv_path: Path) -> pd.DataFrame:
    with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f))
    start, col = _find_table(rows)

    def cell(r: list[str], name: str) -> str:
        # Normalize the CSV's embedded CRLF line endings to LF.
        return r[col[name]].replace("\r\n", "\n").replace("\r", "\n").strip()

    def body(r: list[str], name: str) -> str | None:
        v = cell(r, name)
        return None if v in ("", "N/A", "N/A.") else v

    records = []
    for r in rows[start + 1:]:
        if len(r) <= max(col.values()) or not cell(r, "QID"):
            continue
        cves = [c.strip() for c in cell(r, "CVE ID").split(",") if c.strip()]
        records.append(
            {
                "Name": cell(r, "Title"),
                "description": body(r, "Threat"),
                "solution": body(r, "Solution"),
                "impact": body(r, "Impact"),
                "references": reference_cell(cves),
                "severity": _SEVERITY.get(cell(r, "Severity"), cell(r, "Severity")),
                "host": cell(r, "IP") or None,
                "port": _int_or_none(cell(r, "Port")),
                "protocol": cell(r, "Protocol") or None,
                "source": SOURCE,
                "category": cell(r, "Category") or None,
                "plugin": _int_or_none(cell(r, "QID")),
            }
        )
    return pd.DataFrame(records, columns=canonical_columns(SOURCE))


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        sys.exit("usage: build_baseline_qualys.py <report.csv> <out.xlsx>")
    df = build(Path(argv[0]))
    df.to_excel(Path(argv[1]), index=False)
    print(f"wrote {argv[1]} ({len(df)} rows)")


if __name__ == "__main__":
    main(sys.argv[1:])
