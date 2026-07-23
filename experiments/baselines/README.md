# baselines/

Provenance of the ground-truth baseline XLSX in `resources/<scanner>/`.

The tool *consumes* baselines (as evaluation ground truth); it does not build
them. Preparing the ground truth is a separate, one-off step, so it lives here
rather than in `src/mulitaminer/`. The goal is a defensible provenance for each
baseline: "derived from the scanner's own export / PDF by this script", not
hand curation.

The canonical baseline schema (column set + order) is derived from each
scanner's record model (`mulitaminer.models`) by `_baseline_schema.py`, so a
baseline always tracks the tool's record type.

## Scripts

| Script | What it does |
| --- | --- |
| `build_baseline_qualys.py` | Qualys CSV report export -> baseline XLSX. One row per vuln row; numeric severity `1..5` -> `INFO/LOW/MEDIUM/HIGH/CRITICAL`; `CVE ID` -> `references`. |
| `build_baseline_openvas.py` | OpenVAS/Greenbone CSV export -> baseline XLSX. One row per unique `(NVT, host, port, protocol)`; `CVEs`/`BIDs`/`CERTs`/`Other References` -> `references`. |
| `normalize_baselines.py` | Rewrites every baseline to the canonical schema (typing/format only, content preserved and re-checked): record-model column order, upper-case severity tiers, `references` as a repr'd list. Drops the vestigial always-empty `http_info`/`identification` columns. |
| `_baseline_schema.py` | Shared helpers: canonical column order from the record model, severity/reference normalization. |

## Usage

```bash
uv run python experiments/baselines/build_baseline_qualys.py  <report.csv> <out.xlsx>
uv run python experiments/baselines/build_baseline_openvas.py <report.csv> <out.xlsx>
uv run python experiments/baselines/normalize_baselines.py [resources]   # in place, guarded
```

`normalize_baselines.py` writes each file to a temp, re-reads it, and asserts
that the evaluator would see identical content per record field (references by
canonical id-set, severity case-insensitively, everything else by rendered
text) before replacing the original. A file that would change content is left
untouched and reported.

## Per-scanner provenance

| Scanner | Source | How the baseline is produced |
| --- | --- | --- |
| Qualys | CSV export (`resources/qualys/*.csv`) | `build_baseline_qualys.py`, then `normalize_baselines.py`. |
| OpenVAS | Greenbone CSV export | `build_baseline_openvas.py`, then `normalize_baselines.py`. Hand-curated baselines predate this script; rebuild from the CSV when available. |
| Tenable WAS | PDF report | No CSV export available. Deterministic per-field re-annotation from the PDF via `archive/annotate_*.py` (`cvss`+`references`, `instances`, `plugin_details`), then `normalize_baselines.py`. |

Tenable has no machine CSV export, so its list/detail columns are re-annotated
straight from the PDF (`archive/annotate_cvss_refs.py`,
`annotate_instances.py`, `annotate_plugin_details.py`) rather than parsed from
an export. Those annotators live in `archive/` (local-only).
