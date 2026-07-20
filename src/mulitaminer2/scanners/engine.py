"""Config-driven scanner engine: a scanner is ONE JSON file + ONE prompt file.

Unlike v1 — where the JSON held only part of the definition and the rest lived
in a strategy class plus regexes hardcoded in the chunker — here the JSON is
the WHOLE definition. Adding a scanner requires no Python: drop
`<name>.json` + `<name>_prompt.txt` into `scanners/configs/` (or into the
directory named by the MULITAMINER2_SCANNERS_DIR env var) and it registers.

JSON fields:
- name:                CLI name.
- source:              stamped into every record's `source` field.
- record:              "openvas" | "tenable" | "generic" (typed record class;
                       generic uses the base VulnRecord).
- prompt:              prompt filename, relative to the JSON file.
- max_vulns_per_chunk: chunk-size cap for this scanner.
- marker_pattern:      regex; ONE match line == ONE finding block. If it has a
                       capture group 1, that group is the severity hint.
- marker_ignorecase:   optional bool (default false).
- name_walkback:       lines of finding NAME to pull in from ABOVE the marker
                       (0 = none; Tenable uses 2 — the name precedes its
                       VULNERABILITY header).
- name_stop_pattern:   optional regex; the walk-back never crosses a line
                       matching it (section headers / URLs of the previous
                       block). Beyond the first line, the walk-back also stops
                       at sentence-final punctuation (wrapped names don't end
                       with '.').
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
- identity:            fields defining a DUPLICATE (skipped when the user
                       passes --allow-duplicates). "name" is normalized.
- keys starting with "_" are documentation (lessons travel with the config).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mulitaminer2.consolidate import dedupe, normalize_name
from mulitaminer2.models import Block, OpenVASRecord, TenableRecord, VulnRecord
from mulitaminer2.scanners.profile import ScannerProfile

RECORD_TYPES: dict[str, type[VulnRecord]] = {
    "openvas": OpenVASRecord,
    "tenable": TenableRecord,
    "generic": VulnRecord,
}

_SENTENCE_END = (".", ":", ";", "!", "?")


def _build_segmenter(cfg: dict):
    marker = re.compile(
        cfg["marker_pattern"], re.IGNORECASE if cfg.get("marker_ignorecase") else 0
    )
    context = cfg.get("context") or {}
    headers = [re.compile(p, re.IGNORECASE) for p in context.get("header_patterns", [])]
    host_anchor = re.compile(context["host_anchor"], re.IGNORECASE) if "host_anchor" in context else None
    host_line = re.compile(context["host_line"]) if "host_line" in context else None
    walkback = int(cfg.get("name_walkback", 0))
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
            walked = 0
            for j in range(idx - 1, max(barrier, idx - 1 - walkback), -1):
                candidate = lines[j].strip()
                if not candidate or (name_stop and name_stop.match(candidate)):
                    break
                if walked >= 1 and candidate.endswith(_SENTENCE_END):
                    break
                start = j
                walked += 1
                if walked >= walkback:
                    break
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
    identity = cfg.get("identity") or ["name"]

    def _pair_key(record: VulnRecord):
        name = record.name or ""
        if strip_suffix:
            name = strip_suffix.sub("", name)
        return (normalize_name(name), *(getattr(record, f) for f in pair["by"]))

    def _identity_key(record: VulnRecord):
        return tuple(
            normalize_name(getattr(record, f)) if f == "name" else getattr(record, f)
            for f in identity
        )

    def consolidate(records: list[VulnRecord], allow_duplicates: bool):
        log_lines: list[str] = []
        if pair:
            records, lines = dedupe(records, _pair_key,
                                    merge_instances=bool(pair.get("merge_instances")))
            log_lines += lines
        for record in records:
            mapped = severity_map.get(record.severity)
            if mapped:
                record.severity = mapped
        if not allow_duplicates:
            records, lines = dedupe(records, _identity_key)
            log_lines += lines
        return records, log_lines

    return consolidate


def load_profile(config_path: Path) -> ScannerProfile:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        record_type = RECORD_TYPES[cfg.get("record", "generic")]
        return ScannerProfile(
            name=cfg["name"],
            source=cfg["source"],
            record_type=record_type,
            marker=re.compile(cfg["marker_pattern"],
                              re.IGNORECASE if cfg.get("marker_ignorecase") else 0),
            prompt_path=config_path.parent / cfg["prompt"],
            max_vulns_per_chunk=int(cfg["max_vulns_per_chunk"]),
            segment=_build_segmenter(cfg),
            consolidate=_build_consolidator(cfg),
        )
    except KeyError as exc:
        raise ValueError(f"Scanner config {config_path} is missing field {exc}") from exc
