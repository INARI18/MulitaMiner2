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
**State:** DONE (commit dd8ab3d). Existing outputs/feeds cache migrated by
moving the files; load_kev/load_epss verified against the new path; 80 tests
green. README needed no change (it never named the path).

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
**State:** DONE (8 tests). BERTScorer model cached per process; registry
carries kind + availability + hint; pair_score returns (score, vacuous).

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
**State:** DONE (6 tests). ScannerProfile gained `field_metric_overrides`
(tuple of pairs — frozen dataclass) read from the config's
evaluation.field_metrics; both builtin JSONs ship their overrides. FieldPlan
carries sub_model/is_list for structural recursion in E4.

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
**State:** DONE (7 tests). Design addition found by test: identical names on
different ports tie at fuzzy 1.0 and make the assignment arbitrary —
conflicting composite keys now scale name similarity by
KEY_CONFLICT_PENALTY=0.9 so composite-compatible pairings win. scipy +
rapidfuzz added to main deps here (E3 needs them; planned for E6).
Composite-key layouts keyed by record source (key_parts_for_source).

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
**State:** DONE (5 tests; 106 total green). Orchestration lives in
`runner.py` (re-exported from `__init__`) to keep modules single-purpose.
Structural list scoring: greedy item sub-align on the sub-model's first
field (Instance.instance URL), pair mean over leaf scores (numeric→exact,
text→token_f1), normalized by max(len_ext, len_base) so missing/spurious
items cost score. Scanner overrides resolved by record source via
all_scanners(). --metrics accepts aliases bert/rouge.

## Phase E5 — Report writers

- [ ] `evaluation/report.py`: `evaluation.json` (meta incl. provenance +
  scorer availability, coverage, per-field × metric summary with
  mean/min/std/n/vacuous_n/fill rates, per-pair scores, mapping_debug,
  unevaluated columns) + `evaluation.md` (coverage, field × metric table,
  5 worst pairs per field, missed/spurious lists, notes) + console summary
  table.

**Verify:** `pytest -k report` — JSON structure and MD sections present with
expected numbers on the fabricated fixture.
**State:** DONE (1 test; 107 total). evaluation.json carries generated_at +
tool_version in meta; MD embeds the same summary table the console prints.

## Phase E6 — CLI and dependencies

- [ ] `pyproject.toml`: add `scipy`, `rapidfuzz` (main); dependency group
  `eval` with `bert-score`.
- [ ] `cli.py`: `evaluate <target> [--baseline] [--metrics all] [--threshold]`
  and `--list-metrics` (mirrors `formats` pattern). Unavailable requested
  scorer → actionable error; bare results target without `--baseline` →
  actionable error. Writes reports next to the target, prints summary.

**Verify:** `pytest tests/test_evaluation.py tests/test_cli.py`; `uv run
mulitaminer evaluate --list-metrics` shows availability truthfully.
**State:** DONE (3 CLI tests; 110 total). scipy/rapidfuzz had landed in E3;
this phase added the `eval` group (bert-score). `--list-metrics` lives on
the evaluate command (target optional). Pre-existing ruff E402 in
exporters/__init__.py noted, untouched (not this diff).

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
**State:** DONE (111 tests). Live results:
- OpenVAS JuiceShop: 34/34 matched, recall/precision 1.000; text means
  0.94–1.00, references set_f1 0.917 — consistent with the v1-harness
  numbers in core plan Phase 9. Loader change forced by this run: results
  are read as raw dicts, NOT re-validated (an older run carries
  protocol='cpe-t' from before the Phase-10 type guard; the evaluator must
  score what the run wrote, and out-of-schema values cost score instead of
  crashing).
- Tenable JuiceShop: 75/76 matched (recall 0.987, precision 0.962),
  instances 0.764 against the *_instances_generated GT. Two fixes came out
  of diagnosis: (1) the scanner's severity_map (INFO->LOG) is now applied
  to both sides before align/score — severity went 0.560 -> 0.973 (the
  remainder is real extraction divergence); ScannerProfile exposes
  severity_map. (2) the MD report notes fields the baseline never fills
  (plugin_details etc.), where scores only measure presence agreement.
- GT-convention question RESOLVED (user choice: deterministic re-annotation,
  like instances): `archive/annotate_cvss_refs.py` regenerates the `cvss`
  and `references` columns from the PDF (Risk/Reference Information line
  grammar) into the `*_instances_generated.xlsx` copies; the evaluator now
  merges all three re-annotated columns (instances, cvss, references) from
  that file, with provenance in the report. Conventions anchored to the
  prompt's own contract: cvss verbatim lines, references ONE PER ELEMENT
  (comma-joined label lines exploded; label not duplicated when the value
  carries it). Results: cvss 0.413→0.981 (JuiceShop) / 0.984 (bWAAP);
  references 0.445→0.663 / 0.808. The references residual is a REAL
  extraction-quality signal — the LLM keeps multi-value lines whole about a
  third of the time, violating the prompt's "one per element"; a prompt
  tightening + rerun is the candidate fix (future work, costs a paid run).
  The old hand-annotated cvss cells were also malformed in places
  ('CVSCVSS2#...', 'None, None, 3.1, ...') — regeneration replaced them.
- PENDING USER DECISION: the *_instances_generated.xlsx files and the
  archive/ annotators are gitignored (annotate_instances precedent). If
  they are now official GT, committing both would make evaluation
  reproducible from a clean clone (paper methods).

Full 5-baseline sweep (2026-07-21, latest run per PDF; primary metric per
field, means over matched pairs):

| | OV JuiceShop | OV bBWA | OV artifactory | TN JuiceShop | TN bWAAP |
| --- | --- | --- | --- | --- | --- |
| coverage (recall/prec) | 1.000/1.000 | 1.000/0.983 | 0.983/1.000 | 0.987/0.962 | 1.000/0.970 |
| description (tokF1) | 0.966 | 0.975 | 0.822 | 0.926 | 0.905 |
| solution (tokF1) | 0.940 | 0.921 | 0.806 | 0.774 | 0.953 |
| references (setF1) | 0.917 | **0.304** | 0.825 | 0.663 | 0.808 |
| cvss | 0.971 | 1.000 | 0.912 | 0.981 | 0.984 |
| severity (exact) | 1.000 | 1.000 | 0.965 | 0.973 | 1.000 |
| instances (struct) | — | — | — | 0.764 | 0.767 |

references diagnosis (cross-scanner, consistent): BOTH prompts demand "one
reference per element", and the extraction violates it — OpenVAS keeps raw
'CVE: X, Y' comma-joins, label-only 'Other:' empties and 'URL:' prefixes
(bBWA is reference-heavy in that idiom, hence 0.304); Tenable keeps whole
multi-value label lines ~1/3 of the time. The GT conventions are now
anchored and clean on both scanners — the low references scores are real
extractor deviations. Candidate next step: tighten both prompts on the
references contract (split joins, drop empty labels) and validate with one
paid rerun per scanner.

PROMPT-FIX VALIDATION (2026-07-21, commit 137a99a, reruns evaluated with
measured means — the "before" numbers are inclusive means, slightly
inflated by vacuous pairs, so text-field deltas are not apples-to-apples):

| | before | after (measured) |
| --- | --- | --- |
| OV bBWA references set_f1 | 0.304 | **0.879** (set_f1_ids 0.943) |
| TN JuiceShop references set_f1 | 0.663 | **0.999** (set_f1_ids 0.997) |
| TN JuiceShop cvss set_f1 | 0.981 | **1.000** |
| TN JuiceShop instances | 0.764 | **0.898** |
| TN JuiceShop coverage | 75/76, 3 spurious | **76/76, 0 missed, 0 spurious** |
| TN JuiceShop raw/final | 139/78, 23 warn | **149/76 (=GT), 13 warn** |

The one-reference-per-element clause + exercised few-shot examples fixed
the violation on both scanners. Bonus: the TN rerun also confirms the
Phase 11 envelope/junk fixes — 10 more raw blocks recovered and the final
count landed exactly on ground truth. bBWA text fields read slightly lower
after only because the after-numbers exclude vacuous pairs; run-to-run LLM
variance is within noise (raw counts identical, 0 warnings both).

NLI smoke (2026-07-21, eval group installed, DeBERTa-v3-base-mnli-fever-anli):
negation flip "auth required" vs "NO auth required" scores 0.000
(contradiction, exactly the failure mode the metric was added for);
identical text 0.999; legitimate paraphrase 0.999 (no false alarm).
bertscore available. NLI runtime note: ~seconds/pair on CPU — opt-in via
--metrics nli, excluded from 'all' by design.
