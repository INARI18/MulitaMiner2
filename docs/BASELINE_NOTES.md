# Baseline notes

Known discrepancies between a scanner report and its hand-curated baseline XLSX,
surfaced by the extractor and verified against the report. The extractor is
block-anchored, so a record only exists when the report has a matching block;
these are cases where the report (and the extraction) carry an instance the
baseline does not.

To reproduce: run `evaluate` and read `coverage.false_positive_detail` in
`evaluation.json`; an `invention` entry with a high `best_similarity` is a
finding the report has but the baseline does not (often another port/instance of
a finding the baseline already lists once). Confirm each against the report by
segmenting it (`mulitaminer segment <report> -s <scanner>`).

## Open items

| Report | Finding | Discrepancy | Evidence |
| --- | --- | --- | --- |
| `resources/openvas/OpenVAS_bWAPP.xlsx` | SSL/TLS: Certificate Signed Using A Weak Signature Algorithm | Baseline has only the **5432/tcp** instance; the report also has a **25/tcp** instance (host 172.17.0.3) | Segmentation yields blocks 44 (port 25/tcp) and 51 (port 5432/tcp); the extractor finds both in all 3 deepseek runs. Suggested fix: add the port-25/tcp row to the baseline. |

No other baseline gaps were found across the five reports (openvas: bWAPP,
JuiceShop, artifactory; tenable: bWAPP, JuiceShop).
