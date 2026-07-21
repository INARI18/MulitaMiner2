"""Deterministic instances annotator for Tenable WAS ground-truth baselines.

Parses the `Instances (N)` blocks of a Tenable PDF with plain rules (no LLM,
no cost) and writes a COPY of the baseline XLSX with the `instances` column
regenerated from what the PDF actually contains. The original file is never
touched — review the generated copy and replace manually if you approve.

Motivation (2026-07-21 analysis): the hand-annotated instances were unreliable
in both directions — JuiceShop had input_type values that do not exist in the
PDF (annotated from the Tenable UI/XML), bWAAP had only 7/64 findings
annotated. A deterministic, reviewable parse of the PDF is the defensible
ground truth for a PDF-extraction tool.

Usage:
    uv run python tools/annotate_instances.py resources/tenable/TenableWAS_JuiceShop.pdf \
        resources/tenable/TenableWAS_JuiceShop.xlsx
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from mulitaminer2.reader import extract_pdf
from mulitaminer2.scanners import get_scanner

PLUGIN_RE = re.compile(r"VULNERABILITY\s+\w+\s+PLUGIN\s+ID\s+(\d+)", re.IGNORECASE)
REQUEST_RE = re.compile(r"^([A-Z]+)\s+\S+\s+(HTTP/[\d.]+)\s*$")
STATUS_RE = re.compile(r"^HTTP/[\d.]+\s+(\d{3})\b")
CONTENT_TYPE_RE = re.compile(r"^content-type:\s*([^;]+)", re.IGNORECASE)

# Labels that end a PROOF/OUTPUT text section.
_LABELS = {"INSTANCE", "PROOF", "OUTPUT", "IDENTIFICATION", "HTTP INFO",
           "REQUEST MADE", "REQUEST HEADERS", "RESPONSE HEADERS"}
_INLINE = {"INPUT TYPE": "input_type", "INPUT NAME": "input_name", "PAYLOAD": "payload"}

_EMPTY = {
    "instance": "", "input_type": "", "input_name": "", "payload": "",
    "proof": "", "output": "", "request_method": "", "http_status_code": None,
    "http_protocol": "", "response_content_type": "",
}


def _clean(value: str) -> str:
    value = value.strip()
    return "" if value == "-" else value  # hyphen-only means empty (report idiom)


def parse_instances(block_text: str) -> list[dict]:
    """One pass over an Instances block; a new INSTANCE label opens a dict."""
    instances: list[dict] = []
    current: dict | None = None
    mode: str | None = None  # None | proof | output | response_headers

    def text_target() -> list[str]:
        return current.setdefault(f"_{mode}_lines", [])

    lines = block_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        upper = line.upper()

        if upper == "INSTANCE":
            current = dict(_EMPTY)
            instances.append(current)
            mode = None
            if i + 1 < len(lines):
                current["instance"] = _clean(lines[i + 1])
                i += 1
        elif current is None:
            pass  # header lines before the first INSTANCE
        elif upper == "PAYLOAD":
            # Standalone label: the payload value is the next line.
            mode = None
            if i + 1 < len(lines) and lines[i + 1].strip().upper() not in _LABELS:
                current["payload"] = _clean(lines[i + 1])
                i += 1
        elif any(upper.startswith(label) for label in _INLINE) and (
            inline := next(label for label in _INLINE if upper.startswith(label))
        ):
            current[_INLINE[inline]] = _clean(line[len(inline):])
            mode = None
        elif upper in ("PROOF", "OUTPUT"):
            mode = upper.lower()
        elif upper == "REQUEST MADE":
            mode = None
            if i + 1 < len(lines) and (m := REQUEST_RE.match(lines[i + 1].strip())):
                current["request_method"] = m.group(1)
                current["http_protocol"] = m.group(2)
                i += 1
        elif upper == "RESPONSE HEADERS":
            mode = "response_headers"
        elif upper in _LABELS:
            mode = None
        elif mode in ("proof", "output") and line:
            text_target().append(line)
        elif mode == "response_headers" and line:
            if m := STATUS_RE.match(line):
                current["http_status_code"] = int(m.group(1))
            elif m := CONTENT_TYPE_RE.match(line):
                current["response_content_type"] = _clean(m.group(1))
        i += 1

    for inst in instances:
        for key in ("proof", "output"):
            collected = inst.pop(f"_{key}_lines", [])
            inst[key] = _clean(" ".join(collected))
    return instances


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("xlsx", type=Path)
    args = ap.parse_args()

    profile = get_scanner("tenable")
    doc = extract_pdf(args.pdf)
    blocks = profile.segment(doc.text)

    by_plugin: dict[int, list[dict]] = {}
    for block in blocks:
        if "INSTANCE" not in block.text.upper():
            continue
        m = PLUGIN_RE.search(block.text)
        if not m:
            continue
        parsed = parse_instances(block.text)
        if parsed:
            by_plugin.setdefault(int(m.group(1)), []).extend(parsed)

    df = pd.read_excel(args.xlsx)
    plugin_col = next(c for c in df.columns if c.lower() == "plugin")
    inst_col = next(c for c in df.columns if c.lower() == "instances")
    matched = 0
    for idx, row in df.iterrows():
        plugin = row[plugin_col]
        if pd.notna(plugin) and int(plugin) in by_plugin:
            df.at[idx, inst_col] = repr(by_plugin[int(plugin)])
            matched += 1
        else:
            df.at[idx, inst_col] = repr([])

    out = args.xlsx.with_name(args.xlsx.stem + "_instances_generated.xlsx")
    df.to_excel(out, index=False)

    total = sum(len(v) for v in by_plugin.values())
    print(f"{len(blocks)} blocks -> {len(by_plugin)} findings with instances, "
          f"{total} instance objects; {matched}/{len(df)} baseline rows filled")
    for field in ("input_type", "input_name", "payload", "proof", "output",
                  "request_method", "http_status_code", "response_content_type"):
        filled = sum(1 for v in by_plugin.values() for i in v if i.get(field) not in ("", None))
        print(f"  {field:22s} {filled}/{total}")
    print(f"\nwrote {out}  (original untouched — review, then replace manually)")


if __name__ == "__main__":
    main()
