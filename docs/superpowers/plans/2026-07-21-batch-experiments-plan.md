# MulitaMiner2 — Batch Extraction, Experiment Harness & HTML Report Plan

**Status:** planned (user-requested 2026-07-21); serves the TCC 2 timeline
(sample expansion, metric expansion, model comparison).
**Status tracking:** update the checkbox and the *State* line of each phase as
work progresses, so any future session can resume from the exact point.

Conventions as in the core plan (English everywhere; one commit per phase;
a phase is done only when its Verify passes).

---

## Phase B0 — Directory extraction

`mulitaminer extract <path>` accepts a **directory**: every `*.pdf` inside is
extracted, each into its own normal run dir.

- **Scanner auto-detection, fail-safe by construction:** for each PDF,
  extract text and count each scanner profile's `marker_pattern` matches
  (the same deterministic regexes that drive segmentation — no LLM, no
  heuristics). A scanner claims the file only when it has matches **and
  every other scanner has zero**. Ambiguous (>1 with matches) or unmatched
  (0 everywhere) files are **skipped with a warning** — never extracted on
  a guess. `--scanner` remains as an override that forces one profile for
  the whole directory.
  - Safety note (user concern, addressed): even a hypothetical wrong pick
    cannot produce garbage output — the wrong profile segments 0 blocks,
    which means 0 LLM calls and 0 records, not wrong JSON.
- Per-file INFO log line: `<file> -> <scanner> (<n> markers)` or the skip
  reason. End-of-batch summary: extracted / skipped counts and total cost.
- A failed file (FatalLLMError aside) must not abort the batch — log, count
  as failed, continue. FatalLLMError (bad key/quota) aborts: every next
  file would fail identically.

**Verify:** `pytest` — detection unit tests (OpenVAS-only text, Tenable-only
text, ambiguous synthetic text -> skip, no-match text -> skip, --scanner
override wins); CLI test on a tmp dir with fixture PDFs mixed with a junk
PDF. Manual: `extract resources/openvas/` runs all three without flags.
**State:** TODO.

## Phase B1 — Experiment harness

`mulitaminer experiment <dir> --models deepseek,claude-haiku --runs 5`
(plus `--scanner` override, `--output-dir`, repeatable `--metrics` passed
through to evaluation).

- **Layout** (v1-compatible purpose, per-scanner separation):
  `output_experiments/<scanner>/<model>/run_<n>/<report_stem>/`
  containing the standard run artifacts (`results.json`, `run.json`) plus
  `evaluation.json`/`evaluation.md` when a baseline XLSX sits next to the
  source PDF (auto-evaluation after each run; skipped with a note when no
  baseline exists).
- **Experiment manifest:** `output_experiments/experiment.json` — config
  (reports, models, runs, metrics), start/end timestamps, per-run status,
  totals (cost, tokens, failures). This is the input the HTML report reads.
- **Parallelism by capacity bucket (decision, 2026-07-21):** runs are
  grouped by the model's `api_key_env ?? base_url` — the credential/server
  that actually enforces rate limits. Buckets run in parallel (threads;
  the pipeline is I/O-bound), runs within a bucket run sequentially.
  Rationale: "per provider" is an approximation of this — two models
  sharing OPENAI_API_KEY must serialize (shared rate limit), two DeepSeek
  keys could parallelize, and local servers serialize per `base_url`
  (Ollama processes one request at a time). The bucket key is derived
  entirely from the model config — no hardcoded provider list.
- **Checkpointing (v1 parity, user requirement):** the run dir IS the
  checkpoint — a run with complete `results.json` + `run.json` is skipped
  on re-invocation, so an interrupted experiment resumes exactly where it
  stopped (`mulitaminer experiment` with the same args). The manifest is
  updated incrementally after every finished run (not only at the end), so
  a hard kill loses at most the in-flight run. Skipped-as-cached runs are
  recorded as such.
- **Per-run duration accounting (user requirement):** every run's own
  `duration_s` (already measured by the pipeline, active time only) is
  copied into the manifest, and the experiment total is the **sum of run
  durations** — never `end_timestamp - start_timestamp`, which would count
  idle hours when someone stops and resumes from checkpoint later. The
  manifest keeps both numbers explicitly labeled: `active_seconds` (sum)
  and `wall_clock_seconds` (informational, per session segment).
- Determinism note: temperature is 0 but sampling is not bitwise-stable —
  X runs exist precisely to measure run-to-run variance.

**Verify:** `pytest` with the fake client — layout produced exactly as
specced; bucket grouping unit-tested (shared key -> same bucket, local ->
base_url bucket); resume skips completed runs; manifest totals correct.
Manual: a 2-model x 2-run experiment on one small baseline PDF (deepseek +
a second profile) completes and evaluates.
**State:** TODO.

## Phase B2 — HTML experiment report

`mulitaminer report <experiments_dir>` (also produced automatically at the
end of `experiment`): a **single self-contained HTML file**
(`output_experiments/report.html`) with inline-SVG charts — no JavaScript
dependencies, opens offline in any browser (charts are drawn by our own
Python SVG rendering, same approach as the README pipeline diagrams).
Decision: start with pure SVG; upgrade to an interactive library only if
the result underwhelms (user call, 2026-07-21).

- **Design: based on the TCC defense deck** (`MulitaMiner.pdf` layout):
  warm cream background, near-black ink, orange accent for highlights,
  monospace for data/labels, card-based sections with the deck's soft
  panels, section kickers in small-caps orange. Load the `dataviz` skill
  before writing any chart code.
- **Content (minimum):**
  - Header: experiment config summary (reports, models, runs, date, total
    cost/tokens/time).
  - Coverage per scanner x model: recall/precision (matched/missed/
    spurious) with run-to-run min-max whiskers.
  - Field quality: measured means (vacuous-excluded) per field x model,
    one panel per scanner; strict vs canonical references shown side by
    side when present.
  - Run-to-run variance: per model, the spread of key metrics across the
    X runs (the reason multiple runs exist).
  - Cost/latency: cost per report and duration per model.
  - Footnotes: vacuous counts, unavailable metrics, skipped files,
    baseline provenance (re-annotated columns) — honesty notes mirroring
    evaluation.md.
- Charts follow the audit's guidance: dot/bar comparisons on a common
  axis, no means without their spread when multiple runs exist.

**Verify:** `pytest` — report builds from a fabricated manifest + fake
evaluation.json set; HTML contains the expected sections/SVGs; no external
resource references (offline check). Manual: open the real experiment's
report.html in a browser and eyeball against the deck's look.
**State:** TODO.

---

Sequencing note: this plan is independent of Phase 15 (new scanner +
extra_fields) and Phase 17 (embedded model); the user picks execution
order. B0 -> B1 -> B2 is internally ordered (each consumes the previous).

## Phase B3 — Multi-run statistical aggregation (approved 2026-07-21)

Consumes the B1 experiment tree. Purpose: turn "model A looks better than
model B" into a defensible claim for TCC 2.

- Per metric x field x model: mean, std, and **bootstrap confidence
  intervals** across the X runs; paired significance test between models
  on the same reports (paired bootstrap or Wilcoxon — decide at design
  time with the metrics-auditor lens: n is small, normality not assumed).
- Feeds B2: the HTML report shows CI whiskers instead of bare means, and
  marks model-vs-model deltas whose CI excludes zero.
- Scope guard: no inter-rater kappa (user deferred), no charts beyond what
  B2 already renders.

**Verify:** unit tests with synthetic run sets (known spread -> known CI;
identical runs -> zero-width CI); aggregation output embedded in the
manifest/report.
**State:** TODO (planned; implement after B1).
