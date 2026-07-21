# Prioritization

Ranks a run's findings into a remediation queue using three public signals.
Deterministic and auditable: no LLM in the ranking, and every signal behind a
decision is a column in the output.

| Signal | Source | Meaning |
| --- | --- | --- |
| KEV | CISA Known Exploited Vulnerabilities | The CVE is exploited in the wild |
| EPSS | FIRST.org | Probability of exploitation in the next 30 days |
| SSVC | CISA decision methodology | Act / Attend / Track category per finding |

CVE ids come from each record's `references` (and Tenable `plugin_details`),
so any run with CVEs can be prioritized. Findings without a CVE are handled
explicitly (see below), not silently assumed safe.

## Usage

```bash
# 1. Sync the feeds once (~5 MB, needs internet; cached afterwards)
uv run mulitaminer sync-feeds

# 2. Rank a run (offline; reads the local snapshot)
uv run mulitaminer prioritize outputs/runs/<run_dir>
```

Output next to the run's `results.json`:
`results.prioritization.csv` and `.xlsx`, one row per finding, most urgent
first.

## Columns

| Column | Meaning |
| --- | --- |
| `rank` | Position in the queue |
| `category` | SSVC decision: Act > Attend > Track* > Track |
| `exposure` | `exposed` (default) or `internal` (private IP or internal-looking host) |
| `exploitation` | `active` (KEV), `likely` (EPSS over threshold), `none`, or `unknown` (no CVE) |
| `severity` | high/medium/low from CVSS, falling back to the label |
| `kev`, `epss`, `cvss`, `cves` | The raw signals, so the category is re-derivable by hand |
| `justification` | One-line reason for the category |
| `snapshot_date` | EPSS score date of the feed snapshot used |

## Decision tree

`(exploitation, exposure, severity)` maps to a category. `unknown` (no CVE,
common for Tenable WAS findings like XSS/SQLi) sits one notch above `none`:
the absence of a CVE is absence of evidence, not evidence of safety, so it is
never discounted as safe.

## Ordering

Within a category, rows are ordered by EPSS descending, then CVSS descending.
Two findings in the same category are equally urgent by SSVC; the tiebreak
just surfaces the more probable one first.
