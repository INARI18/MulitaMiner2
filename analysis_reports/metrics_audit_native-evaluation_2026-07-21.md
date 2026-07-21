# Metrics audit — MulitaMiner2 native evaluation subsystem

**Date:** 2026-07-21
**Audited:** `src/mulitaminer/evaluation/` (scorers, fields, align, runner,
report) and the 5-baseline sweep recorded in
`docs/superpowers/plans/2026-07-21-native-evaluation-plan.md`.
**Artifacts examined:** input data (`results.json` per run, baseline XLSX +
`*_instances_generated.xlsx`), metric outputs (`evaluation.json`/`.md` in the
five run dirs), computation code (all five evaluation modules, plus the
prompts that define the extraction contract).

## Verification performed

- **Independent recomputation** (scratch script, no imports from
  `mulitaminer.evaluation`): token F1, ROUGE-L (own LCS) and set F1
  re-derived from raw `results.json` + XLSX over **all 75 matched pairs** of
  the Tenable JuiceShop run.
- **Denominator check:** coverage counts cross-checked against the run's own
  `mapping_debug` table and the raw row counts.
- **End-to-end traces:** worst `solution` pair (TN JuiceShop), worst
  `description` pair (artifactory), a median `instances` pair, the worst
  `references` pairs (bBWA, traced earlier this session).
- **Distribution check:** per-pair `description` scores on artifactory
  (n=114) vs the reported mean.

## Findings (ranked)

### 1. Vacuous matches inflate headline means — the weak fields are weaker than the table says

`pair_score` counts empty×empty as 1.0 (vacuous) and the per-field mean
includes those pairs. The summary exposes `vacuous_n`, but the headline
table reports the inclusive mean. Recomputed measured-only means
(excluding vacuous):

| field | reported mean | vacuous/n | mean on measured pairs |
| --- | --- | --- | --- |
| TN JuiceShop `references` | 0.663 | 31/75 | **0.426** |
| OV bBWA `references` | 0.304 | 12/58 | **0.122** |
| TN JuiceShop `impact`/`insight`/`log_method`/`detection_result` | 1.000 | 75/75 | — (nothing measured) |

The Tenable 1.000 rows are contract-correct (the prompt mandates `[]` for
those fields and the GT agrees — the score confirms schema compliance, not
text quality), but a reader of the table cannot tell 1.000-measured from
1.000-vacuous, and 0.663 substantially understates the references problem.
**Recommendation:** report the measured-only mean alongside (or instead),
with `n_measured`; render all-vacuous cells as e.g. `1.000*` or `n/a`.

### 2. Computation fidelity: verified, no discrepancy

Independent recomputation over all 75 TN JuiceShop pairs matches the
reported values to 4 decimals: description token F1 0.9257 = 0.9257,
description ROUGE-L 0.9249 = 0.9249, references set F1 0.6632 = 0.6632.
Coverage denominators consistent: 76 baseline rows / 78 extracted records /
75 MATCHED + 3 UNMATCHED in `mapping_debug` → recall 75/76, precision
75/78 as reported.

### 3. Lexical metrics are the *right* primary tool for this task (with the usual caveat inverted)

The standard pitfall — n-gram metrics punish paraphrase — does not apply:
both prompts demand **verbatim** extraction ("Extract content verbatim and
complete"), so lexical divergence is exactly what should cost score.
Corollary: BERTScore should remain the *secondary* metric here — it
saturates (0.85–0.95 band) and would mask truncations that token F1
surfaces. The v1-harness BERTScore comparisons stay useful for
cross-checking, not as headline.

### 4. Traced outliers are real extraction defects, not metric artifacts

- Worst `solution` (TN JuiceShop, Apache 2.4.58): extraction returned `[]`
  where GT has `['Upgrade to Apache version 2.4.58 or later.']` → 0.0 is
  correct.
- Worst `description` (artifactory, Tomcat Rewrite Bypass): extraction
  truncated (101 chars incl. a stray "Quality of Detection (QoD): 30%"
  line vs 296-char GT) → 0.373 is correct.
- artifactory `description` distribution is unimodal (n=114, mean 0.822,
  median 0.800, q1 0.783, min 0.373, no zeros) — the mean is a fair
  summary there; no hidden bimodality.

### 5. `references` set F1 measures prompt adherence, not content fidelity

After token normalization, `'CVE CVE-2022-22719'` ≠ `'CVE-2022-22719'` and
`'CVE: X, Y'` (one item) ≠ two atomic items — content-identical outputs
score 0. This is appropriate for the **current** claim (does the extractor
follow the one-per-element contract? — the prompt-tightening experiment in
flight tests exactly this). If the paper later wants a *content* claim
("did we capture the right references?"), add a canonicalized variant:
regex-extract CVE/CWE/BID/OWASP/WASC identifiers from both sides and
compare those sets. Report both, labeled.

### 6. ROUGE-L duplicates token F1 on this task

Across the sweep the two differ only in the 3rd decimal (e.g. 0.9257 vs
0.9249) — verbatim extraction rarely reorders tokens. Keeping both is
cheap; for the paper, present one of them (plus BERTScore) and state the
near-identity once.

### 7. Structural `instances` scoring: plausible but least-verified

The 0.764/0.767 means come from greedy first-field (URL) fuzzy sub-align ≥
0.7 + leaf-mean recursion, normalized by max(item count). A median pair
traced clean (1×1 → 1.0), and missing items correctly cost score, but no
hand-verified instance-level ground truth exists to calibrate the
sub-alignment itself. Treat instance scores as comparative (run vs run),
not absolute, until spot-checked.

## Metric-appropriateness verdicts

| Metric | Verdict |
| --- | --- |
| exact (numeric/categorical) | Appropriate; numeric-aware normalization verified (8019.0≡8019) |
| token F1 / ROUGE-L (text) | Appropriate as primary for a verbatim contract; near-duplicates of each other |
| set F1 (references, Tenable cvss) | Appropriate for prompt-adherence claims; too strict for content claims — add canonicalized variant if needed |
| structural (instances, plugin_details) | Reasonable design; least-verified — calibrate before absolute claims |
| BERTScore (optional) | Keep secondary; saturation would hide truncation defects |
| coverage recall/precision | Sound; denominators verified. Note precision uses post-consolidation records |

## Visualization suggestions (not generated)

- Field × run comparison: grouped dot plot (fields on y, one dot per run),
  with vacuous-excluded means — makes the references outlier and the
  artifactory floor visible at a glance; the current markdown table hides
  ordering.
- `references` per-pair scores: strip/beeswarm per run — expected strongly
  bimodal (many 0s, many 1s); a mean alone is misleading precisely there.
- Before/after prompt-fix comparison (the experiment in flight): slope
  chart per field, old run → new run.

## Limitations

- BERTScore path not audited (not installed in this environment).
- Hungarian optimality not independently re-verified (scipy trusted); the
  KEY_CONFLICT_PENALTY=0.9 tiebreak was verified by unit test only.
- The regenerated GT (`annotate_cvss_refs.py`) was spot-verified against
  raw PDF text for a handful of blocks, not exhaustively; note the
  circularity: it encodes the same conventions the prompt demands, which is
  correct for adherence claims but means GT and contract cannot disagree.
- OpenVAS bBWA/artifactory `references` GT is still the original hand
  annotation (only Tenable was regenerated).
