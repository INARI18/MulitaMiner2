# Metrics audit — MulitaMiner2 evaluation subsystem

**Date:** 2026-07-24
**Subject:** Are the evaluation metrics good for judging the extraction tool? Are the
numbers trustworthy, and are they the right numbers?
**Scope:** the deepseek sweep (`output_experiments/deepseek/`, 5 of 8 reports
complete at audit time), the baselines under `resources/`, and the evaluation code
in `src/mulitaminer/evaluation/`.

## Verification performed

- **Read the computation code** (`scorers.py`, `runner.py`, `report.py`,
  `fields.py`). token_f1, rouge_l, set_f1, set_f1_ids and exact are **custom**
  implementations (no `rouge_score`/`nltk`/`sklearn` installed); bertscore is
  `bert_score` 0.3.12, nli is `transformers` 5.14.1.
- **Recomputed token_f1 independently** (from-scratch bag-of-words F1) on the
  worst-scoring OpenVAS Metasploitable2 pair: matches the stored values exactly on
  every field (name 1.0, description 0.75, insight 0.0, solution 0.6933,
  detection_result 0.0). No implementation bug.
- **Traced 3 records end-to-end** (worst + two median) on OpenVAS Metasploitable2,
  comparing extraction vs baseline field content.
- **Scanned all 8 baselines** for ligature corruption.

## Findings (ranked)

### 1. The OpenVAS text scores understate the tool; the errors are baseline-side, not tool-side

Every traced sub-1.0 pair was a **baseline** problem, not an extraction error:

- **Worst pair** (`SSL/TLS: Diffie-Hellman ... insufficient DH strength`, mean 0.618):
  - `insight` 0.0 and `detection_result` 0.0 because the **baseline is empty** while
    the extraction has real content (`Server Temporary Key Size: 1024 bits`, the DH
    explanation). Present-vs-absent scores 0.0 — the extraction is *more complete*.
  - `description` 0.75 because the baseline reads `Di_x001E_e-Hellman` /
    `insu_x001E_cient` (control char 0x1E = the "ff"/"ffi" ligature). The extraction
    has the correct `Diffie` / `insufficient` and is **penalized for being right**.
- **Median pair** (`SSL/TLS: Certificate Expired`, solution 0.76): baseline reads
  `certicate` (the "fi" ligature silently dropped) and lacks `Solution type:
  Mitigation`. Extraction correct and more complete.
- **Median pair** (`TWiki CSRF`, solution 0.71): extraction adds a real
  `Affected Software/OS` section the baseline omits — a granularity difference.

Direction analysis over all OpenVAS Metasploitable2 pairs (non-vacuous, <1.0):

| field | ext-filled / base-empty | ext-empty / base-filled (real omission) | both filled, differ |
| --- | --- | --- | --- |
| insight | 3 | 0 | 16 |
| solution | 1 | 0 | 29 |
| detection_result | 1 | 0 | 12 |
| detection_method | 0 | 0 | 17 |
| description | 0 | 0 | 16 |
| references | 0 | 1 | 8 |

**Real omissions are ~0.** Errors are "both differ", and the three traced cases show
"differ" is driven by baseline incompleteness, ligature corruption, and granularity —
not extraction mistakes. Fill rates are near-identical (ext ≈ base), so the tool is
not systematically over- or under-extracting.

**Ligature corruption is OpenVAS-specific** (two forms: `_x001E_` control char, and
silently dropped ff/fi/fl): OpenVAS_Metasploitable2 6 rows, OpenVAS_JuiceShop 3,
artifactory 1; Nessus/Qualys/Tenable 0. It is the same corruption `pdf_reader`
restores for the extraction, so the extraction is correct and the baseline is not.

**Consequence:** the OpenVAS free-text means (0.88–0.94) are a floor, not the true
fidelity. The tool is doing better than the numbers say on OpenVAS.

### 2. The metric computation is faithful; aggregation is honest

- token_f1 reproduced exactly by independent reimplementation.
- The mean handling is correct and already audited once (code comment
  "audit finding, 2026-07-21"): `measured_mean` **excludes** vacuous empty×empty
  pairs (which score a free 1.0), and it is the reported headline. Present-vs-absent
  scores 0.0 non-vacuous (`pair_score`, `_structural_score`). exact is numeric-aware
  (`8019.0 == 8019`) and case-folded; rouge_l is standard LCS-F1; set_f1_ids
  canonicalizes CVE/CWE/BID/OWASP/URL ids. All correct.
- The summary also computes `std`, `min`, `vacuous_n`, and `fill_rate_*` per field —
  richer than the report surfaces (see finding 4).

### 3. Metric appropriateness: right family, one structural gap

- **n-gram overlap (token_f1, rouge_l) is appropriate here.** The usual ROUGE pitfall
  ("punishes legitimate paraphrase") is *inverted* for extraction: the tool is
  supposed to copy, so lexical overlap is the right axis. Good fit.
- **No metric can separate "extraction more complete/correct than the baseline" from
  "extraction wrong"** — both land under 1.0. Finding 1 shows this conflation is
  actively misleading when the baseline is imperfect. The fix is a **source-grounding
  / faithfulness metric** (does the extracted span appear in the *report*, not the
  baseline?). It is the one dimension nothing currently measures, and it would be
  *more* reliable than baseline comparison for the degraded-baseline fields. Caveat:
  grounding must tolerate the same text transforms the extractor applies (ligatures,
  line-wrap hyphens, the U+FFFE fix) or it will false-negative.
- **Coverage is near-ceiling.** Recall is ~1.0 by construction (block-anchored +
  baseline from the same report). Precision caught one real miss (Metasploitable2
  0.983 — a known baseline gap, the 25/tcp SSL instance). So coverage is a useful
  sanity check and config-bug catcher (it exposed the qualys key collapse) but a weak
  model-quality discriminator.

### 4. Means hide the distribution in the human report

`summary_table` prints **only** `measured_mean` (3 decimals). `std`, `min` and
`fill_rate` are computed and stored in `evaluation.json` but never surfaced in
`evaluation.md`. The "Worst pairs per field" section partially compensates. Two
aggregation pitfalls remain open:

- **No stratification.** The mean pools 83%-informational findings and the easy
  structural fields (severity/port/protocol/plugin/cvss are 100% everywhere). A weak
  model could score well on the structural majority and hide a collapse on free text.
  Report structural vs free-text separately, and stratify by severity.
- **Small n on the tail that matters.** Nessus scan-b has 4 Critical/High pairs;
  Critical/High mean (0.9948) vs rest (0.9947) is indistinguishable but the n is too
  small to conclude. Any per-severity claim needs more high-severity data.

### 5. BERTScore saturation (minor)

bertscore runs on whole-field concatenated text (list joined by newline), default
model, no baseline-rescaling — so it saturates in the 0.85–0.95 band (e.g.
detection_result 0.949). Report **deltas**, not absolutes, when comparing models.
Mitigated by having token_f1/rouge_l alongside for triangulation.

## Appropriateness verdicts

| Metric | Verdict |
| --- | --- |
| exact (severity/port/protocol/plugin) | Correct and appropriate; but at ceiling (100%), so it does not discriminate models. |
| token_f1, rouge_l | Correct; appropriate for a copy task. Cannot tell "fuller than baseline" from "wrong". |
| set_f1 / set_f1_ids | Correct; the id-canonicalized variant is the right primary for references. |
| bertscore | Correct call; saturates — report deltas. |
| nli | Appropriate as a negation safety net; opts out of `--all` for speed (fine). |
| coverage (recall/precision) | Necessary sanity check + config-bug catcher; near-ceiling, weak as a quality signal. |
| **(missing) source grounding** | The gap. Nothing measures whether extracted text is faithful to the report. Highest-value addition. |

## Visualization suggestions

- Per-field **score distribution** (box or strip plot), not just the mean table —
  directly addresses finding 4. The `std`/`min` needed are already in the json.
- **Structural vs free-text** split as two grouped bars per model — makes the
  ceiling effect and the real discriminating signal visible at a glance.
- For model comparison later: **delta bars vs the DeepSeek ceiling**, since bertscore
  saturates and absolutes mislead (finding 5).

## Limitations (not verified)

- bertscore and nli were **not** independently recomputed (model calls); only
  token_f1/rouge_l logic was reproduced.
- Only OpenVAS Metasploitable2 was traced pair-by-pair (3 records). Nessus, Tenable
  and Qualys were checked only in aggregate; their sub-1.0 pairs were not traced, so
  finding 1 is established for OpenVAS and *plausible but unverified* elsewhere.
- "Extraction is more correct than the baseline" is inferred from content
  plausibility (real report sections, correct spelling), **not** confirmed against the
  source PDF — which is exactly the missing grounding check.
- The sweep was partial (5/8 reports) at audit time.
