# Exports

Every export is a deterministic mapping from `results.json`; no LLM involved.
Generate them at extraction time (`--export`) or later from any finished run:

```bash
uv run mulitaminer export outputs/runs/<run_dir> -e sarif -e csaf
```

## Formats

| Name | File(s) | Consumed by |
| --- | --- | --- |
| `xlsx` | `results.xlsx` | Spreadsheets, manual review |
| `csv` | `results.csv` | Spreadsheets, scripts |
| `sarif` | `results.sarif` | GitHub code scanning, SonarQube, Azure DevOps |
| `generic` | `results.generic.json` | DefectDojo (Generic Findings Import) |
| `cais` | `results.cais.csv` + `.json` | CAIS institutional schema (dotted keys) |
| `csaf` | `results.csaf.json` | CSAF 2.0 security advisory (CISA/CSIRT ecosystem) |

Note on serialization: SARIF and CSAF are JSON by definition of their
standards; a CSV version of them would not be ingested by anything. The
tabular formats are `xlsx`, `csv` and `cais`.

## Mapping notes

- CVE/CWE ids come from `references`; severity labels are case-insensitive.
- Location is `host:port`, or the `instances` URLs when there is no host (ZAP).
- **SARIF**: hosts become a synthetic file location (host at line 1), which
  GitHub requires; each scanner gets its own category, so uploads don't
  overwrite each other. GitHub code scanning is free only on public repos.
  SonarQube imports it with severity reduced to three levels.
- **Generic**: use this one for DefectDojo; its SARIF parser drops the hosts.
- **CSAF**: one entry per CVE, hosts as products; `baseSeverity` comes from
  the CVSS score, the scanner's label goes in an `impact` threat.

Verified against GitHub, DefectDojo, SonarQube and the official SARIF/CSAF
validators. Remaining validator warnings (missing descriptions, TLP label,
CPE, remediations the extraction left empty) are expected.

## Adding a format

One module in `src/mulitaminer/exporters/` with a `to_<name>` function
decorated `@register("<name>", "description")`, imported in the package
`__init__`. It receives the validated records and the run directory.
