"""DefectDojo Generic Findings Import (JSON).

DefectDojo
is the aggregator closest to MulitaMiner's role (it ingests scanner findings
and does cross-scanner dedup/tracking), and its Generic parser takes plain
JSON; the cheapest bridge from "PDF report" to "managed findings".
Format: https://docs.defectdojo.com/supported_tools/parsers/file/generic/
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mulitaminer.exporters import register
from mulitaminer.models import VulnRecord

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


def instance_urls(record: VulnRecord) -> list[str]:
    """Distinct URLs a web finding was seen on; the location of host-less records (ZAP)."""
    urls: list[str] = []
    for inst in getattr(record, "instances", None) or []:  # scanner-specific field
        if inst.instance and inst.instance not in urls:
            urls.append(inst.instance)
    return urls


def endpoints(record: VulnRecord) -> list[str]:
    """`host:port`, the bare host, or the instance URLs of host-less records."""
    if not record.host:
        return instance_urls(record)
    # Nessus uses port 0 for host-level findings; DefectDojo drops "host:0".
    if record.port not in (None, "general", 0):
        return [f"{record.host}:{record.port}"]
    return [record.host]


# Scanner-specific text fields -> the DefectDojo field they belong in. Generic
# has no field for "why it is vulnerable", so insight extends the description.
_DESCRIPTION_EXTRAS = ("insight",)
_STEPS_FIELDS = ("detection_method", "detection_result", "product_detection_result", "log_method")


def _sections(record: VulnRecord, fields: tuple[str, ...]) -> list[str]:
    sections = []
    for field in fields:
        if lines := getattr(record, field, None):  # absent on scanners without it
            sections.append(f"**{field.replace('_', ' ').capitalize()}**\n" + "\n".join(lines))
    return sections


def _finding(record: VulnRecord) -> dict:
    cves = cves_from(record)
    description = ["\n".join(record.description)] if record.description else []
    finding = {
        "title": record.name,
        "severity": _SEVERITY.get(record.severity.upper(), "Info"),
        "description": "\n\n".join(description + _sections(record, _DESCRIPTION_EXTRAS)),
        "mitigation": "\n".join(record.solution),
        "impact": "\n".join(record.impact),
        "references": "\n".join(record.references),
        "active": True,
        "dynamic_finding": True,
        "static_finding": False,
        "vuln_id_from_tool": str(getattr(record, "plugin", None) or record.name),
        "unique_id_from_tool": "|".join(
            str(p) for p in (record.source, record.name, record.host, record.port)
        ),
    }
    if cves:
        finding["cve"] = cves[0]
        if cves[1:]:  # DefectDojo adds these after `cve`
            finding["vulnerability_ids"] = cves[1:]
    cvss = getattr(record, "cvss", None)
    if isinstance(cvss, (int, float)):
        finding["cvssv3_score"] = float(cvss)
    if eps := endpoints(record):
        finding["endpoints"] = eps
    if steps := _sections(record, _STEPS_FIELDS):
        finding["steps_to_reproduce"] = "\n\n".join(steps)
    return finding


@register("generic", "DefectDojo Generic Findings JSON (import into DefectDojo)")
def to_generic(records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path) -> Path:
    path = out_dir / "results.generic.json"
    payload = {"findings": [_finding(r) for r in records]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
