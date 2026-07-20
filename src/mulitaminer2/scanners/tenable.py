"""Tenable WAS scanner profile: segmentation + prompt + record type.

Domain knowledge carried over from MulitaMiner v1:

- Each finding block is delimited by a ``VULNERABILITY <SEVERITY> PLUGIN ID
  <n>`` header. The vulnerability NAME sits on the line(s) immediately BEFORE
  that header — segmentation walks back to pull it into the block it names
  (the mirror image of the OpenVAS NVT lesson).
- A vulnerability typically appears as TWO consecutive blocks: a Base block
  (Description/Solution/Risk/Plugin Details) and an ``... Instances (N)``
  block. Both are extracted as separate records here; consolidation merges
  them by (Name, plugin).
"""
from __future__ import annotations

import re
from pathlib import Path

from mulitaminer2.models import Block, TenableRecord
from mulitaminer2.scanners.profile import ScannerProfile

# v1 configs/scanners/tenable.json marker (with v1 strategy's optional
# markdown-heading / section-number prefixes).
MARKER = re.compile(
    r"(?:#+\s+)?(?:\d+(?:\.\d+)*\s+)?VULNERABILITY\s+(CRITICAL|HIGH|MEDIUM|LOW|INFO)"
    r"\s+PLUGIN\s+ID\s+\d+",
    re.IGNORECASE,
)

# Lines that clearly belong to the PREVIOUS block's body — the name walk-back
# must not cross them.
_SECTION_LINE = re.compile(
    r"^\s*(Description|Solution|Risk Information|Plugin Details|Reference Information|"
    r"Identification|HTTP Info|See Also)\b.*:?\s*$|^\s*https?://",
    re.IGNORECASE,
)

# How many non-blank lines a wrapped vulnerability name can span above its
# VULNERABILITY header (names wrap to 2 lines in the baseline reports).
_NAME_WALKBACK = 2


def segment(text: str) -> list[Block]:
    """One Block per VULNERABILITY header, name line(s) pulled in from above."""
    lines = text.splitlines()
    marker_idx = [i for i, line in enumerate(lines) if MARKER.search(line)]
    if not marker_idx:
        return []

    # For each marker, walk back over the contiguous non-blank, non-section
    # lines that hold the vulnerability name.
    starts: list[int] = []
    for prev_end, idx in zip([-1] + marker_idx[:-1], marker_idx):
        start = idx
        walked = 0
        for j in range(idx - 1, max(prev_end, idx - 1 - _NAME_WALKBACK), -1):
            candidate = lines[j].strip()
            if not candidate or _SECTION_LINE.match(candidate):
                break
            # Beyond the line directly above the header, only accept plausible
            # name continuations: a wrapped name never ends with sentence
            # punctuation, while previous-block body content usually does.
            if walked >= 1 and candidate.endswith((".", ":", ";", "!", "?")):
                break
            start = j
            walked += 1
            if walked >= _NAME_WALKBACK:
                break
        starts.append(start)

    blocks: list[Block] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        severity = MARKER.search(lines[marker_idx[k]])
        blocks.append(
            Block(
                id=k,
                text=body,
                severity_hint=severity.group(1).upper() if severity else None,
            )
        )
    return blocks


PROFILE = ScannerProfile(
    name="tenable",
    source="TENABLEWAS",
    record_type=TenableRecord,
    marker=MARKER,
    prompt_path=Path(__file__).with_name("tenable_prompt.txt"),
    max_vulns_per_chunk=3,  # v1 calibration (configs/scanners/tenable.json)
    segment=segment,
)
