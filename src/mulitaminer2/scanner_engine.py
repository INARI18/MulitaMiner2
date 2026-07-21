"""Config-driven scanner engine: a scanner is ONE JSON file + ONE prompt file.

Unlike v1 — where the JSON held only part of the definition and the rest lived
in a strategy class plus regexes hardcoded in the chunker — here the JSON is
the WHOLE definition. Adding a scanner requires no Python: drop `<name>.json`
+ `<name>.txt` into `configs/scanners/` + `configs/prompts/` (or into the
directory named by the MULITAMINER2_SCANNERS_DIR env var) and it registers.

JSON fields:
- name:                CLI name. Also selects the typed record class when one
                       matches (openvas/tenable); otherwise the base VulnRecord
                       is used. An explicit "record" key overrides.
- source:              stamped into every record's `source` field.
- prompt:              optional prompt filename; defaults to `<name>.txt`.
- max_vulns_per_chunk: chunk-size cap for this scanner.
- marker_pattern:      regex; ONE match line == ONE finding block. If it has a
                       capture group 1, that group is the severity hint. Use
                       an inline "(?i)" prefix for case-insensitive matching.
- name_above_marker:   bool; the finding NAME is the single line directly
                       ABOVE the marker and is pulled into the block (Tenable;
                       mirror of the OpenVAS NVT lesson).
- name_stop_pattern:   optional regex; a line matching it is never taken as
                       the name (section headers / reference tails / URLs of
                       the previous block).
- context:             optional tracking of state that lives OUTSIDE blocks:
    header_patterns:   regexes with named groups (?P<sev>/(?P<port>/(?P<proto>;
                       the latest match above a marker becomes that block's
                       port/protocol context (case-insensitive).
    host_anchor:       regex for the per-host boundary line.
    host_line:         regex whose group 1 is the host, matched on the nearest
                       non-blank line above the anchor.
- pair:                optional structural pairing (ALWAYS runs — structure,
                       not dedup): {strip_name_suffix, by: [fields],
                       merge_instances}. Tenable pairs Base + "Instances (N)"
                       records by (name, plugin).
- severity_map:        optional post-pairing normalization, e.g. {"INFO": "LOG"}.

Duplicate merging is not configurable: a duplicate is a FULLY identical
record (name compared normalized) — same key with different content is two
real findings and never collapses.

The rationale behind each built-in config value (marker choices, name
placement, pairing) is documented in docs/SCANNER_CONFIGS.md.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from mulitaminer2.consolidate import dedupe, normalize_name
from mulitaminer2.models import Block, OpenVASRecord, TenableRecord, VulnRecord

RECORD_TYPES: dict[str, type[VulnRecord]] = {
    "openvas": OpenVASRecord,
    "tenable": TenableRecord,
    "generic": VulnRecord,
}

_BUILTIN_DIR = Path(__file__).parent / "configs" / "scanners"

# A wrapped block-title tail, e.g. "(1)" or "Instances" / "Instances (25)"
# alone on the line above a marker — the real name sits one line further up.
_SUFFIX_FRAGMENT = re.compile(r"^(\(\d+\)|Instances(\s*\(\d+\))?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ScannerProfile:
    """Everything that defines one scanner, built from its JSON config."""

    name: str                     # CLI name, e.g. "openvas"
    source: str                   # stamped into VulnRecord.source
    record_type: type[VulnRecord]
    marker: re.Pattern            # one match line == one candidate finding
    prompt_path: Path
    max_vulns_per_chunk: int      # v1 calibration, per scanner
    segment: Callable[[str], list[Block]]
    # records -> (consolidated records, merge-log lines). Always runs:
    # structural pairing + severity normalization + identical-identity dedup.
    consolidate: Callable[[list[VulnRecord]], tuple[list[VulnRecord], list[str]]]

    def prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")


def _build_segmenter(cfg: dict):
    marker = re.compile(cfg["marker_pattern"])
    context = cfg.get("context") or {}
    headers = [re.compile(p, re.IGNORECASE) for p in context.get("header_patterns", [])]
    host_anchor = re.compile(context["host_anchor"], re.IGNORECASE) if "host_anchor" in context else None
    host_line = re.compile(context["host_line"]) if "host_line" in context else None
    walkback = 1 if cfg.get("name_above_marker") else 0
    name_stop = re.compile(cfg["name_stop_pattern"], re.IGNORECASE) if "name_stop_pattern" in cfg else None

    def segment(text: str) -> list[Block]:
        lines = text.splitlines()
        host = port = proto = None
        last_nonblank: str | None = None
        markers: list[tuple[int, dict]] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if host_anchor and host_line and last_nonblank and host_anchor.match(stripped):
                m = host_line.match(last_nonblank)
                if m:
                    host = m.group(1)
            if stripped:
                last_nonblank = stripped
            for header in headers:
                m = header.match(stripped)
                if m:
                    groups = m.groupdict()
                    if groups.get("port"):
                        port = int(groups["port"]) if groups["port"].isdigit() else groups["port"]
                    if groups.get("proto"):
                        proto = groups["proto"].lower()
                    break
            m = marker.search(line)
            if m:
                severity = m.group(1).upper() if m.groups() and m.group(1) else None
                markers.append(
                    (i, {"host": host, "port": port, "protocol": proto,
                         "severity_hint": severity})
                )

        starts: list[int] = []
        for k, (idx, _) in enumerate(markers):
            start = idx
            barrier = markers[k - 1][0] if k else -1
            if walkback and idx - 1 > barrier:
                candidate = lines[idx - 1].strip()
                if candidate and not (name_stop and name_stop.match(candidate)):
                    start = idx - 1
                    # Long "<name> Instances (N)" titles wrap: the line above
                    # the marker is then only the suffix fragment ("(1)" or
                    # "Instances"). Climb one more line for the real name.
                    if _SUFFIX_FRAGMENT.match(candidate) and start - 1 > barrier:
                        above = lines[start - 1].strip()
                        if above and not (name_stop and name_stop.match(above)):
                            start -= 1
            starts.append(start)

        blocks: list[Block] = []
        for k, start in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            blocks.append(
                Block(id=k, text="\n".join(lines[start:end]).strip(), **markers[k][1])
            )
        return blocks

    return segment


def _build_consolidator(cfg: dict):
    pair = cfg.get("pair")
    strip_suffix = re.compile(pair["strip_name_suffix"], re.IGNORECASE) if pair and "strip_name_suffix" in pair else None
    severity_map = cfg.get("severity_map") or {}

    def _pair_key(record: VulnRecord):
        name = record.name or ""
        if strip_suffix:
            name = strip_suffix.sub("", name)
        return (normalize_name(name), *(getattr(record, f) for f in pair["by"]))

    def _identity_key(record: VulnRecord):
        # A duplicate is a FULLY identical record (name compared normalized).
        # User decision, generalizing v1's 'Services' exception to everything:
        # same key but different content means two real findings — merging
        # them would silently lose one. Only exact repeats collapse.
        data = record.model_dump(mode="json", by_alias=True)
        data["Name"] = normalize_name(record.name)
        return json.dumps(data, sort_keys=True)

    def consolidate(records: list[VulnRecord]):
        log_lines: list[str] = []
        if pair:
            records, lines = dedupe(records, _pair_key,
                                    merge_instances=bool(pair.get("merge_instances")))
            log_lines += lines
        for record in records:
            mapped = severity_map.get(record.severity)
            if mapped:
                record.severity = mapped
        records, lines = dedupe(records, _identity_key)
        return records, log_lines + lines

    return consolidate


def _resolve_prompt(config_path: Path, prompt_name: str) -> Path:
    """Prompts may sit next to the JSON (flat user dirs) or in a sibling
    `prompts/` folder (the package convention: configs/scanners + configs/prompts)."""
    candidates = (
        config_path.parent / prompt_name,
        config_path.parent.parent / "prompts" / prompt_name,
        config_path.parent / "prompts" / prompt_name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError(
        f"Prompt '{prompt_name}' for scanner config {config_path} not found in: "
        + ", ".join(str(c.parent) for c in candidates)
    )


def load_profile(config_path: Path) -> ScannerProfile:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        record_type = RECORD_TYPES.get(cfg.get("record", cfg["name"]), VulnRecord)
        return ScannerProfile(
            name=cfg["name"],
            source=cfg["source"],
            record_type=record_type,
            marker=re.compile(cfg["marker_pattern"]),
            prompt_path=_resolve_prompt(config_path, cfg.get("prompt", f"{cfg['name']}.txt")),
            max_vulns_per_chunk=int(cfg["max_vulns_per_chunk"]),
            segment=_build_segmenter(cfg),
            consolidate=_build_consolidator(cfg),
        )
    except KeyError as exc:
        raise ValueError(f"Scanner config {config_path} is missing field {exc}") from exc


@lru_cache
def _registry(extra_dir: str | None) -> dict[str, ScannerProfile]:
    profiles: dict[str, ScannerProfile] = {}
    dirs = [_BUILTIN_DIR]
    if extra_dir:
        user_dir = Path(extra_dir)
        # Accept both a flat user dir and one mirroring the scanners/ split.
        dirs += [user_dir, user_dir / "scanners"]
    for directory in dirs:
        for config in sorted(directory.glob("*.json")):
            profile = load_profile(config)
            profiles[profile.name] = profile
    return profiles


def all_scanners() -> dict[str, ScannerProfile]:
    return _registry(os.getenv("MULITAMINER2_SCANNERS_DIR"))


def get_scanner(name: str) -> ScannerProfile:
    scanners = all_scanners()
    try:
        return scanners[name.lower()]
    except KeyError:
        raise ValueError(f"Unknown scanner '{name}'. Available: {sorted(scanners)}")
