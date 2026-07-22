# Evaluation

How `evaluate` and `experiment` score an extraction against a baseline, what the
numbers mean, and what the HTML report shows.

## What gets produced

- `evaluate` writes `evaluation.json` (machine) and `evaluation.md` (human) into
  the run directory.
- `experiment` evaluates every run the same way and builds a self-contained
  `report.html` over the whole tree.

## Coverage

The baseline XLSX is the gold standard, one row per finding. Coverage aligns the
extracted records to those rows and reports:

| Field | Meaning |
| --- | --- |
| `matched` | extracted records paired to a baseline row |
| `recall` | matched / baseline_count (how much of the baseline was recovered) |
| `precision` | matched / extraction_count (how much of the extraction is in the baseline) |
| `false_negatives` | baseline rows with no extracted match |
| `false_positives` | extracted records with no baseline match |

Coverage measures **alignment fidelity**, not invention. Extraction is
block-anchored (one record per finding block, count fixed before any LLM call),
so the model cannot invent a vulnerability from nothing. A false positive is
therefore almost always a record whose identity did not line up with its baseline
twin, not a hallucination.

## Alignment

Each (extraction, baseline) pair is scored by a composite key and a fuzzy name
match, then the globally optimal 1-to-1 assignment is solved (Hungarian,
`scipy.linear_sum_assignment`) and cut at a threshold (0.70).

- Composite key = normalized name plus scanner-specific parts (OpenVAS:
  port+protocol; Tenable: severity+plugin).
- Matching keys score the key match; conflicting keys penalize the name score,
  so two findings on different ports do not accidentally pair.
- A pair below 0.70 is dropped: its extraction side becomes a false positive and
  its baseline side a false negative.

## False positives, classified

Every false positive carries a `category` (`false_positive_kinds` totals them,
`false_positive_detail` lists each with its closest baseline row):

- **invention**: no baseline row is its counterpart. This is relative to the
  baseline, not a claim it was fabricated. With block-anchoring these are usually
  a real report finding the baseline lacks, or the same finding with a diverged
  name; a high `best_similarity` points to the latter.
- **duplicate**: the same finding (identical composite key) was extracted more
  than once while the baseline has it once.

`best_baseline`/`best_similarity` give the closest baseline row for context, so a
name-diverged false positive (high similarity) is easy to tell from a genuinely
unrelated one (low similarity). Confirmed baseline gaps are tracked in
[BASELINE_NOTES.md](BASELINE_NOTES.md).

A false negative is the mirror image: a baseline finding the extraction did not
recover (or recovered under a name too different to align).

## Per-field metrics

Only matched pairs are scored per field. Each field's metric is derived from the
record schema:

- **structural** (always on): `exact` for numeric/categorical fields, `set_f1`
  for reference lists (`set_f1_ids` normalizes id prefixes first).
- **text** (select with `--metrics`, list with `--list-metrics`): `token_f1`,
  `rouge_l`, and the heavy optional `bertscore` and `nli` (a contradiction check
  that flags an extraction stating the opposite of the baseline). The last two
  need `uv sync --group eval`.

The HTML report lists whichever of these a run actually scored, so `bertscore`
and `nli` appear once you evaluate with them.

Empty-vs-empty scores a vacuous 1.0 (flagged so reports can count it apart);
present-vs-absent scores 0.0.

## The HTML report (experiment)

`report.html` is self-contained (inline SVG, no network). It shows:

- model ranking by mean recall (fixed 0-1 scale) with run-to-run spread,
- per-field measured means across models,
- score distribution per report,
- false negatives vs false positives per model (mean/run),
- cost and latency per model, and a cost-vs-recall Pareto view.
