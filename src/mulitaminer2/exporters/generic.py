"""DefectDojo Generic Findings Import (JSON).

The pragmatic first integration from the OUTPUT_STANDARDS analysis: DefectDojo
is the aggregator closest to MulitaMiner's role (it ingests scanner findings
and does cross-scanner dedup/tracking), and its Generic parser takes plain
JSON — the cheapest bridge from "PDF report" to "managed findings".
Format: https://docs.defectdojo.com/supported_tools/parsers/file/generic/
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mulitaminer2.exporters import register
from mulitaminer2.models import VulnRecord

CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

# MulitaMiner severity -> DefectDojo severity (LOG is v2's informational tier).
_SEVERITY = {"CRITICAL": "Critical", "HIGH": "High", "MEDIUM": "Medium",
             "LOW": "Low", "LOG": "Info", "INFO": "Info"}


def cves_from(record: VulnRecord) -> list[str]:
    found: list[str] = []
    for ref in record.references:
        for cve in CVE_RE.findall(ref):
            cve = cve.upper()
            if cve not in found:
                found.append(cve)
    return found


def _endpoint(record: VulnRecord) -> str | None:
    if not record.host:
        return None
    if record.port is not None and record.port != "general":
        return f"{record.host}:{record.port}"
    return record.host


def _finding(record: VulnRecord) -> dict:
    cves = cves_from(record)
    finding = {
        "title": record.name,
        "severity": _SEVERITY.get(record.severity, "Info"),
        "description": "\n".join(record.description),
        "mitigation": "\n".join(record.solution),
        "impact": "\n".join(record.impact),
        "references": "\n".join(record.references),
        "active": True,
        "dynamic_finding": True,
        "static_finding": False,
        "vuln_id_from_tool": str(record.plugin) if record.plugin else record.name,
        "unique_id_from_tool": "|".join(
            str(p) for p in (record.source, record.name, record.host, record.port)
        ),
    }
    if cves:
        finding["cve"] = cves[0]
        finding["vulnerability_ids"] = [{"vulnerability_id": c} for c in cves]
    if isinstance(record.cvss, (int, float)):
        finding["cvssv3_score"] = float(record.cvss)
    endpoint = _endpoint(record)
    if endpoint:
        finding["endpoints"] = [endpoint]
    return finding


@register("generic")
def to_generic(records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path) -> Path:
    path = out_dir / "results.generic.json"
    payload = {"findings": [_finding(r) for r in records]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
