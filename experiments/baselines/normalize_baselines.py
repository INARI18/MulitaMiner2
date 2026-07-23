"""Normalize baseline XLSX *typing/format* without changing their content.

The hand-curated baselines drifted apart in shape: different column order per
report, `references` sometimes a repr'd list and sometimes a newline block,
severity in mixed case. All three are formatting, not content. This rewrites
each baseline to one canonical shape:

    * columns in the record-model order (extra, non-record columns kept, appended)
    * severity upper-cased to its tier
    * references as a repr'd list (blank when empty)

Every rewrite is guarded: it re-reads the written file and asserts, per record
field, that the evaluator would see identical content (references compared by
canonical id-set, severity case-insensitively, everything else by rendered
text). A file that would change content is left untouched and reported.

Usage:
    uv run python experiments/baselines/normalize_baselines.py [resources_dir]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

from _baseline_schema import (
    SOURCE_BY_DIR,
    as_reference_list,
    canonical_columns,
    normalize_severity,
    reference_cell,
)
from mulitaminer.evaluation.runner import _parse_cell
from mulitaminer.evaluation.scorers import _canonical_ids, render_text
from mulitaminer.models import record_type_for_source


def _record_fields(source: str) -> list[str]:
    rt = record_type_for_source(source)
    return ["Name" if n == "name" else n for n in rt.model_fields]


def _ref_ids(value) -> set[str]:
    return {i for item in as_reference_list(_parse_cell(value)) for i in _canonical_ids(item)}


# Vestigial, always-empty columns from an older schema; dropped on normalize.
# Kept as an explicit denylist (not a blanket "drop everything off-record"),
# because some off-record columns, e.g. Tenable's detection_* fields, carry
# real content the current record type just does not declare.
_DROP_COLUMNS = {"http_info", "identification"}


def _reorder(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df = df.drop(columns=[c for c in _DROP_COLUMNS if c in df.columns])
    canon = canonical_columns(source)
    extras = [c for c in df.columns if c not in canon]
    for col in canon:
        if col not in df.columns:
            df[col] = source if col == "source" else None
    return df[canon + extras]


def _normalized(df: pd.DataFrame, source: str) -> pd.DataFrame:
    out = _reorder(df.copy(), source)
    out["severity"] = out["severity"].map(normalize_severity)
    out["references"] = out["references"].map(
        lambda v: reference_cell(as_reference_list(_parse_cell(v)))
    )
    return out


def _content_equal(old: pd.DataFrame, new: pd.DataFrame, source: str) -> list[str]:
    """Per record field, list the fields whose evaluator-visible content changed."""
    diffs: list[str] = []
    fields = [f for f in _record_fields(source) if f in old.columns or f in new.columns]
    for field in fields:
        for i in range(len(old)):
            a = _parse_cell(old[field].iloc[i]) if field in old.columns else None
            b = _parse_cell(new[field].iloc[i]) if field in new.columns else None
            if field == "severity":
                same = render_text(a).lower() == render_text(b).lower()
            elif field == "references":
                same = _ref_ids(old[field].iloc[i] if field in old.columns else None) == \
                    _ref_ids(new[field].iloc[i] if field in new.columns else None)
            else:
                same = render_text(a) == render_text(b)
            if not same:
                diffs.append(f"{field}[row {i}]")
                break
    return diffs


def normalize_file(path: Path, source: str) -> None:
    original = pd.read_excel(path)
    new = _normalized(original, source)

    tmp = path.with_suffix(".normalized.tmp.xlsx")
    new.to_excel(tmp, index=False)
    written = pd.read_excel(tmp)

    diffs = _content_equal(original, written, source)
    if diffs:
        tmp.unlink()
        print(f"SKIP  {path.name}: content would change -> {diffs[:5]}")
        return

    os.replace(tmp, path)
    added = [c for c in new.columns if c not in original.columns]
    note = f" (+cols {added})" if added else ""
    print(f"OK    {path.name}: {len(new)} rows, {len(new.columns)} cols{note}")


def main(argv: list[str]) -> None:
    root = Path(argv[0]) if argv else Path("resources")
    files = [
        (p, SOURCE_BY_DIR[d])
        for d in SOURCE_BY_DIR
        for p in sorted((root / d).glob("*.xlsx"))
    ]
    if not files:
        sys.exit(f"no baseline XLSX under {root}/{{{','.join(SOURCE_BY_DIR)}}}")
    for path, source in files:
        normalize_file(path, source)


if __name__ == "__main__":
    main(sys.argv[1:])
