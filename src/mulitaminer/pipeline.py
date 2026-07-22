"""End-to-end run: read -> segment -> extract -> consolidate -> write.

All intermediate state is in memory (spec §10). Disk is touched only for the
final run artifacts under outputs/runs/<timestamp>_<input>_<model>/ and, with
debug=True, inspection dumps in the same directory.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from mulitaminer import settings
from mulitaminer.extraction import extract_blocks
from mulitaminer.llm import FatalLLMError, LLMClient, get_model
from mulitaminer.models import RunResult, TokenUsage
from mulitaminer.pdf_reader import DEFAULT_BACKEND, extract_pdf
from mulitaminer.scanner_engine import detect_scanner, get_scanner
from mulitaminer.exporters import get_exporter
from mulitaminer.writers import write_json

log = logging.getLogger(__name__)


@dataclass
class RunConfig:
    input_path: Path
    scanner: str | None                # None = auto-detect (directory mode)
    model: str
    model_name: str | None = None      # override for generic local profiles
    pdf_backend: str = DEFAULT_BACKEND
    formats: tuple[str, ...] = ()      # extra exports (see exporters registry)
    output_dir: Path | None = None     # default: settings.OUTPUTS_DIR
    debug: bool = False

    def snapshot(self) -> dict:
        return {
            "input": str(self.input_path),
            "scanner": self.scanner,
            "model": self.model,
            "model_name": self.model_name,
            "pdf_backend": self.pdf_backend,
            "formats": list(self.formats),
            "debug": self.debug,
        }


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)


def _make_run_dir(config: RunConfig) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = config.output_dir or settings.OUTPUTS_DIR
    run_dir = root / f"{stamp}_{_slug(config.input_path.stem)}_{_slug(config.model)}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_directory(config: RunConfig, client: LLMClient | None = None) -> list[dict]:
    """Extract every PDF in the directory ``config.input_path``.

    Per file: resolve the scanner (config.scanner forces one for the whole
    batch; None auto-detects via marker census, skipping files no scanner
    uniquely claims), then run the normal pipeline into its own run dir.
    A failing file is recorded and the batch continues, EXCEPT for
    FatalLLMError (bad key/quota): every subsequent file would fail the
    same way, so the batch aborts.

    Returns one summary dict per PDF: file, status (ok|skipped|failed),
    scanner, detail, and run_dir/cost_usd when extracted.
    """
    pdfs = sorted(config.input_path.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDF files in {config.input_path}")

    summaries: list[dict] = []
    for pdf in pdfs:
        entry = {"file": pdf.name, "status": "failed", "scanner": config.scanner,
                 "detail": ""}
        summaries.append(entry)
        try:
            scanner_name = config.scanner
            if scanner_name is None:
                doc = extract_pdf(pdf, backend=config.pdf_backend)
                scanner_name, counts = detect_scanner(doc.text)
                if scanner_name is None:
                    positive = {k: v for k, v in counts.items() if v}
                    entry["status"] = "skipped"
                    entry["detail"] = (
                        f"ambiguous scanner markers {positive}" if positive
                        else "no scanner markers found"
                    )
                    log.warning("%s: skipped (%s)", pdf.name, entry["detail"])
                    continue
                log.info("%s -> %s (%d markers)", pdf.name, scanner_name,
                         counts[scanner_name])
            result, run_dir = run(replace(config, input_path=pdf,
                                          scanner=scanner_name), client=client)
            entry.update(
                status="ok", scanner=scanner_name, run_dir=str(run_dir),
                cost_usd=result.usage.cost_usd,
                detail=f"{len(result.records)} records in {result.duration_s}s",
            )
        except FatalLLMError:
            entry["detail"] = "fatal provider error; batch aborted"
            raise
        except Exception as exc:  # one bad file must not sink the batch
            entry["scanner"] = scanner_name
            entry["detail"] = f"{type(exc).__name__}: {exc}"
            log.error("%s: failed (%s)", pdf.name, entry["detail"])
    return summaries


def run(config: RunConfig, client: LLMClient | None = None,
        run_dir: Path | None = None, doc=None) -> tuple[RunResult, Path]:
    """Execute one extraction run. Returns (result, run directory).

    ``run_dir`` pins the output location (experiment harness). ``doc`` supplies
    an already-extracted document, so a caller can extract a PDF once and reuse
    it across runs (pdfium is not thread-safe, so this also avoids concurrent
    extraction of the same file)."""
    started = time.perf_counter()
    profile = get_scanner(config.scanner)
    if client is None:
        client = LLMClient(get_model(config.model), model_name=config.model_name)

    if run_dir is None:
        run_dir = _make_run_dir(config)
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
    file_handler = None
    if config.debug:
        file_handler = logging.FileHandler(run_dir / "debug.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(file_handler)

    try:
        if doc is None:
            doc = extract_pdf(config.input_path, backend=config.pdf_backend)
        blocks = profile.segment(doc.text)
        if not blocks:
            raise ValueError(
                f"No finding blocks found in {config.input_path.name} with the "
                f"'{profile.name}' scanner profile; wrong --scanner?"
            )
        log.info("Segmented %d finding blocks", len(blocks))

        usage = TokenUsage()
        debug_sink: list | None = [] if config.debug else None
        records, warnings = extract_blocks(blocks, profile, client, usage, debug_sink)
        raw_count = len(records)
        raw_records = list(records)
        records, merge_log = profile.consolidate(records)
        log.info(
            "Extracted %d/%d blocks; %d records after consolidation",
            raw_count, len(blocks), len(records),
        )

        result = RunResult(
            records=records,
            warnings=warnings,
            usage=usage,
            duration_s=round(time.perf_counter() - started, 2),
            block_count=len(blocks),
            chunk_count=0,  # informational; per-round chunking varies
            config=config.snapshot(),
        )

        write_json(records, run_dir / "results.json")
        if merge_log:
            # Consolidation changed something: keep the pre-consolidation
            # records so every merge decision stays auditable offline.
            write_json(raw_records, run_dir / "results.raw.json")
        for fmt in config.formats:
            get_exporter(fmt)(records, profile.record_type, run_dir)

        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "config": result.config,
                    "block_count": result.block_count,
                    "raw_record_count": raw_count,
                    "final_record_count": len(records),
                    "usage": usage.model_dump(),
                    "duration_s": result.duration_s,
                    "warnings": warnings,
                    "merge_log": merge_log,
                    "pdf": {"pages": doc.page_count, "backend": doc.backend},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if config.debug:
            (run_dir / "layout.txt").write_text(doc.text, encoding="utf-8")
            (run_dir / "blocks.txt").write_text(
                "\n\n".join(f"--- BLOCK {b.id} (host={b.host} port={b.port}/"
                            f"{b.protocol} sev={b.severity_hint}) ---\n{b.text}"
                            for b in blocks),
                encoding="utf-8",
            )
            with (run_dir / "llm_traffic.jsonl").open("w", encoding="utf-8") as fh:
                for entry in debug_sink or []:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return result, run_dir
    finally:
        if file_handler:
            logging.getLogger().removeHandler(file_handler)
            file_handler.close()
