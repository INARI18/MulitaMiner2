"""OpenVAS/Greenbone scanner profile: segmentation + prompt + record type.

Domain knowledge carried over from MulitaMiner v1 (provenance in comments):

- The block marker is the ``<Severity> (CVSS: X.Y)`` header line, which sits
  immediately ABOVE each ``NVT:`` line. v1 originally marked at ``NVT:``
  itself, which left the severity/cvss header in the previous segment and
  forced the LLM to guess severity (often defaulting to LOG) —
  misclassification on Ingreslock/Telnet in the bWAPP report. Breaking one
  line earlier makes the header travel with its NVT.
- Port/protocol headers (``High 443/tcp``) appear in three layouts (plain,
  reversed order, section-numbered); all are tracked as scanning state and
  attached to blocks as context, since the header may sit in the previous
  block's tail.
- The scanned host is the IP on the line above ``Host scan start`` — it lives
  in the report preamble (before any marker), so segmentation state-tracking
  is the only way to recover it.
"""
from __future__ import annotations

import re
from pathlib import Path

from mulitaminer2.consolidate import consolidate_openvas
from mulitaminer2.models import Block, OpenVASRecord
from mulitaminer2.scanners.profile import ScannerProfile

# One marker line == one finding occurrence (v1 configs/scanners/openvas.json).
MARKER = re.compile(r"^\s*(?:Critical|High|Medium|Low|Log)\s+\(CVSS:", re.MULTILINE)

# Header layouts (v1 scanners/openvas.py HEADER_REGEX / HEADER_REGEX_ALT):
#   (1) "High 443/tcp"            severity then port/proto (text PDF)
#   (2) "443/tcp High"            reversed (markdown extractor)
#   (3) "2.1.1 Critical 8019/tcp" section-number prefix (markdown TOC)
_SEV = r"(?P<sev>Critical|High|Medium|Low|Log)"
_PORT = r"(?P<port>\d+|general)"
_PROTO = r"(?P<proto>[a-zA-Z0-9_-]+)"
_SECTION_NUM = r"(?:\d+(?:\.\d+)*\s+)?"
HEADER_REGEX = re.compile(rf"^(?:#+\s+)?{_SECTION_NUM}{_SEV}\s+{_PORT}/{_PROTO}", re.IGNORECASE)
HEADER_REGEX_ALT = re.compile(rf"^(?:#+\s+)?{_PORT}/{_PROTO}\s+{_SEV}", re.IGNORECASE)

# Host recovery (v1): the target IP is on the nearest non-blank line above
# "Host scan start", optionally preceded by a section number.
_HOST_LINE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\s+)?((?:\d{1,3}\.){3}\d{1,3})\s*$")
_HOST_SCAN_ANCHOR = re.compile(r"^\s*host scan start", re.IGNORECASE)

_MARKER_SEV = re.compile(r"^\s*(Critical|High|Medium|Low|Log)\s+\(CVSS:", re.IGNORECASE)


def segment(text: str) -> list[Block]:
    """Split the cleaned report text into one Block per finding marker.

    Content before the first marker (cover, TOC, per-host preamble) yields no
    block but IS scanned, because it carries the initial host and port state.
    """
    lines = text.splitlines()

    host: str | None = None
    port: int | str | None = None
    protocol: str | None = None
    last_nonblank: str | None = None

    blocks: list[Block] = []
    current: list[str] | None = None  # lines of the open block
    current_meta: dict = {}

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(
                Block(id=len(blocks), text="\n".join(current).strip(), **current_meta)
            )
        current = None

    for line in lines:
        stripped = line.strip()

        # Per-host boundary: IP sits on the line above "Host scan start".
        if _HOST_SCAN_ANCHOR.match(stripped) and last_nonblank:
            m = _HOST_LINE.match(last_nonblank)
            if m:
                host = m.group(1)
        if stripped:
            last_nonblank = stripped

        header = HEADER_REGEX.match(stripped) or HEADER_REGEX_ALT.match(stripped)
        if header:
            port_raw = header.group("port")
            port = int(port_raw) if port_raw.isdigit() else port_raw
            protocol = header.group("proto").lower()

        marker = _MARKER_SEV.match(stripped)
        if marker:
            flush()
            current = []
            current_meta = {
                "host": host,
                "port": port,
                "protocol": protocol,
                "severity_hint": marker.group(1).upper(),
            }
        if current is not None:
            current.append(line)

    flush()
    return blocks


PROFILE = ScannerProfile(
    name="openvas",
    source="OPENVAS",
    record_type=OpenVASRecord,
    marker=MARKER,
    prompt_path=Path(__file__).with_name("openvas_prompt.txt"),
    max_vulns_per_chunk=4,  # v1 calibration (configs/scanners/openvas.json)
    segment=segment,
    consolidate=consolidate_openvas,
)
