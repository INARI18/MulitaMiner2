"""Consolidation: ONE definition of vulnerability identity per scanner.

v1 had three competing notions of "same vulnerability" (scanner strategies,
central consolidation, metrics aligner); v2 keeps a single one here.

Consolidation always runs and has no user-facing toggle (v1's
--allow-duplicates flag existed to repair chunk-level over-extraction; with
block-anchored extraction there is nothing to repair). Steps: structural
pairing (e.g. Tenable base+instances — structure, not dedup), severity
normalization, and merging of records with an IDENTICAL identity key.

The surviving record of a merge is the most complete one, where cvss=0.0
COUNTS as filled (a Log finding's legitimate score — v1's count_filled_fields
nuance). Which fields define identity is declared per scanner in its JSON
config (see scanners/engine.py).
"""
from __future__ import annotations

import logging
import re

from mulitaminer2.models import TenableRecord, VulnRecord

log = logging.getLogger(__name__)


def normalize_name(name: str | None) -> str:
    """Lowercase + strip + collapse internal whitespace (v1 dedup key)."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", str(name).strip().lower())


def _filled(value) -> bool:
    """cvss=0.0 counts as filled; empty containers and None do not."""
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return bool(value)
    return True


def _completeness(record: VulnRecord) -> int:
    return sum(_filled(v) for v in record.model_dump().values())


def _merge_pair(winner: VulnRecord, loser: VulnRecord) -> VulnRecord:
    """Backfill the winner's empty fields from the loser (v1 Tenable merge)."""
    for field in type(winner).model_fields:
        if not _filled(getattr(winner, field)) and _filled(getattr(loser, field)):
            setattr(winner, field, getattr(loser, field))
    return winner


def dedupe(
    records: list[VulnRecord], key_fn, merge_instances: bool = False
) -> tuple[list[VulnRecord], list[str]]:
    merged: dict = {}
    log_lines: list[str] = []
    for record in records:
        key = key_fn(record)
        if key not in merged:
            merged[key] = record
            continue
        kept = merged[key]
        if merge_instances and isinstance(record, TenableRecord):
            kept.instances = list(kept.instances) + list(record.instances)
        if _completeness(record) > _completeness(kept):
            record_wins = _merge_pair(record, kept)
            record_wins.instances = kept.instances  # already accumulated above
            merged[key] = record_wins
        else:
            _merge_pair(kept, record)
        log_lines.append(f"merged duplicate: {record.name!r} (key={key})")
    return list(merged.values()), log_lines


# Scanner-specific consolidation policies (identity fields, structural
# pairing, severity normalization) are declared in each scanner's JSON config
# and assembled by scanners/engine.py on top of dedupe() above.
