# Architecture

## Pipeline

![MulitaMiner pipeline](imgs/pipeline.svg)

All intermediate state flows in memory as typed Pydantic objects. Disk is
touched only for final run artifacts and optional `--debug` dumps.

## Modules

| Module | Responsibility |
| --- | --- |
| `pdf_reader.py` | PDF text extraction (pypdfium2 default, pdfplumber fallback) + cleanup |
| `scanner_engine.py` | Builds a ScannerProfile (segmenter + consolidator) from a JSON config |
| `chunking.py` | Packs whole blocks into token-budgeted chunks; blocks are never split |
| `llm.py` | One OpenAI-compatible client; structured output; usage accounting |
| `extraction.py` | Block-anchored loop: block_id reconciliation, shrinking retries, truncation |
| `consolidate.py` | Pairing, severity normalization, merge of fully identical records |
| `models.py` | VulnRecord and subclasses; the LLM contract is derived from them |
| `writers.py` / `exporters/` | results.json plus the `--export` formats |
| `prioritization.py` | KEV/EPSS/SSVC remediation queue over a run's results.json |
| `pipeline.py` | Composes the stages into one run and writes the artifacts |
| `cli.py` | Typer commands; thin consumer of the library |
| `settings.py` | Calibrated tunables |

## Key design rules

- **Block-anchored extraction**: segmentation determines the finding count
  deterministically before any LLM call. Each block carries an id; the model
  must return exactly one record per id. Missing ids are re-sent in smaller
  groups (4, then 2, then 1); unknown or duplicate ids are dropped with a
  warning. The raw output count therefore equals the report's marker count.
- **Typed end to end**: records are born validated from structured LLM output
  and stay objects until serialization. Post-validation writes are also
  schema-checked.
- **Failures are declared, never silent**: dropped blocks, truncated oversized
  blocks and merges all land in `run.json` warnings and merge log.
- **Scanner knowledge lives in one place**: the JSON config. The engine
  interprets it; no scanner-specific Python.

## Data flow objects

`Block` (one finding segment with host/port context), `Chunk` (group of whole
blocks), `VulnRecord` (validated record), `RunResult` (records + usage +
warnings). All in `models.py`.
