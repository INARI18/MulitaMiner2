"""Trim baseline text the paired PDF never renders.

Exports/hand-made baselines can carry paragraphs the PDF layout omits; scoring
against them caps every extractor below 1.0 for content it never saw. For each
resources/<scanner>/<stem>.xlsx with a sibling PDF: segment the PDF, pair rows
to blocks by name-token containment, and drop from the text columns any
paragraph/element whose tokens are not >=0.80 contained in its block. Cells
keep their original format (plain string or list repr). Unmatched rows are
left untouched.

  uv run python tools/trim_baselines.py [--dry-run]
"""
from __future__ import annotations

import argparse
import ast
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from mulitaminer.pdf_reader import extract_pdf
from mulitaminer.scanner_engine import get_scanner

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
TEXT_COLS = ["description", "solution", "impact", "insight", "detection_result",
             "detection_method", "product_detection_result", "log_method"]
CMIN = 0.80
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(value) -> Counter:
    return Counter(_TOKEN_RE.findall(str(value).lower()))


def containment(needle: Counter, hay: Counter) -> float:
    total = sum(needle.values())
    return sum((needle & hay).values()) / total if total else 1.0


def trim_cell(cell, block_tokens: Counter):
    """Returns (new_cell, n_removed); preserves the cell's format."""
    if not isinstance(cell, str) or not cell.strip():
        return cell, 0
    if cell.lstrip().startswith("["):
        try:
            items = ast.literal_eval(cell)
        except (ValueError, SyntaxError):
            return cell, 0
        kept = [p for p in items if containment(tokens(p), block_tokens) >= CMIN]
        if len(kept) == len(items):
            return cell, 0
        return (str(kept) if kept else ""), len(items) - len(kept)
    paras = [p for p in re.split(r"\n\s*\n", cell) if p.strip()]
    kept = [p for p in paras if containment(tokens(p), block_tokens) >= CMIN]
    if len(kept) == len(paras):
        return cell, 0
    return ("\n\n".join(kept) if kept else ""), len(paras) - len(kept)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for xlsx in sorted(RESOURCES.glob("*/*.xlsx")):
        pdf = xlsx.with_suffix(".pdf")
        if not pdf.exists():
            continue
        scanner = xlsx.parent.name
        blocks = get_scanner(scanner).segment(extract_pdf(pdf).text)
        block_tokens = [(b, tokens(b.text)) for b in blocks]

        df = pd.read_excel(xlsx)
        used: dict[int, int] = defaultdict(int)
        trimmed: Counter = Counter()
        unmatched = 0
        for i, row in df.iterrows():
            name_tokens = tokens(row.get("Name"))
            candidates = [(containment(name_tokens, bt), used[b.id], b, bt)
                          for b, bt in block_tokens]
            candidates = [c for c in candidates if c[0] >= CMIN]
            if not candidates:
                unmatched += 1
                continue
            candidates.sort(key=lambda c: (c[1], -c[0]))
            _, _, block, bt = candidates[0]
            used[block.id] += 1
            for col in TEXT_COLS:
                if col not in df.columns:
                    continue
                new, n = trim_cell(row[col], bt)
                if n:
                    df.at[i, col] = new
                    trimmed[col] += n

        status = f"{xlsx.relative_to(RESOURCES)}: {sum(trimmed.values())} trimmed"
        if trimmed:
            status += f" {dict(trimmed)}"
        if unmatched:
            status += f" | {unmatched} rows unmatched (untouched)"
        print(status)
        if trimmed and not args.dry_run:
            df.to_excel(xlsx, index=False)


if __name__ == "__main__":
    main()
