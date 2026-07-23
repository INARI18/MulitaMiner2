"""CSAF 2.0 security advisory export (OASIS; the CISA-endorsed advisory format).

One document per run: scanned hosts become the product_tree, each record one
entry in vulnerabilities[]. Scores are emitted only when a CVSS v3 vector is
available (the cvss_v3 object requires vectorString).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from mulitaminer import __version__
from mulitaminer.exporters import register
from mulitaminer.exporters.generic import cves_from
from mulitaminer.models import VulnRecord

_CVSS3_SCORE_RE = re.compile(r"CVSSV3\s+BASE\s+SCORE\s+([\d.]+)", re.IGNORECASE)
_CVSS3_VECTOR_RE = re.compile(r"CVSSV3\s+VECTOR\s+(CVSS:3[^\s]+)", re.IGNORECASE)

_BASE_SEVERITY = {"CRITICAL": "CRITICAL", "HIGH": "HIGH", "MEDIUM": "MEDIUM",
                  "LOW": "LOW", "LOG": "NONE", "INFO": "NONE"}


def _product_id(host: str, index: dict[str, str]) -> str:
    if host not in index:
        index[host] = f"HOST-{len(index) + 1}"
    return index[host]


def _score(record: VulnRecord, product_id: str | None) -> dict | None:
    cvss = getattr(record, "cvss", None)  # scanner-specific field
    if not isinstance(cvss, list):
        return None
    joined = " ".join(cvss)
    vector = _CVSS3_VECTOR_RE.search(joined)
    score = _CVSS3_SCORE_RE.search(joined)
    if not (vector and score):
        return None
    cvss = {
        "version": "3.1" if vector.group(1).startswith("CVSS:3.1") else "3.0",
        "vectorString": vector.group(1),
        "baseScore": float(score.group(1)),
        "baseSeverity": _BASE_SEVERITY.get(record.severity, "NONE"),
    }
    return {"products": [product_id] if product_id else [], "cvss_v3": cvss}


def _vulnerability(record: VulnRecord, product_index: dict[str, str]) -> dict:
    product_id = _product_id(record.host, product_index) if record.host else None
    entry: dict = {
        "title": record.name,
        "notes": [{"category": "description",
                   "text": "\n".join(record.description) or record.name}],
    }
    cves = cves_from(record)
    if cves:
        entry["cve"] = cves[0]
    if product_id:
        entry["product_status"] = {"known_affected": [product_id]}
    if record.solution:
        remediation = {"category": "mitigation", "details": "\n".join(record.solution)}
        if product_id:
            remediation["product_ids"] = [product_id]
        entry["remediations"] = [remediation]
    if score := _score(record, product_id):
        entry["scores"] = [score]
    return entry


@register("csaf", "CSAF 2.0 security advisory JSON (CISA/CSIRT ecosystem)")
def to_csaf(records: list[VulnRecord], record_type: type[VulnRecord], out_dir: Path) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    product_index: dict[str, str] = {}
    vulnerabilities = [_vulnerability(r, product_index) for r in records]

    document = {
        "document": {
            "category": "csaf_security_advisory",
            "csaf_version": "2.0",
            "lang": "en",
            "publisher": {
                "category": "other",
                "name": "MulitaMiner",
                "namespace": "https://github.com/INARI18/MulitaMiner2",
            },
            "title": "MulitaMiner scan findings",
            "tracking": {
                "id": f"MULITAMINER-{now.replace(':', '').replace('-', '')}",
                "status": "final",
                "version": "1",
                "generator": {"engine": {"name": "MulitaMiner", "version": __version__}},
                "initial_release_date": now,
                "current_release_date": now,
                "revision_history": [
                    {"date": now, "number": "1", "summary": "Initial version"}
                ],
            },
        },
        "product_tree": {
            "full_product_names": [
                {"product_id": pid, "name": host} for host, pid in product_index.items()
            ]
        },
        "vulnerabilities": vulnerabilities,
    }
    path = out_dir / "results.csaf.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
