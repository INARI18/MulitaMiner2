"""Extraction-to-baseline record alignment (Hungarian assignment).

Similarity per (extraction, baseline) cell = max(composite-key score, fuzzy
normalized-name score); the globally optimal assignment is solved with
``scipy.optimize.linear_sum_assignment`` and cut at a threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from mulitaminer.consolidate import normalize_name

# Minimum similarity to accept an assignment.
FUZZY_THRESHOLD = 0.7

# When composite keys CONFLICT (a concrete part differs on both sides, e.g. the
# same finding name on two different ports), the name-only similarity is scaled
# down so the assignment prefers the composite-compatible pairing. Without this,
# identical names tie at 1.0 and the assignment is arbitrary.
KEY_CONFLICT_PENALTY = 0.9

# The composite key is the finding name plus a scanner's ``evaluation.key_parts``
# (see ScannerProfile.key_parts); align() takes those parts as a parameter.


def _get(row: dict, name: str) -> Any:
    """Field access tolerating the Name/name alias split."""
    if name in row:
        return row[name]
    if name.lower() == "name":
        return row.get("Name" if name == "name" else "name")
    return None


def _normalize_part(name: str, value: Any) -> str:
    """One composite-key part; '*' is the wildcard for absent values.

    Float guard: pandas coerces int columns to float64 as soon as a null
    appears, so port 8019 arrives as 8019.0; stripping the dot naively would
    produce "80190" and silently break every key. Collapse integer-valued
    floats first.
    """
    if isinstance(value, float):
        if value != value:  # NaN
            return "*"
        if value.is_integer():
            value = int(value)
    s = str(value).strip().lower() if value is not None else ""
    if not s or s in ("nan", "none"):
        return "*"
    if name == "port":
        s = s.replace(",", "").replace(".", "")
        if not s.isdigit() and s != "general":
            return "*"
    return s


def composite_key(row: dict, key_parts: tuple[str, ...]) -> str:
    """``<name>|<part>|...`` over the normalized name plus each key part."""
    name = normalize_name(str(_get(row, "Name") or ""))
    return "|".join([name, *(_normalize_part(p, _get(row, p)) for p in key_parts)])


def keys_match(key1: str, key2: str) -> bool:
    parts1, parts2 = key1.split("|"), key2.split("|")
    if len(parts1) != len(parts2):
        return False
    return all(a == "*" or b == "*" or a == b for a, b in zip(parts1, parts2))


def key_match_score(key1: str, key2: str) -> float:
    """Concrete equal parts score 1.0, wildcard positions 0.3."""
    parts1, parts2 = key1.split("|"), key2.split("|")
    if len(parts1) != len(parts2) or not parts1:
        return 0.0
    score = 0.0
    for a, b in zip(parts1, parts2):
        if a == "*" or b == "*":
            score += 0.3
        elif a == b:
            score += 1.0
    return score / len(parts1)


def cell_score(ek: str, en: str, bk: str, bn: str) -> float:
    """One similarity-matrix cell: composite-key score, else penalized name."""
    name_sim = (fuzz.ratio(en, bn) / 100.0) if en and bn else 0.0
    if keys_match(ek, bk):
        return max(key_match_score(ek, bk), name_sim)
    return name_sim * KEY_CONFLICT_PENALTY


@dataclass
class AlignmentResult:
    pairs: list[tuple[int, int]]  # (extraction_index, baseline_index)
    unmatched_extraction: list[int]  # false-positive findings
    unmatched_baseline: list[int]  # false-negative findings
    debug_rows: list[dict]


def align(
    ext_rows: list[dict],
    base_rows: list[dict],
    key_parts: tuple[str, ...] = (),
    threshold: float = FUZZY_THRESHOLD,
) -> AlignmentResult:
    ext_names = [normalize_name(str(_get(r, "Name") or "")) for r in ext_rows]
    base_names = [normalize_name(str(_get(r, "Name") or "")) for r in base_rows]

    if not ext_rows or not base_rows:
        return AlignmentResult(
            pairs=[],
            unmatched_extraction=list(range(len(ext_rows))),
            unmatched_baseline=list(range(len(base_rows))),
            debug_rows=[
                _debug(i, ext_names[i], None, None, 0.0, "UNMATCHED")
                for i in range(len(ext_rows))
            ],
        )

    ext_keys = [composite_key(r, key_parts) for r in ext_rows]
    base_keys = [composite_key(r, key_parts) for r in base_rows]

    sim = [
        [cell_score(ek, en, bk, bn) for bk, bn in zip(base_keys, base_names)]
        for ek, en in zip(ext_keys, ext_names)
    ]

    cost = [[1.0 - cell for cell in row] for row in sim]
    row_ind, col_ind = linear_sum_assignment(cost)

    pairs: list[tuple[int, int]] = []
    debug_rows: list[dict] = []
    matched_ext: set[int] = set()
    matched_base: set[int] = set()

    for i, j in zip(row_ind, col_ind):
        score = sim[i][j]
        if score < threshold:
            continue
        pairs.append((int(i), int(j)))
        matched_ext.add(int(i))
        matched_base.add(int(j))
        debug_rows.append(
            _debug(int(i), ext_names[i], int(j), base_names[j], score, "MATCHED")
        )

    for i in range(len(ext_rows)):
        if i not in matched_ext:
            debug_rows.append(_debug(i, ext_names[i], None, None, 0.0, "UNMATCHED"))

    return AlignmentResult(
        pairs=sorted(pairs, key=lambda p: p[1]),
        unmatched_extraction=[i for i in range(len(ext_rows)) if i not in matched_ext],
        unmatched_baseline=[j for j in range(len(base_rows)) if j not in matched_base],
        debug_rows=debug_rows,
    )


def classify_false_positives(
    ext_rows: list[dict],
    base_rows: list[dict],
    alignment: AlignmentResult,
    key_parts: tuple[str, ...] = (),
) -> list[dict]:
    """Classify each unmatched extraction (a 'false positive'):

    - duplicate: shares its composite key with an already-matched extraction, so
      a finding that IS in the baseline was extracted more than once.
    - invention: any other unmatched extraction, a finding the baseline has no
      counterpart for (relative to the baseline, not a claim it was fabricated).

    ``best_baseline``/``best_similarity`` report the closest baseline row for
    context: a high similarity on an invention flags a name-diverged or extra
    instance worth a human look. They do not drive the category.
    """
    ext_names = [normalize_name(str(_get(r, "Name") or "")) for r in ext_rows]
    base_names = [normalize_name(str(_get(r, "Name") or "")) for r in base_rows]
    ext_keys = [composite_key(r, key_parts) for r in ext_rows]
    base_keys = [composite_key(r, key_parts) for r in base_rows]
    matched_keys = {ext_keys[i] for i, _ in alignment.pairs}

    out: list[dict] = []
    for i in sorted(alignment.unmatched_extraction):
        best, j = max(
            ((cell_score(ext_keys[i], ext_names[i], base_keys[k], base_names[k]), k)
             for k in range(len(base_rows))),
            default=(0.0, None),
        )
        category = "duplicate" if ext_keys[i] in matched_keys else "invention"
        out.append({
            "extraction_index": i,
            "name": str(_get(ext_rows[i], "Name") or ""),
            "category": category,
            "best_baseline": str(_get(base_rows[j], "Name") or "") if j is not None else None,
            "best_similarity": round(best, 4),
        })
    return out


def _debug(
    ext_idx: int,
    ext_name: str,
    base_idx: int | None,
    base_name: str | None,
    score: float,
    status: str,
) -> dict:
    return {
        "extraction_index": ext_idx,
        "extraction_name": ext_name,
        "baseline_index": base_idx,
        "baseline_name": base_name,
        "similarity": round(score, 4),
        "status": status,
    }
