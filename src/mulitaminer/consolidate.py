"""Consolidation primitives. Always runs: structural pairing, severity
normalization, then merging of fully identical records. The survivor of a
merge is the most complete record; cvss=0.0 counts as filled."""
from __future__ import annotations

import logging
import re

from mulitaminer.models import VulnRecord

log = logging.getLogger(__name__)


def normalize_name(name: str | None) -> str:
    """Lowercase + strip + collapse internal whitespace."""
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
    """Backfill the winner's empty fields from the loser."""
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
        has_instances = "instances" in type(record).model_fields
        if merge_instances and has_instances:
            kept.instances = list(kept.instances) + list(record.instances)
        if _completeness(record) > _completeness(kept):
            record_wins = _merge_pair(record, kept)
            if merge_instances and has_instances:
                record_wins.instances = kept.instances  # already accumulated above
            merged[key] = record_wins
        else:
            _merge_pair(kept, record)
        log_lines.append(f"merged duplicate: {record.name!r} (key={key})")
    return list(merged.values()), log_lines


# Scanner-specific consolidation policies (identity fields, structural
# pairing, severity normalization) are declared in each scanner's JSON config
# and assembled by scanners/engine.py on top of dedupe() above.
