"""ScannerProfile — the single source of truth for one scanner.

Everything that defines a scanner lives in its module: marker regex,
segmentation, prompt, chunk sizing, record type. Adding a scanner = one module
+ one prompt file + one entry in scanners.SCANNERS (v1 spread this knowledge
across a JSON config, hardcoded regexes in the chunker, and a strategy class).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mulitaminer2.models import Block, VulnRecord


@dataclass(frozen=True)
class ScannerProfile:
    name: str                     # CLI name, e.g. "openvas"
    source: str                   # stamped into VulnRecord.source, e.g. "OPENVAS"
    record_type: type[VulnRecord]
    marker: re.Pattern            # one match line == one candidate finding
    prompt_path: Path
    max_vulns_per_chunk: int      # v1 calibration, per scanner
    segment: Callable[[str], list[Block]]
    # (records, allow_duplicates) -> (consolidated records, merge-log lines)
    consolidate: Callable[[list[VulnRecord], bool], tuple[list[VulnRecord], list[str]]]

    def prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")
