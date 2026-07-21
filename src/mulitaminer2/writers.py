"""Output writers: JSON (primary), XLSX, CSV.

Columns are derived from the record model — never hardcoded.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from mulitaminer2.models import VulnRecord

log = logging.getLogger(__name__)


def _dump(records: list[VulnRecord]) -> list[dict]:
    return [r.model_dump(by_alias=True) for r in records]


def columns_for(record_type: type[VulnRecord]) -> list[str]:
    """Schema-ordered output columns (JSON key names)."""
    return [f.alias or name for name, f in record_type.model_fields.items()]


def write_json(records: list[VulnRecord], path: Path) -> None:
    path.write_text(
        json.dumps(_dump(records), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Wrote %d records to %s", len(records), path)


def _cell(value) -> object:
    if isinstance(value, list):
        return "\n".join(
            v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for v in value
        )
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False) if value else ""
    return value


def _dataframe(records: list[VulnRecord], record_type: type[VulnRecord]):
    import pandas as pd

    cols = columns_for(record_type)
    rows = [{c: _cell(d.get(c)) for c in cols} for d in _dump(records)]
    return pd.DataFrame(rows, columns=cols)


def write_xlsx(records: list[VulnRecord], record_type: type[VulnRecord], path: Path) -> None:
    _dataframe(records, record_type).to_excel(path, index=False)
    log.info("Wrote %d records to %s", len(records), path)


def write_csv(records: list[VulnRecord], record_type: type[VulnRecord], path: Path) -> None:
    _dataframe(records, record_type).to_csv(path, index=False, encoding="utf-8")
    log.info("Wrote %d records to %s", len(records), path)
