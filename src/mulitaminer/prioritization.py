"""KEV/EPSS/SSVC remediation queue. Deterministic and auditable, no LLM.

Feeds (CISA KEV + FIRST EPSS, ~5 MB) are synced to a local snapshot; scoring
only reads the snapshot. Every signal behind a decision is a column in the
queue, so the category is re-derivable by hand.
"""
from __future__ import annotations

import csv
import gzip
import io
import ipaddress
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from mulitaminer.models import VulnRecord
from mulitaminer.settings import FEEDS_DIR

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://epss.cyentia.com/epss_scores-current.csv.gz"
KEV_FILE, EPSS_FILE, META_FILE = "kev.json", "epss.csv.gz", "meta.json"

# EPSS score at/above which exploitation counts as "likely" (FIRST's ~F1-optimal
# remediation cutoff).
EPSS_LIKELY_THRESHOLD = 0.10

_CVE_RE = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)
_INTERNAL_SUFFIXES = (".local", ".internal", ".lan", ".home", ".corp", ".intranet")

ACT, ATTEND, TRACK_STAR, TRACK = "Act", "Attend", "Track*", "Track"
CATEGORY_ORDER = {ACT: 0, ATTEND: 1, TRACK_STAR: 2, TRACK: 3}

# (exploitation, exposure, severity) -> category. "unknown" (no CVE) sits one
# notch above "none": absence of a CVE is absence of evidence, not safety.
_TREE: dict[tuple[str, str, str], str] = {
    ("active", "exposed", "high"): ACT,
    ("active", "exposed", "medium"): ACT,
    ("active", "exposed", "low"): ATTEND,
    ("active", "internal", "high"): ACT,
    ("active", "internal", "medium"): ATTEND,
    ("active", "internal", "low"): TRACK_STAR,
    ("likely", "exposed", "high"): ACT,
    ("likely", "exposed", "medium"): ATTEND,
    ("likely", "exposed", "low"): TRACK_STAR,
    ("likely", "internal", "high"): ATTEND,
    ("likely", "internal", "medium"): TRACK_STAR,
    ("likely", "internal", "low"): TRACK,
    ("none", "exposed", "high"): ATTEND,
    ("none", "exposed", "medium"): TRACK_STAR,
    ("none", "exposed", "low"): TRACK,
    ("none", "internal", "high"): TRACK_STAR,
    ("none", "internal", "medium"): TRACK,
    ("none", "internal", "low"): TRACK,
    ("unknown", "exposed", "high"): ACT,
    ("unknown", "exposed", "medium"): ATTEND,
    ("unknown", "exposed", "low"): TRACK_STAR,
    ("unknown", "internal", "high"): ATTEND,
    ("unknown", "internal", "medium"): TRACK_STAR,
    ("unknown", "internal", "low"): TRACK,
}

QUEUE_COLUMNS = ["rank", "name", "host", "category", "exposure", "exploitation",
                 "severity", "kev", "epss", "cvss", "cves", "justification",
                 "snapshot_date"]


# --------------------------------------------------------------------------- #
# feeds
# --------------------------------------------------------------------------- #
def sync_feeds(dest: Path = FEEDS_DIR) -> dict:
    """Download KEV + EPSS into dest and stamp meta.json. Fails loud."""
    import httpx

    dest.mkdir(parents=True, exist_ok=True)
    kev_bytes = httpx.get(KEV_URL, timeout=60, follow_redirects=True).raise_for_status().content
    _atomic_write(dest / KEV_FILE, kev_bytes)
    epss_bytes = httpx.get(EPSS_URL, timeout=60, follow_redirects=True).raise_for_status().content
    _atomic_write(dest / EPSS_FILE, epss_bytes)

    meta = {
        "synced_at": datetime.now(UTC).isoformat(),
        "kev_count": len(load_kev(dest)),
        "epss_count": len(load_epss(dest)),
        "epss_score_date": _epss_score_date(epss_bytes),
    }
    _atomic_write(dest / META_FILE, json.dumps(meta, indent=2).encode("utf-8"))
    return meta


def load_kev(dest: Path = FEEDS_DIR) -> set[str]:
    path = dest / KEV_FILE
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {v["cveID"].upper() for v in data.get("vulnerabilities", []) if v.get("cveID")}


def load_epss(dest: Path = FEEDS_DIR) -> dict[str, float]:
    path = dest / EPSS_FILE
    if not path.exists():
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = (line for line in fh if not line.startswith("#"))
        return {r["cve"].upper(): float(r["epss"]) for r in csv.DictReader(rows) if r.get("cve")}


def feed_meta(dest: Path = FEEDS_DIR) -> dict | None:
    path = dest / META_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _epss_score_date(epss_bytes: bytes) -> str | None:
    with gzip.open(io.BytesIO(epss_bytes), "rt", encoding="utf-8") as fh:
        first = fh.readline()
    m = re.search(r"score_date:([0-9T:\-]+)", first)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# per-record signals
# --------------------------------------------------------------------------- #
def extract_cve_ids(record: VulnRecord) -> list[str]:
    """CVE ids from references and plugin details, upper-cased, order preserved."""
    parts = [str(x) for x in record.references]
    details = record.plugin_details
    if details:
        parts.append(details if isinstance(details, str) else json.dumps(
            details if isinstance(details, dict) else details.model_dump()))
    seen: dict[str, None] = {}
    for match in _CVE_RE.findall(" ".join(parts)):
        seen[match.upper()] = None
    return list(seen)


def host_of(record: VulnRecord) -> str | None:
    """The asset host, or the first instance URL for web-scan records."""
    if record.host:
        return str(record.host)
    for item in record.instances or []:
        value = item.get("instance") if isinstance(item, dict) else getattr(item, "instance", "")
        if value:
            return str(value)
    return None


def exposure(record: VulnRecord) -> str:
    """"internal" only when the host is confidently private; else "exposed"."""
    host = host_of(record)
    if not host:
        return "exposed"
    hostname = _hostname(host)
    if not hostname:
        return "exposed"
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        internal = "." not in hostname or hostname.endswith(_INTERNAL_SUFFIXES)
        return "internal" if internal else "exposed"
    private = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    return "internal" if private else "exposed"


def severity_band(record: VulnRecord) -> str:
    """high / medium / low from numeric CVSS, falling back to the label."""
    cvss = record.cvss if isinstance(record.cvss, (int, float)) else None
    if cvss is not None and cvss > 0:
        return "high" if cvss >= 7.0 else "medium" if cvss >= 4.0 else "low"
    word = (record.severity or "").lower()
    return "high" if word in ("critical", "high") else "medium" if word == "medium" else "low"


def exploitation(cves: list[str], kev: set[str], epss: dict[str, float],
                 threshold: float = EPSS_LIKELY_THRESHOLD) -> str:
    if not cves:
        return "unknown"
    if any(cve in kev for cve in cves):
        return "active"
    if max((epss.get(cve, 0.0) for cve in cves), default=0.0) >= threshold:
        return "likely"
    return "none"


# --------------------------------------------------------------------------- #
# queue
# --------------------------------------------------------------------------- #
def build_queue(records: list[VulnRecord], kev: set[str], epss: dict[str, float],
                snapshot_date: str | None = None) -> list[dict]:
    """Rank all records: category, then EPSS desc, then CVSS desc."""
    rows = []
    for record in records:
        cves = extract_cve_ids(record)
        expo = exposure(record)
        expl = exploitation(cves, kev, epss)
        sev = severity_band(record)
        score = max((epss.get(cve, 0.0) for cve in cves), default=0.0)
        rows.append({
            "name": record.name,
            "host": host_of(record) or "",
            "category": _TREE[(expl, expo, sev)],
            "exposure": expo,
            "exploitation": expl,
            "severity": sev,
            "kev": any(cve in kev for cve in cves),
            "epss": round(score, 5),
            "cvss": record.cvss if isinstance(record.cvss, (int, float)) else "",
            "cves": ", ".join(cves),
            "justification": _justify(expl, expo, sev),
            "snapshot_date": snapshot_date or "",
        })
    rows.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], -r["epss"], -_as_float(r["cvss"])))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def prioritize_run(run_dir: Path, feeds_dir: Path = FEEDS_DIR) -> dict[str, Path]:
    """Read a run's results.json, rank it, write the queue beside it."""
    from mulitaminer.models import record_type_for_source

    results = run_dir / "results.json" if run_dir.is_dir() else run_dir
    data = json.loads(results.read_text(encoding="utf-8"))
    record_type = record_type_for_source(data[0].get("source") if data else None)
    records = [record_type.model_validate(r) for r in data]

    kev, epss = load_kev(feeds_dir), load_epss(feeds_dir)
    if not kev and not epss:
        raise ValueError("KEV/EPSS feeds not found. Run `mulitaminer sync-feeds` first.")
    meta = feed_meta(feeds_dir) or {}
    rows = build_queue(records, kev, epss, snapshot_date=meta.get("epss_score_date"))

    base = results.parent / "results.prioritization"
    csv_path = base.with_name(base.name + ".csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    import pandas as pd

    xlsx_path = base.with_name(base.name + ".xlsx")
    pd.DataFrame(rows, columns=QUEUE_COLUMNS).to_excel(
        xlsx_path, index=False, sheet_name="Prioritization")
    return {"csv": csv_path, "xlsx": xlsx_path}


def _justify(expl: str, expo: str, sev: str) -> str:
    exploit_phrase = {
        "active": "active exploitation (KEV)",
        "likely": "likely exploitation (EPSS)",
        "none": "no known exploitation",
        "unknown": "no CVE to assess exploitation",
    }[expl]
    expo_phrase = "internet-exposed" if expo == "exposed" else "internal asset"
    return f"{exploit_phrase}; {expo_phrase}; {sev} severity"


def _hostname(host: str) -> str:
    host = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", host.strip(), flags=re.IGNORECASE)
    host = host.split("/")[0].split("?")[0]
    if ":" in host and host.count(":") < 2:  # drop :port, keep IPv6 literals
        host = host.rsplit(":", 1)[0]
    return host.strip("[]").lower()


def _as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
