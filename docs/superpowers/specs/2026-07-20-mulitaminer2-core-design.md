# MulitaMiner2 — Core Extraction Design

**Date:** 2026-07-20
**Status:** Approved (pending final spec review)
**Scope:** v1.0 of the rewrite — the extraction core only. Metrics, prioritization,
and batch experiments are later, separate projects.

## 1. Context and goals

MulitaMiner (the v1 repo, kept as backup/reference at `../MulitaMiner`) extracts
structured vulnerability records from security-scanner PDF reports using LLMs.
It works, but carries structural debt: free-text LLM output recovered by six
parsing heuristics, `dict`-based data flow, scanner knowledge triplicated across
JSON configs / hardcoded regexes / strategy classes, a God-orchestrator, 328
`print()` calls, and silent failure paths.

MulitaMiner2 is a clean rewrite in a new repository that keeps the empirically
earned domain knowledge and fixes the structure. Everything — code, comments,
docstrings, docs, commit messages — is written in **English**.

**Goals**

- Same capability as v1's extraction core: PDF report → structured vulnerability
  records (JSON/XLSX/CSV), for OpenVAS and Tenable WAS, using cloud (OpenAI,
  Groq, DeepSeek) or local (Ollama, LM Studio) models.
- Raw LLM output count should match the report's actual finding count as closely
  as possible **even without deduplication** (a known v1 weakness). Addressed by
  block-anchored extraction (§6).
- Typed data end to end; structured LLM output; single source of truth per
  scanner; real logging; per-run artifact directory.
- Library-first: the package is importable and testable without the CLI.

**Non-goals (v1.0)**

- Evaluation metrics (BERTScore/ROUGE/F1), KEV/EPSS/SSVC prioritization,
  batch experiment runner, HTML reports, CAIS export.
- Scanners beyond OpenVAS and Tenable WAS (the design makes adding them cheap).

## 2. Package layout

```
MulitaMiner2/
├── pyproject.toml            # uv-managed; Python 3.11+
├── CLAUDE.md                 # copied from v1 (project principles)
├── .claude/settings.local.json
├── .env                      # copied from v1, gitignored, NEVER read by tooling
├── .env.example              # variable names only
├── src/mulitaminer2/
│   ├── models.py             # VulnRecord + Block/Chunk/RunResult (Pydantic v2)
│   ├── settings.py           # tunables with provenance comments (v1 calibrations)
│   ├── reader.py             # PdfReader protocol + backends (§4)
│   ├── scanners/
│   │   ├── __init__.py       # SCANNERS dict (plain registry)
│   │   ├── profile.py        # ScannerProfile dataclass
│   │   ├── openvas.py        # profile + segmentation (single source of truth)
│   │   ├── openvas_prompt.txt
│   │   ├── tenable.py
│   │   └── tenable_prompt.txt
│   ├── chunking.py           # pack whole blocks into token-budgeted chunks
│   ├── llm.py                # one OpenAI-compatible client + model profiles
│   ├── extraction.py         # block-anchored extract loop + targeted retry
│   ├── consolidate.py        # single vulnerability-identity definition + merge
│   ├── writers.py            # json / xlsx / csv
│   ├── pipeline.py           # compose stages → RunResult
│   └── cli.py                # Typer app
├── tests/
│   ├── fixtures/             # real text excerpts from baseline PDFs
│   └── test_*.py
├── resources/baselines/      # PDFs + ground-truth XLSX copied from v1
├── tools/compare_v1_v2.py    # golden parity script (§9)
└── docs/superpowers/specs/   # this spec + implementation plan
```

Design rule: each module has one purpose, a typed interface, and no knowledge of
the CLI. Adding a scanner = one JSON config + one prompt file, no Python
(revised after user review — see §5).

## 3. Data models (`models.py`)

- `VulnRecord` (Pydantic v2): `name`, `description`, `severity`, `cvss`, `port`,
  `host`, `solution`, `references`, plus scanner-specific subclasses
  (`OpenVASRecord`, `TenableRecord` with `plugin_details` / `instances`).
  Field names and types are seeded from v1's `configs/vuln_schema.py`.
- `source` is **not** produced by the LLM and **not** part of the prompt schema:
  it is stamped in code from the active `ScannerProfile` (user decision — the
  scanner is already known from `--scanner`).
- `Block`: one marker-delimited segment (`id: int`, `text`, `page_hint`).
- `Chunk`: ordered list of whole `Block`s + token estimate.
- `RunResult`: records, token/cost totals, duration, warnings, config snapshot.

Records are born validated (from the LLM's structured output) and stay objects
until serialization. No `list[dict]` plumbing.

## 4. PDF reading (`reader.py`)

Backend choice is an open experiment by design (rewrite = chance to improve).
A minimal protocol:

```python
class PdfBackend(Protocol):
    def extract(self, path: Path) -> ExtractedDoc: ...  # page texts + layout dump
```

Two thin backends (~30–50 lines each):

- **`pdfplumber`** — MIT license; the v1 reference. Its text output is what the
  v1 layout regexes were calibrated against.
- **`pypdfium2`** — new candidate: fast, permissively licensed (PyMuPDF was
  ruled out: AGPL conflicts with this project's MIT license).

An early implementation task runs both backends over the baseline PDFs and
compares (a) marker-line counts against known finding counts and (b) header-line
integrity. The winner becomes the default; the other stays available via
`--pdf-backend`. Note: scanner **marker** patterns are inherent to the scanner's
report format and survive any reasonable extractor; only the **layout header**
regexes are extractor-sensitive and may need recalibration for pypdfium2.

## 5. Scanner profiles (`scanners/`)

One `ScannerProfile` per scanner is the single source of truth (v1 spread this
across JSON config + hardcoded regexes in `tokens.py` + a strategy class):

```python
@dataclass(frozen=True)
class ScannerProfile:
    name: str                      # stamped into VulnRecord.source
    record_type: type[VulnRecord]
    marker: re.Pattern             # block delimiter
    header_patterns: list[re.Pattern]  # layout headers to strip/parse
    prompt_path: Path
    max_vulns_per_chunk: int
    consolidate: Callable[[list[VulnRecord]], list[VulnRecord]]
```

**Revised after user review (2026-07-20):** the profile is BUILT FROM a JSON
config by a generic engine (`scanners/engine.py`) — a lay user plugs a scanner
by dropping `<name>.json` + `<name>_prompt.txt` into `scanners/configs/` or a
directory named by `MULITAMINER2_SCANNERS_DIR`, no Python needed. Marker
pattern, name walk-back, context tracking, structural pairing, severity map
and duplicate identity are all config fields; `_`-prefixed keys carry the
empirical lessons as documentation. Unlike v1, the JSON is the WHOLE
definition (v1 split it between JSON, chunker regexes, and a strategy class).
A typed record subclass is optional (`record: "generic"` works without one).

Carried-over domain knowledge (verbatim, now inside the JSON configs):

- **OpenVAS** marker: `^\s*(?:Critical|High|Medium|Low|Log)\s+\(CVSS:` — breaks
  ONE line **before** the `NVT:` line so the `Severity (CVSS: X.Y)` header
  travels in the same block as its NVT. (v1 lesson: marking at `NVT:` left the
  severity in the previous chunk and the LLM guessed LOG — misclassification on
  Ingreslock/Telnet in bWAPP.) `max_vulns_per_chunk = 4`. Host recovery via the
  `Host scan start` line. Three known header-layout regex variants.
- **Tenable WAS** marker: `VULNERABILITY\s+(CRITICAL|HIGH|MEDIUM|LOW|INFO)\s+PLUGIN\s+ID\s+\d+`;
  BASE+INSTANCES pairs; merge instances with the same base finding.
  `max_vulns_per_chunk = 3`.

Prompts start from v1's `configs/prompts/*.txt`, translated/cleaned to English
where needed, minus the `source` field (§3).

## 6. Block-anchored extraction (`extraction.py`) — the key improvement

v1 lets the LLM *discover* vulnerabilities inside a chunk, so hallucinated
extras, boundary re-extractions, and missed findings silently skew the count.
v2 inverts this:

1. Segmentation by marker is deterministic → we know the exact candidate count
   **before** calling the LLM.
2. Each `Block` gets an explicit ID; the chunk prompt renders blocks as
   delimited sections (`### BLOCK 7`).
3. The response schema requires `block_id` on every record; the LLM's job is
   **field extraction per block, not discovery**.
4. Validation is exact, not heuristic:
   - missing IDs → re-send only those blocks in a smaller follow-up call
     (up to 2 rounds, then a warning in `RunResult`);
   - unknown/duplicate IDs → dropped with a warning.

Guarantee: raw output count == marker count (minus explicitly warned failures),
independent of deduplication. Duplicates in the output can then only reflect the
report itself (same finding on several hosts/ports), which is exactly what
`consolidate.py` handles semantically — one identity function
(name + host + port normalization, seeded from v1's consolidation rules),
toggled by `--allow-duplicates`.

## 7. Chunking (`chunking.py`)

Two phases, as in v1 (the shape was good):

1. Scanner profile segments the extracted text into `Block`s at marker lines.
2. Packer groups **whole blocks** into chunks subject to: model token budget ×
   safety margin (0.85, v1 calibration), char ceiling (30k floor, v1
   calibration), and the profile's `max_vulns_per_chunk`. Blocks are never
   split; chunks never overlap. Token counting via `tiktoken` with a
   chars-per-token fallback for non-OpenAI tokenizers.

All tunables live in `settings.py` with a comment naming their v1 origin.

## 8. LLM layer (`llm.py`)

One client class over the official `openai` SDK. Every supported provider —
OpenAI, Groq, DeepSeek, Ollama, LM Studio — speaks the OpenAI-compatible API,
so provider differences reduce to a `ModelProfile`:

```python
@dataclass(frozen=True)
class ModelProfile:
    key: str            # CLI name, e.g. "deepseek"
    model: str          # e.g. "deepseek-chat"
    base_url: str | None
    api_key_env: str | None  # env var NAME only; None for local servers
                             # (Ollama/LM Studio need no key — a dummy value
                             # is sent to satisfy the SDK). Cloud profiles
                             # fail fast with a clear message if the var is
                             # missing. The env var VALUE is only ever read
                             # by the SDK, never by tooling.
    context_window: int
    supports_json_schema: bool
    price_in / price_out: float  # USD per 1M tokens
    reasoning_tags: bool  # strip <think>…</think> (v1 lesson: Qwen3/DeepSeek-R1)
```

- Structured output: JSON Schema generated from the response model
  (`list[BlockExtraction]`), `strict` where supported, otherwise
  `json_object` mode + Pydantic validation. The only pre-parse cleanup kept
  from v1: strip markdown fences and `<think>` blocks. The six-stage heuristic
  parser and `json_repair` are gone.
- Transport retries (rate limit, network): the SDK's built-in exponential
  backoff. Fatal errors (auth, quota) raise immediately with actionable
  messages. Semantic retries are §6's targeted block re-sends.
- API keys come from `.env` via `python-dotenv`. Tooling and agents must
  **never read `.env` contents** — only `.env.example` documents variable names.
- **Local models need no API key.** Ollama and LM Studio profiles ship with
  `base_url` pointing at their default localhost ports and `api_key_env=None`.
  A custom `base_url` also covers any other OpenAI-compatible server (vLLM,
  llama.cpp, TGI), which is how HuggingFace-hosted models are run locally.
- **Deferred (not in v1.0):** v1's in-process HuggingFace provider
  (transformers/torch loaded inside the MulitaMiner process, `.[hf-local]`
  extra). Local models are served via Ollama/LM Studio instead — lighter
  install, better structured-output support. If a future experiment needs an
  HF model unavailable through those servers, add a second client
  implementation behind the same `llm.py` interface as an optional extra.

## 9. Testing and validation

- **Unit tests** (pytest): segmentation per scanner against fixture excerpts
  from the baseline PDFs; chunk packing invariants (budget respected, blocks
  whole, no overlap); structured-output validation incl. reasoning-tag
  stripping (recorded responses, no network); consolidation identity; writers.
- **Backend comparison test** (§4): marker counts per backend vs. known
  baseline finding counts.
- **Golden parity** (`tools/compare_v1_v2.py`): run v1 (old repo) and v2 on
  `resources/baselines/openvas/OpenVAS_JuiceShop.pdf` with the same model and
  compare record sets. Acceptance for v2: coverage equal or better, raw count
  closer to the baseline count than v1's.
- **Live smoke test** uses **DeepSeek cloud** (user-designated test provider):
  one small baseline PDF end to end, asserting count parity and schema
  validity.

## 10. Runs, logging, errors

- Each run writes to `outputs/runs/<UTC-timestamp>_<input-stem>_<model>/`:
  `results.json`, optional `results.xlsx`/`results.csv`, `run.json` (full
  config snapshot, token/cost totals, duration, warnings), `debug.log` when
  `--debug` (request/response payloads — replaces v1's llm_debug).
- Stdlib `logging`: clean INFO progress on console (per-chunk), DEBUG to file.
  No `print()`. No `except: pass`: config errors raise immediately; per-block
  extraction failures accumulate as warnings surfaced in the final summary.
- No PID-named files, no glob+rename, no `os.environ` as a data channel.
- **In-memory pipeline (explicit rule):** all intermediate state — extracted
  page text, visual layout, `Block`s, `Chunk`s, LLM payloads — flows between
  stages as in-memory objects. v1 round-tripped blocks through disk (wrote each
  block to a file, then re-read it) and did the same for the visual layout and
  token info; v2 does **no intermediate disk I/O on the happy path**. Disk is
  touched only for (a) the final run artifacts above and (b) optional debug
  dumps: with `--debug`, the extracted layout, block boundaries, chunk
  contents, and raw LLM requests/responses are also written to the run
  directory for inspection.

## 11. CLI (`cli.py`, Typer)

```
mulitaminer2 extract REPORT.pdf --scanner openvas --model deepseek
             [--xlsx] [--csv] [--allow-duplicates] [--pdf-backend NAME]
             [--output-dir DIR] [--debug]
mulitaminer2 models     # list model profiles
mulitaminer2 scanners   # list scanner profiles
```

Fresh, consistent flag names (v1's `--llm gpt4` → `gpt-4o-mini` mismatch is not
inherited: profile keys name the actual model).

## 12. Repository bootstrap and publishing

- Local: sibling folder `MulitaMiner2`, own git history (`main`), `uv` project,
  `CLAUDE.md` + `.claude/settings.local.json` copied from v1, `.env` copied
  without inspection, `.gitignore` excludes `.env`/`outputs/`/`.venv`.
- Remote: **private repository on the user's personal GitHub account** (not the
  AnonShield org). `gh` CLI is not installed; either the user creates the empty
  private repo on github.com and we push, or we install `gh` first.
- Versioning stance (user decision): v2 supersedes v1 via releases (2.0-style);
  no requirement to keep v1 reproducibility inside this repo.

## 13. Decisions log

| Decision | Choice | Why |
| --- | --- | --- |
| Scope v1.0 | Extraction core only | Avoid two half-finished tools |
| Providers | One OpenAI-compatible client | All 5 targets speak the same API |
| LangChain | Dropped | Used in only one v1 provider; unneeded weight |
| PDF backend | pdfplumber vs pypdfium2, decided by experiment | Rewrite is the chance to improve; PyMuPDF rejected (AGPL) |
| `source` field | Stamped from profile, not prompted | User idea; removes a hallucination surface |
| Count fidelity | Block-anchored extraction | User requirement: raw count ≈ baseline without dedup |
| Language | English everywhere | User requirement |
| Test provider | DeepSeek cloud | User designation |
| Intermediate state | In memory; disk only for results + `--debug` dumps | User requirement; v1 round-tripped blocks/layout through disk |
| Local models | Ollama/LM Studio (+ any OpenAI-compatible server), no API key | Same client path as cloud; keyless profiles |
| In-process HF inference | Deferred to a post-1.0 optional extra | Heavy torch dependency; servers cover the same models |
| Scanner definition | JSON config + generic engine (no Python per scanner) | User requirement: lay users plug scanners; JSON is the WHOLE definition, unlike v1 |
