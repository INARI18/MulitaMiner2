"""Standalone experiment (NOT part of the core pipeline).

Runs a NuExtract-family model with its NATIVE template prompt instead of the
tool's general instruct prompt, to test whether it fills the body fields that
the general prompt leaves empty. Kept out of src/mulitaminer on purpose.

It reuses the tool's segmenter + record schema, does ONE call per block (NuExtract
1.5 fills one object per call), and writes a results.json in the tool's format so
`mulitaminer evaluate <out_dir>` can score it exactly like a normal run.

Usage:
    uv run python experiments/small_model_study/nuextract_native.py <scanner> <report.pdf> <model_key> <out_dir>
    # e.g. ... openvas resources/openvas/OpenVAS_JuiceShop.pdf nuextract /tmp/nu_native
    uv run mulitaminer evaluate <out_dir> --baseline resources/openvas/OpenVAS_JuiceShop.xlsx
"""
from __future__ import annotations

import json
import sys
import typing
from pathlib import Path

from openai import OpenAI

from mulitaminer.llm import get_model
from mulitaminer.models import _is_llm_produced
from mulitaminer.pdf_reader import extract_pdf
from mulitaminer.scanner_engine import get_scanner

# Severity comes from the report structure (block header), not the model, so we
# backfill it before validating — the normal pipeline gets it via schema-guided
# decoding, which raw NuExtract completions do not have.
_SEV_TIERS = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "LOG", "INFO"}
_QUALYS_SEV = {"1": "INFO", "2": "LOW", "3": "MEDIUM", "4": "HIGH", "5": "CRITICAL"}


def _backfill_context(data: dict, block) -> None:
    """Fill severity/port/protocol/cvss from block context so free-form model
    output validates against the strict record schema (these are report
    metadata, not fields NuExtract is being tested on)."""
    data["host"] = block.host
    sev = (block.severity_hint or "").strip()
    sev = _QUALYS_SEV.get(sev, sev.upper())
    if sev in _SEV_TIERS:
        data["severity"] = sev
    if data.get("port") in (None, "") and block.port is not None:
        data["port"] = block.port
    if data.get("protocol") not in ("tcp", "udp"):
        data["protocol"] = block.protocol if block.protocol in ("tcp", "udp") else None
    cvss = data.get("cvss")
    if isinstance(cvss, str):
        try:
            data["cvss"] = float(cvss)
        except ValueError:
            data["cvss"] = None


def build_template(record_type) -> dict:
    """Empty-value NuExtract template from the record schema ("" text, [] list)."""
    tmpl: dict = {}
    for name, f in record_type.model_fields.items():
        if not _is_llm_produced(f):
            continue
        key = f.alias or name
        origin = typing.get_origin(f.annotation)
        if origin in (list, tuple, set):
            tmpl[key] = []
        elif origin is dict or f.annotation is dict:
            tmpl[key] = {}
        else:
            tmpl[key] = ""
    return tmpl


def main() -> None:
    scanner, pdf, model_key, out_dir = sys.argv[1:5]
    profile = get_scanner(scanner)
    mp = get_model(model_key)
    client = OpenAI(base_url=mp.base_url, api_key="local")

    template = build_template(profile.record_type)
    tmpl_str = json.dumps(template, indent=4, ensure_ascii=False)

    doc = extract_pdf(Path(pdf))
    blocks = profile.segment(doc.text)
    print(f"{len(blocks)} blocks; template fields: {list(template)}")

    records: list[dict] = []
    for i, block in enumerate(blocks):
        prompt = (f"<|input|>\n### Template:\n{tmpl_str}\n"
                  f"### Text:\n{block.text}\n\n<|output|>")
        out = client.completions.create(
            model=mp.model, prompt=prompt, temperature=mp.temperature,
            max_tokens=mp.max_output_tokens,
        ).choices[0].text.strip()
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            print(f"  block {i}: JSON parse failed; skipped")
            continue
        _backfill_context(data, block)
        try:
            rec = profile.record_type.model_validate(data)
            if not rec.source:
                rec.source = profile.source
            records.append(rec.model_dump(by_alias=True))
        except Exception as exc:  # noqa: BLE001 - experiment: log and move on
            print(f"  block {i}: validation failed: {exc}")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(records)}/{len(blocks)} records -> {out_path/'results.json'}")
    print(f"score it: uv run mulitaminer evaluate {out_dir} --baseline <baseline.xlsx>")


if __name__ == "__main__":
    main()
