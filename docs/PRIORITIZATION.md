# Prioritization

Ranks extracted findings into a remediation queue using three public signals:

| Signal | Source | Meaning |
| --- | --- | --- |
| KEV | CISA Known Exploited Vulnerabilities | The CVE is being exploited in the wild |
| EPSS | FIRST.org | Probability of exploitation in the next 30 days |
| SSVC | CISA decision methodology | Act / Attend / Track decision per finding |

CVE ids are taken from each record's `references`, so any run with CVEs can
be prioritized.

## Status

Not yet native to this package. The prioritization module of the previous
MulitaMiner version consumes this tool's `results.json` unchanged (verified),
so the workflow below works today. Porting it into this package is planned.

## Prioritizing a run today

From the previous version's repository (`../MulitaMiner`):

```bash
# 1. Sync the KEV and EPSS feeds (needs internet, cached afterwards)
python tools/sync_feeds.py

# 2. Point the prioritizer at a run of this tool
python -c "from mulitaminer.prioritization.apply import prioritize_extraction; \
prioritize_extraction(r'..\\MulitaMiner2\\outputs\\runs\\<run_dir>\\results.json')"
```

Output: `results_prioritization.csv` and `.xlsx` written next to the
`results.json`, one row per finding ranked by the SSVC decision, KEV presence
and EPSS score.

## Interpreting the queue

Fix in order: SSVC `Act` first (exploited or high stakes), then `Attend`,
then `Track`. Within a tier, higher EPSS first. Findings without a CVE fall
back to CVSS/severity ordering.
