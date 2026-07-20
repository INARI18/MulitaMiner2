"""Golden parity: compare a v1 extraction JSON with a v2 results.json.

Usage:
    uv run python tools/compare_v1_v2.py <v1.json> <v2_results.json> [--baseline <gt.xlsx>]

Reports record counts, normalized-name overlap, and (with a ground-truth
baseline XLSX) how close each run's raw count is to the truth.
"""
import argparse
import json
import re
from pathlib import Path


def normalize(name: str | None) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def load_names(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):  # tolerate {"vulnerabilities": [...]} wrappers
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
    return [normalize(r.get("Name") or r.get("name")) for r in data]


def baseline_count(path: Path) -> int:
    import pandas as pd

    df = pd.read_excel(path)
    return len(df)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("v1_json", type=Path)
    ap.add_argument("v2_json", type=Path)
    ap.add_argument("--baseline", type=Path, default=None)
    args = ap.parse_args()

    v1 = load_names(args.v1_json)
    v2 = load_names(args.v2_json)
    s1, s2 = set(v1), set(v2)
    overlap = s1 & s2

    print(f"v1 records: {len(v1)}  (unique names: {len(s1)})")
    print(f"v2 records: {len(v2)}  (unique names: {len(s2)})")
    print(f"name overlap: {len(overlap)} "
          f"({100 * len(overlap) / max(1, len(s1 | s2)):.0f}% of union)")
    only_v1 = sorted(s1 - s2)
    only_v2 = sorted(s2 - s1)
    if only_v1:
        print(f"\nonly in v1 ({len(only_v1)}):")
        for n in only_v1:
            print(f"  - {n}")
    if only_v2:
        print(f"\nonly in v2 ({len(only_v2)}):")
        for n in only_v2:
            print(f"  - {n}")

    if args.baseline:
        truth = baseline_count(args.baseline)
        print(f"\nground truth rows: {truth}")
        print(f"count distance from truth: v1={abs(len(v1) - truth)}  "
              f"v2={abs(len(v2) - truth)}")


if __name__ == "__main__":
    main()
