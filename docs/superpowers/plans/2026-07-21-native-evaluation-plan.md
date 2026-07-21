# MulitaMiner2 — Native Evaluation (Phase 14) Implementation Plan

**Spec:** `docs/superpowers/specs/2026-07-21-native-evaluation-design.md`
**Status tracking:** update the checkbox and the *State* line of each phase as
work progresses, so any future session can resume from the exact point.

Conventions (same as the core plan):

- All code, comments, docstrings, tests, and commit messages in English.
- One commit (or a few focused ones) per phase, message prefixed by area.
- A phase is done only when its **Verify** step passes.
- v1 reference material lives at `../MulitaMiner` (read-only; NEVER read
  `.env`). Alignment logic reference: `src/metrics/common/aligner.py`,
  normalization: `src/metrics/common/normalization.py`.

---

## Phase E0 — Feeds cache relocation (companion fix, own commit)

- [ ] `settings.py`: `FEEDS_DIR = Path("feeds")` (repo root, CWD-relative by
  documented decision — see spec §9).
- [ ] `.gitignore`: add `feeds/`.
- [ ] `sync-feeds` prints the absolute cache path it wrote to.
- [ ] Adjust anything referencing `outputs/feeds` (tests, README).

**Verify:** `uv run pytest`; `uv run mulitaminer sync-feeds` writes to
`feeds/` and prints the path; `uv run mulitaminer prioritize <run>` still
works against the new location.
**State:** TODO.

## Phase E1 — Scorers

- [ ] `evaluation/scorers.py`: registry `SCORERS: dict[str, Scorer]` with
  `exact` (numeric-aware normalization), `set_f1`, `token_f1`, `rouge_l`
  (in-repo LCS F1), `bertscore` (lazy import; unavailable → registered with
  `available=False` and an actionable hint). Pair rules: empty×empty = 1.0
  (flagged vacuous), present×absent = 0.0.
- [ ] Text scorers vs structural scorers are distinguishable in the registry
  (the CLI `--metrics` filter applies only to text scorers).

**Verify:** `pytest tests/test_evaluation.py -k scorers` — hand-computed
values per scorer; vacuous and presence-mismatch rules; missing bert-score
does not crash.
**State:** TODO.

## Phase E2 — Schema-driven field mapping

- [ ] `evaluation/fields.py`: iterate `record_type.model_fields`, keep
  LLM-produced fields only (`host`/`source` excluded via `llm_produced`
  marker); infer metric kind from the annotation per spec §5 (Literal →
  exact, numeric → exact, str/list[str] → text, nested model/dict →
  structural recurse, list[Model] → structural sub-align).
- [ ] Overrides read from the scanner config JSON optional block
  `"evaluation": {"field_metrics": {...}}`; `"skip"` supported. Ship built-in
  overrides: openvas `references: set_f1`; tenable `references: set_f1`,
  `cvss: set_f1`.

**Verify:** `pytest -k fields` — inference for every field of both record
types matches the spec table; a dynamically added field gets the right
default; overrides (incl. skip) beat inference.
**State:** TODO.

## Phase E3 — Alignment

- [ ] `evaluation/align.py`: name normalization (port from v1
  `normalization.py`), composite keys (openvas `name|port|protocol`, tenable
  `name|severity|plugin`, `services` row-hash sentinel, float-port guard),
  similarity matrix `max(composite, fuzzy_name)`, Hungarian via
  `scipy.optimize.linear_sum_assignment`, threshold 0.7, mapping-debug rows,
  coverage (recall/precision + missed/spurious name lists).

**Verify:** `pytest -k align` — known pairs found; paraphrase above/below
threshold; duplicate names split by composite; surplus rows spurious; float
port and services cases.
**State:** TODO.

## Phase E4 — Loaders and orchestration

- [ ] `evaluation/__init__.py`: `evaluate_run(target, baseline=None,
  metrics="all", threshold=0.7) -> EvalResult`. Target resolution: run dir
  (results.json + run.json, baseline auto-discovery from `config.input`) or
  bare results.json file (`--baseline` required). Baseline XLSX loader:
  rows → dicts, `ast.literal_eval` for serialized cells (fallback raw
  string), `<stem>_instances_generated.xlsx` merge for the `instances`
  column (provenance recorded). Structural scoring for nested fields
  (sub-align instances by `instance` URL fuzzy match, recurse per sub-field).
- [ ] Baseline columns outside the record model → `unevaluated_baseline_columns`.

**Verify:** `pytest -k orchestration` — end-to-end on fabricated mini
baseline + results.json: expected coverage, means, provenance, unevaluated
columns.
**State:** TODO.

## Phase E5 — Report writers

- [ ] `evaluation/report.py`: `evaluation.json` (meta incl. provenance +
  scorer availability, coverage, per-field × metric summary with
  mean/min/std/n/vacuous_n/fill rates, per-pair scores, mapping_debug,
  unevaluated columns) + `evaluation.md` (coverage, field × metric table,
  5 worst pairs per field, missed/spurious lists, notes) + console summary
  table.

**Verify:** `pytest -k report` — JSON structure and MD sections present with
expected numbers on the fabricated fixture.
**State:** TODO.

## Phase E6 — CLI and dependencies

- [ ] `pyproject.toml`: add `scipy`, `rapidfuzz` (main); dependency group
  `eval` with `bert-score`.
- [ ] `cli.py`: `evaluate <target> [--baseline] [--metrics all] [--threshold]`
  and `--list-metrics` (mirrors `formats` pattern). Unavailable requested
  scorer → actionable error; bare results target without `--baseline` →
  actionable error. Writes reports next to the target, prints summary.

**Verify:** `pytest tests/test_evaluation.py tests/test_cli.py`; `uv run
mulitaminer evaluate --list-metrics` shows availability truthfully.
**State:** TODO.

## Phase E7 — Live validation and bookkeeping

- [ ] Run `uv run mulitaminer evaluate` on the existing OpenVAS_JuiceShop
  deepseek run; sanity-check coverage 34/34 and that field means are in the
  ballpark of the v1-harness numbers recorded in core plan Phase 9 (BERTScore
  only if the `eval` group is installed — optional here).
- [ ] Run on a Tenable run to exercise instances_generated provenance and
  structural instance scoring.
- [ ] Core plan updates: Phase 14 state; Phase 11 caveat revised (instances
  GT re-annotated deterministically → reliable; generated files are the
  instances reference).
- [ ] README: evaluation section (command, metrics, `eval` group install).

**Verify:** both live evaluations produce sane `evaluation.json`/`.md`; 
`uv run pytest` fully green; docs updated.
**State:** TODO.
