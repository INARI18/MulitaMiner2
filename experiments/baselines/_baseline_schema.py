"""Shared schema helpers for the baseline builders and the normalizer.

Single source of truth for the canonical baseline schema: column set and order
are derived from each scanner's record model (`mulitaminer.models`), so a
baseline always tracks the tool's own record type.
"""
from __future__ import annotations

import ast
from typing import Any

from mulitaminer.models import record_type_for_source

# Baseline resource folder -> record `source` stamp.
SOURCE_BY_DIR = {"openvas": "OPENVAS", "tenable": "TENABLEWAS", "qualys": "QUALYS"}

# The record field `name` is written under its `Name` alias in the XLSX header.
_NAME_COL = "Name"

_SEVERITY_TIERS = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "LOG", "INFO"}


def canonical_columns(source: str) -> list[str]:
    """Record-model field order for a scanner's baseline (`name` -> `Name`)."""
    rt = record_type_for_source(source)
    return [_NAME_COL if n == "name" else n for n in rt.model_fields]


def normalize_severity(value: Any) -> Any:
    """Severity to its upper-case tier; pass anything unrecognized through."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    s = str(value).strip()
    return s.upper() if s.upper() in _SEVERITY_TIERS else s


def as_reference_list(value: Any) -> list[str]:
    """Any references cell -> list of reference strings, content preserved.

    Accepts a repr'd list (``"['CVE-1']"``), a newline-joined block, or a plain
    scalar; empty/NaN -> ``[]``.
    """
    if value is None or (isinstance(value, float) and value != value):
        return []
    if isinstance(value, (list, tuple)):
        items: list = list(value)
    else:
        s = str(value).strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                items = list(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                items = s.splitlines()
        else:
            items = s.splitlines()
    return [t for t in (str(i).strip() for i in items) if t]


def reference_cell(refs: list[str]) -> Any:
    """References list -> XLSX cell: a repr for non-empty, blank for empty."""
    return repr(list(refs)) if refs else None
