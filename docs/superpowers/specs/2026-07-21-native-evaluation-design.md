# MulitaMiner2 — Native Evaluation Subsystem (Phase 14) Design

**Date:** 2026-07-21
**Status:** approved by user (brainstorming session), pending spec review
**Replaces:** the v1 metrics-harness bridge (`../MulitaMiner/src/metrics/`) for
evaluating v2 runs against the baseline ground-truth XLSX files.

## 1. Goal and scope

A lean, schema-driven evaluation subsystem that scores a single run
(`results.json`) against a human-annotated baseline XLSX and writes a
machine-readable + human-readable report into the run directory.

Decisions fixed during brainstorming:

- **Purpose:** paper + everyday dev regression. Light metrics (exact, set F1,
  token F1, ROUGE-L) always available; **BERTScore lives in an optional
  dependency group `eval`** (`uv sync --group eval`) because it pulls
  torch/transformers (~2 GB).
- **Alignment:** Hungarian only (optimal global assignment). No greedy port.
- **Tenable `instances` ground truth:** measured against the deterministic
  re-annotation files `<stem>_instances_generated.xlsx` (the user re-annotated
  the instances column deterministically from the PDF; it is no longer
  considered unreliable). Provenance recorded in the report.
- **Report:** `evaluation.json` + `evaluation.md`, written into the run dir.
- **CLI scope:** single-run `mulitaminer evaluate <run_dir>` now; multi-run
  aggregation / bootstrap CI / statistical tests are a later phase.
- **Schema independence (user requirement):** the evaluator never hardcodes
  field names. It derives the field list and the metric kind from the Pydantic
  record model's type annotations; per-field overrides live in the scanner
  config JSON. A field the user adds to the schema is evaluated with a
  sensible default without touching evaluator code.

Out of scope (explicitly): charts/PNG, multi-run aggregators, bootstrap CI,
statistical tests, inter-rater kappa, the v1 `field_f1`/severity-confusion
pipelines.

## 2. Package layout

```
src/mulitaminer/evaluation/
    __init__.py     # evaluate_run(run_dir, baseline=None, ...) -> EvalResult
    align.py        # composite keys, similarity matrix, Hungarian assignment
    fields.py       # Pydantic annotation -> metric kind; scanner-JSON overrides
    scorers.py      # registry {name: callable(a, b) -> float}
    report.py       # evaluation.json + evaluation.md writers
tests/test_evaluation.py
```

Follows the existing `exporters/` pattern: small modules, one responsibility
each, testable in isolation.

New dependencies: `scipy`, `rapidfuzz` (main group); `bert-score` (optional
group `eval`). ROUGE-L is implemented in-repo (plain LCS, ~30 lines) — no dep.

## 3. Data flow

```
run_dir/results.json ──┐
                       ├─→ load → align (Hungarian) → score per field → report
baseline XLSX ─────────┘                                (evaluation.json/.md)
```

1. **Extraction load:** `results.json` → `list[VulnRecord]` via
   `record_type_for_source` (the evaluator works on the Pydantic objects, not
   DataFrames — the record model stays the single source of truth).
2. **Baseline load:** XLSX rows → plain dicts. Cells holding serialized
   lists/dicts (the GT stores Python-repr strings, e.g. `instances`) are
   parsed with `ast.literal_eval`, falling back to the raw string on failure.
3. **Alignment** (`align.py`): see §4.
4. **Scoring** (`fields.py` + `scorers.py`): see §5.
5. **Report** (`report.py`): see §6.

## 4. Alignment (align.py)

Hungarian only. Build an `N_ext × N_base` similarity matrix where each cell is
`max(composite_key_score, fuzzy_name_score)`:

- **Composite keys** ported from v1 `metrics/common/aligner.py`:
  - openvas → `name|port|protocol`
  - tenable → `name|severity|plugin`
  - wildcard `*` for missing parts; per-part score 1.0 exact / 0.3 wildcard;
    incompatible parts → 0.
  - Keep the v1 special cases: the OpenVAS `"services"` sentinel name (hash
    the full row so distinct Services rows stay distinguishable) and the
    float-port guard (`8019.0` must normalize to `"8019"`, never `"80190"`).
- **Fuzzy name score:** `rapidfuzz.fuzz.ratio(normalized_a, normalized_b)/100`
  over v1-style normalized names (lowercase, strip punctuation/whitespace).
- Solve with `scipy.optimize.linear_sum_assignment` on `1 - similarity`;
  accept pairs with similarity ≥ **threshold 0.7** (v1 `FUZZY_THRESHOLD`).

Outputs: matched pairs, unmatched extraction rows (spurious), unmatched
baseline rows (missed), and a mapping-debug table (per extraction row: key,
matched baseline name, similarity, status) embedded in `evaluation.json`.

**Coverage falls out of alignment:** `matched/len(baseline)` (detection
recall), `matched/len(extraction)` (precision), plus the named lists of
missed/spurious findings.

## 5. Schema-driven field scoring (fields.py + scorers.py)

### Field selection

Iterate `record_type.model_fields`. Evaluate every LLM-produced field — this
includes `port`/`protocol`, whose block-context backfill is part of extraction
quality. Exclude the pipeline-stamped fields (`host`, `source`, marked
`llm_produced: False` in the model). Baseline columns that are
not in the record model (e.g. Tenable GT extras `http_info`,
`identification`) are not scored — they are listed in the report as
`unevaluated_baseline_columns`.

### Metric inference by annotation

| Annotation | Default metric |
| --- | --- |
| `Literal[...]` (severity, protocol) | `exact` |
| numeric (`int`, `float`, unions thereof) | `exact` (after numeric normalization: `8019.0` == `8019`) |
| `str` / `list[str]` | text: `token_f1` + `rouge_l` (+ `bertscore` when available) |
| nested model / `dict` (`plugin_details`) | structural: recurse field-by-field with these same rules, average |
| `list[Model]` (`instances`) | structural: sub-align items by key (`instance` URL, fuzzy), then recurse per sub-field |

`list[str]` defaults to text scoring (joined with newline). Fields whose items
are atomic identifiers need an override to `set_f1` (see below).

### Overrides

The scanner config JSON (already "the whole scanner definition") gains an
optional block:

```json
"evaluation": {
  "field_metrics": { "references": "set_f1", "cvss": "set_f1" }
}
```

- Values are scorer names or `"skip"`.
- Built-in configs ship overrides: openvas → `references: set_f1`;
  tenable → `references: set_f1`, `cvss: set_f1` (Tenable cvss is a list of
  CVSS strings).
- Inference covers any new field by type; overrides only where the default is
  wrong.

### Scorers (registry `{name: callable(a: str|Any, b: str|Any) -> float}`)

- `exact` — normalized equality (numbers compared numerically, strings
  stripped/lowercased).
- `set_f1` — F1 over normalized item sets.
- `token_f1` — bag-of-tokens F1.
- `rouge_l` — LCS-based F1, implemented in-repo.
- `bertscore` — lazy import; when `bert-score` is missing the scorer is
  registered as unavailable and the report notes "install the `eval` group".

Pair rules kept from v1: empty×empty = 1.0 (vacuous match);
present×absent = 0.0. **New:** the per-field summary counts vacuous matches
(`vacuous_n`) and reports both-side fill rates, so a real 1.0 is
distinguishable from an "both empty" 1.0.

## 6. Report (report.py)

**`evaluation.json`** (machine):

- `meta`: run dir, baseline path(s) + instances provenance
  (`instances_generated` file used or not), threshold, package version,
  scorer availability, UTC timestamp.
- `coverage`: matched / missed / spurious counts + name lists, recall,
  precision.
- `fields`: per field × metric → `{mean, min, std, n, vacuous_n,
  fill_rate_extraction, fill_rate_baseline}`.
- `pairs`: per matched pair → per-field per-metric scores.
- `mapping_debug`: alignment table (§4).
- `unevaluated_baseline_columns`: GT columns outside the schema.

**`evaluation.md`** (human): coverage summary; field × metric mean table;
the 5 worst-scoring pairs per field (name + score); missed and spurious name lists;
notes (instances provenance, unavailable scorers, unevaluated columns).

Console output: the field × metric summary table.

## 7. CLI

```
mulitaminer evaluate <run_dir> [--baseline PATH] [--threshold 0.7] [--no-bert]
```

- Baseline auto-discovery: `run.json → config.input`, swap extension to
  `.xlsx` in the same directory. If `<stem>_instances_generated.xlsx` exists
  alongside, the `instances` column is taken from it. `--baseline` overrides
  discovery entirely.
- `--no-bert`: skip BERTScore even when installed (it is the slow one — loads
  a transformer model).
- Writes `evaluation.json` + `evaluation.md` into the run dir; prints the
  summary table.

## 8. Testing (offline, no torch)

`tests/test_evaluation.py`:

- **align:** synthetic fixtures — known pairs all found; paraphrased name
  above threshold matches, below does not; duplicate names with different
  ports resolved via composite key; surplus extraction rows become spurious;
  float-port and `services` special cases.
- **fields:** inference for every field of both record types; a field added
  dynamically to a subclass gets the correct default; JSON override
  (including `skip`) beats inference.
- **scorers:** hand-computed known values per scorer; empty×empty = 1.0;
  present×absent = 0.0; missing bert-score → unavailable without crash.
- **end-to-end:** fabricated mini baseline XLSX + `results.json` →
  `evaluation.json`/`.md` with expected coverage and means.

## 9. Companion changes (separate commits, outside `evaluation/`)

1. **Feeds cache fix:** `FEEDS_DIR` moves from `outputs/feeds` (ephemeral,
   CWD-relative — user spotted the inconsistency) to
   `platformdirs.user_data_dir("mulitaminer")/feeds`. New dep `platformdirs`.
   Existing caches are simply re-synced (`mulitaminer sync-feeds`).
2. **Plan updates:** Phase 11 caveat revised — Tenable `instances` GT is now
   reliable via the deterministic re-annotation; Phase 14 state updated as
   work lands.
