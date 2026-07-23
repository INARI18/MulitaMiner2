"""Build an OpenVAS/Greenbone ground-truth baseline XLSX from a CSV report export.

The tool consumes baselines; it does not produce them. This derives the OpenVAS
baseline deterministically from the scanner's own CSV export, so its provenance
is "the Greenbone CSV export via this script" instead of hand curation.

One row per unique (NVT, host, port, protocol) finding-instance.

Usage:
    uv run python experiments/baselines/build_baseline_openvas.py <report.csv> <out.xlsx>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

from _baseline_schema import canonical_columns, reference_cell

SOURCE = "OPENVAS"


def _clean(v: str) -> str | None:
    v = (v or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return v or None


def _int_or_none(raw: str) -> int | str | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def _float_or_none(raw: str) -> float | None:
    try:
        return float((raw or "").strip())
    except ValueError:
        return None


def _references(row: dict) -> list[str]:
    """OpenVAS reference columns -> one flat id list (CVEs, BIDs, CERTs, URLs)."""
    refs: list[str] = []
    refs += [c.strip() for c in row.get("CVEs", "").split(",") if c.strip()]
    for bid in (b.strip() for b in row.get("BIDs", "").split(",") if b.strip()):
        refs.append(f"BID:{bid}" if bid.isdigit() else bid)
    refs += [c.strip() for c in row.get("CERTs", "").split(",") if c.strip()]
    refs += [r.strip() for r in row.get("Other References", "").split(",") if r.strip()]
    return refs


def build(csv_path: Path) -> pd.DataFrame:
    with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    records = []
    seen: set[tuple] = set()
    for row in rows:
        key = (row["NVT Name"], row["IP"], row["Port"], row["Port Protocol"])
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "Name": _clean(row["NVT Name"]),
                "description": _clean(row["Summary"]),
                "solution": _clean(row["Solution"]),
                "impact": _clean(row["Impact"]),
                "references": reference_cell(_references(row)),
                "severity": (row["Severity"] or "").strip().upper() or None,
                "host": _clean(row["IP"]),
                "port": _int_or_none(row["Port"]),
                "protocol": _clean(row["Port Protocol"]),
                "source": SOURCE,
                "cvss": _float_or_none(row["CVSS"]),
                "insight": _clean(row["Vulnerability Insight"]),
                "detection_result": _clean(row["Specific Result"]),
                "detection_method": _clean(row["Vulnerability Detection Method"]),
                "product_detection_result": _clean(row["Product Detection Result"]),
                "log_method": None,  # not a separate column in the CSV export
            }
        )
    return pd.DataFrame(records, columns=canonical_columns(SOURCE))


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        sys.exit("usage: build_baseline_openvas.py <report.csv> <out.xlsx>")
    df = build(Path(argv[0]))
    df.to_excel(Path(argv[1]), index=False)
    print(f"wrote {argv[1]} ({len(df)} rows)")


if __name__ == "__main__":
    main(sys.argv[1:])
