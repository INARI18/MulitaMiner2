"""SARIF 2.1.0 export; the de facto findings format tools actually ingest
(GitHub code scanning, DefectDojo, SonarQube, Azure DevOps).

Network findings carry no file location, so results use logicalLocations
(`host:port`); scanner-specific fields ride in the SARIF property bag.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mulitaminer import __version__
from mulitaminer.exporters import register
from mulitaminer.models import VulnRecord

# MulitaMiner severity -> SARIF result level.
_LEVEL = {"CRITICAL": "error", "HIGH": "error", "MEDIUM": "warning",
          "LOW": "note", "LOG": "note", "INFO": "note"}


def _rule_id(record: VulnRecord) -> str:
    plugin = getattr(record, "plugin", None)  # scanner-specific field
    if plugin:
        return f"{record.source}-{plugin}"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", record.name).strip("-")[:80]
    return f"{record.source}-{slug}"


def _result(record: VulnRecord, rule_index: int) -> dict:
    message = "\n".join(record.description) or record.name
    result = {
        "ruleId": _rule_id(record),
        "ruleIndex": rule_index,
        "level": _LEVEL.get(record.severity, "note"),
        "message": {"text": message},
        "properties": {
            "severity": record.severity,
            "cvss": getattr(record, "cvss", None),
            "source": record.source,
            "port": record.port,
            "protocol": record.protocol,
        },
    }
    if record.host:
        qualified = f"{record.host}:{record.port}" if record.port is not None else record.host
        result["locations"] = [
            {"logicalLocations": [{"fullyQualifiedName": qualified, "kind": "resource"}]}
        ]
    return result


@register("sarif", "SARIF 2.1.0 JSON (GitHub code scanning, DefectDojo, SonarQube)")
def to_sarif(records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path) -> Path:
    rules: dict[str, dict] = {}
    rule_index: dict[str, int] = {}
    for record in records:
        rid = _rule_id(record)
        if rid not in rules:
            rule_index[rid] = len(rules)
            rule = {"id": rid, "name": record.name,
                    "shortDescription": {"text": record.name}}
            solution = "\n".join(record.solution)
            if solution:
                rule["help"] = {"text": solution}
            rules[rid] = rule

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "MulitaMiner",
                        "version": __version__,
                        "informationUri": "https://github.com/INARI18/MulitaMiner2",
                        "rules": list(rules.values()),
                    }
                },
                "results": [_result(r, rule_index[_rule_id(r)]) for r in records],
            }
        ],
    }
    path = out_dir / "results.sarif"
    path.write_text(json.dumps(sarif, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
