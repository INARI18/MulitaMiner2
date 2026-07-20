# MulitaMiner2 — Core Implementation Plan

**Spec:** `docs/superpowers/specs/2026-07-20-mulitaminer2-core-design.md`
**Status tracking:** update the checkbox and the *State* line of each phase as
work progresses, so any future session can resume from the exact point.

Conventions for every phase:

- All code, comments, docstrings, tests, and commit messages in English.
- One commit (or a few focused ones) per phase, message prefixed by area.
- A phase is done only when its **Verify** step passes.
- v1 reference material lives at `../MulitaMiner` (read-only; NEVER read `.env`).

---

## Phase 0 — Project scaffold

- [ ] `pyproject.toml` managed by `uv`: package `mulitaminer2` (src layout),
  Python `>=3.11`, deps: `pydantic>=2`, `openai`, `typer`, `tiktoken`,
  `pdfplumber`, `pypdfium2`, `python-dotenv`, `pandas`, `openpyxl`.
  Dev group: `pytest`, `ruff`, `mypy`.
- [ ] Package skeleton with empty modules per spec §2; `cli.py` with a stub
  Typer app exposing `--help`.
- [ ] `.env.example` with variable NAMES only (mirror v1's `.env.example`,
  which is safe to read — never the real `.env`).
- [ ] Console script `mulitaminer2 = mulitaminer2.cli:app`.

**Verify:** `uv sync` succeeds; `uv run mulitaminer2 --help` prints usage;
`uv run pytest` runs (0 tests is fine).
**State:** DONE (commit 033438f). Notes: `uv` lives at `~\.cargo\bin\uv.exe`
(not on PATH); venv is CPython 3.13. Model profiles must accept legacy v1 env
var names (`API_KEY_DEEPSEEK` …) as fallbacks — the user's `.env` (copied,
never read) uses them.

## Phase 1 — Data models and settings

- [ ] `models.py`: `VulnRecord` + `OpenVASRecord`/`TenableRecord`, field names
  and types ported from v1 `src/mulitaminer/configs/vuln_schema.py` (read it
  for the authoritative field list). `source` has no default from the LLM —
  it is stamped by the pipeline. Also `Block`, `Chunk`, `BlockExtraction`
  (the LLM response item: `block_id` + record fields), `RunResult`.
- [ ] `settings.py`: chunk safety margin 0.85, char ceiling floor 30_000,
  default retry rounds 2, etc. — each with a provenance comment naming the v1
  origin (`configs/constants.py`).

**Verify:** `pytest tests/test_models.py` — validation accepts a known-good
record dict, rejects wrong types, `source` stamping works.
**State:** DONE (9 tests passing). `extraction_model_for()` derives the LLM
contract from the record type (block_id + LLM-produced fields, extra=forbid).

## Phase 2 — PDF reader with competing backends

- [ ] Copy baseline resources from v1 `resources/baselines/` (OpenVAS +
  Tenable PDF/XLSX pairs) into `resources/baselines/`.
- [ ] `reader.py`: `ExtractedDoc` (page texts + full layout text),
  `PdfBackend` protocol, `PdfplumberBackend` (port the layout-preserving
  extraction from v1 `readers/pdf_extraction.py`, in memory — no
  visual-layout file), `Pdfium2Backend`.
- [ ] `tools/compare_backends.py`: for each baseline PDF × backend, count
  scanner-marker matches and print a comparison table.

**Verify:** `pytest tests/test_reader.py` (both backends extract non-empty
text from a baseline PDF); run `compare_backends.py` — record results in this
file, pick the default backend, and note the decision here.
**State:** DONE. Bake-off results (2026-07-20): marker counts IDENTICAL across
backends on all 5 baseline PDFs (OpenVAS: 34/59/116; Tenable: 128/152);
pypdfium2 is 10-40x faster (e.g. 0.6s vs 21.8s on TenableWAS_JuiceShop).
**Decision: pypdfium2 is the default backend**; pdfplumber stays as fallback
via `--pdf-backend`. v1's heuristic sentence-continuation merge was not ported
(explicit continuation markers are stripped; parity run guards this).

## Phase 3 — Scanner profiles and segmentation

- [ ] `scanners/profile.py`: frozen `ScannerProfile` dataclass (spec §5).
- [ ] `scanners/openvas.py`: marker `^\s*(?:Critical|High|Medium|Low|Log)\s+\(CVSS:`
  (break-one-line-early rationale in a comment), header-layout patterns ported
  from v1 (`readers/pdf_extraction.py` + `scanners/openvas.py` HEADER_REGEX
  variants), host recovery via `Host scan start`, `max_vulns_per_chunk=4`.
- [ ] `scanners/tenable.py`: marker
  `VULNERABILITY\s+(CRITICAL|HIGH|MEDIUM|LOW|INFO)\s+PLUGIN\s+ID\s+\d+`,
  BASE+INSTANCES pairing, `max_vulns_per_chunk=3`.
- [ ] `scanners/__init__.py`: `SCANNERS` dict.
- [ ] Prompts: port v1 `configs/prompts/{openvas,tenable}_prompt.txt`,
  translate to English, REMOVE the `source` field, ADD the block-ID contract
  (one record per `### BLOCK n`).
- [ ] Fixtures: real text excerpts extracted from the baseline PDFs.

**Verify:** `pytest tests/test_segmentation.py` — block counts on baseline
fixtures match the known finding counts from the ground-truth XLSX; severity
header line is INSIDE its block (the NVT lesson).
**State:** DONE. v2 Blocks are FINDING-level (one per CVSS/VULNERABILITY
marker), unlike v1's port-section/severity-group blocks; port/host/severity
context travels as Block metadata rendered into the `### BLOCK` prompt header.
Tenable name walk-back pulls the name line(s) from above the header (stops at
sentence punctuation). Real-PDF counts verified: 34/59 OpenVAS, 152 Tenable;
host recovery works on the real JuiceShop report.

## Phase 4 — Chunk packer

- [ ] `chunking.py`: pack whole blocks into chunks under (token budget ×
  margin) AND char ceiling AND profile `max_vulns_per_chunk`. Never split a
  block; never overlap. `tiktoken` with chars-per-token fallback.

**Verify:** `pytest tests/test_chunking.py` — invariants: union of chunks ==
all blocks, no duplicates, budgets respected, oversized single block goes
alone into its own chunk with a warning.
**State:** DONE (5 tests). Token budget is derived from the model's OUTPUT cap
(extraction output mirrors input, so output is the binding constraint).

## Phase 5 — LLM client and model profiles

- [ ] `llm.py`: `ModelProfile` (spec §8, `api_key_env: str | None`),
  `MODELS` dict with profiles: `deepseek` (cloud, primary test model),
  `gpt-4o-mini`, `gpt-4o`, `groq-llama-3.3-70b`, `ollama` (generic,
  `--model-name` passthrough), `lmstudio` (generic). Prices from v1
  `reporting/tokens_cost.py` LLM_PRICES.
- [ ] Client: chat call with JSON-schema structured output when
  `supports_json_schema`, else `json_object` + validation; strip markdown
  fences and `<think>…</think>`; SDK retries for transport; fatal auth/quota
  errors raise `FatalLLMError` with actionable message; token usage captured
  per call.

**Verify:** `pytest tests/test_llm.py` with a stubbed transport — schema mode,
json_object fallback, think-tag stripping, keyless local profile, missing env
var for cloud profile raises.
**State:** DONE (8 tests). DeepSeek profile: deepseek-v4-flash via /v1,
json_object mode. Legacy v1 env names accepted as fallbacks. Few-shot examples
restored into both prompts after user review (v1 evidence: wording matters).

## Phase 6 — Block-anchored extraction

- [ ] `extraction.py`: render chunk prompt (`### BLOCK n` sections), call
  client, validate `BlockExtraction` list; exact ID reconciliation: missing →
  re-send only those blocks (≤2 rounds) then warn; unknown/duplicate → drop
  with warning. Stamp `source` from profile. Per-chunk INFO progress log.

**Verify:** `pytest tests/test_extraction.py` with a fake client scripted to
(a) succeed, (b) miss IDs then recover, (c) return unknown IDs — assert final
count == block count and warnings recorded.
**State:** DONE (7 tests). Targeted retry re-packs only unresolved blocks;
port/protocol backfilled from Block context when the LLM returns null.

## Phase 7 — Consolidation and writers

- [ ] `consolidate.py`: one identity function (normalized name + host + port),
  rules seeded from v1 `scanners/consolidation.py` (field-count-based winner
  selection; keep the cvss=0.0 nuance); Tenable instance merge. Toggled by
  `allow_duplicates`.
- [ ] `writers.py`: `results.json` (schema-ordered fields), `results.xlsx`,
  `results.csv` — columns derived from the record model, never hardcoded
  (v1 lesson).

**Verify:** `pytest tests/test_consolidate.py test_writers.py`.
**State:** DONE (11 tests). v2 semantics simplified vs v1's activation matrix:
Tenable base+instances pairing ALWAYS runs (structure, not dedup);
--allow-duplicates only skips duplicate merging. Fuzzy name matching
(v1 rapidfuzz pass) intentionally deferred — revisit if parity shows misses.

## Phase 8 — Pipeline, CLI, run artifacts

- [ ] `pipeline.py`: `run(config) -> RunResult` composing all stages in
  memory; writes `outputs/runs/<utc-ts>_<stem>_<model>/` with `results.*`,
  `run.json` (config snapshot, tokens, cost, duration, warnings); `--debug`
  additionally dumps layout text, block boundaries, chunk contents, raw LLM
  traffic to the same directory.
- [ ] `cli.py`: `extract`, `models`, `scanners` commands (spec §11); logging
  setup (INFO console / DEBUG file).

**Verify:** `pytest tests/test_pipeline.py` end-to-end with fake client (no
network); manual: `uv run mulitaminer2 extract` on a baseline PDF with
`--model deepseek` — see Phase 9.
**State:** DONE (55 tests total). Without --debug a run dir contains exactly
results.json + run.json (in-memory rule verified by test).

## Phase 9 — Live validation (DeepSeek cloud) and v1 parity

- [ ] Live smoke: extract `resources/baselines/openvas/OpenVAS_JuiceShop.pdf`
  with `deepseek`; assert run completes, records validate, raw count ==
  marker count (warnings allowed).
- [ ] `tools/compare_v1_v2.py`: load a v1 output JSON and a v2 `results.json`,
  compare record counts and per-name overlap; print a verdict table.
- [ ] Run v1 (old repo) once on the same PDF/model for the comparison.
  Acceptance: v2 coverage ≥ v1, v2 raw count closer to ground truth.
- [ ] Record both results in this file.

**State:** not started

## Phase 10 — README and publishing

- [ ] `README.md` (English): what it is, install (`uv sync`), quickstart,
  supported models/scanners, `.env` setup, debug mode.
- [ ] Push to a **private repo on the user's personal GitHub account** (not
  AnonShield): user creates the empty repo or we install `gh` — ask when
  reaching this step.
- [ ] Tag nothing yet; versioning starts at `2.0.0-alpha` in `pyproject.toml`.

**State:** not started
