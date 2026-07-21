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
| `sarif` | `results.sarif` | GitHub code scanning, DefectDojo, SonarQube, Azure DevOps |
| `generic` | `results.generic.json` | DefectDojo Generic Findings Import |
| `cais` | `results.cais.csv` + `.json` | CAIS institutional schema (dotted keys) |
| `csaf` | `results.csaf.json` | CSAF 2.0 security advisory (CISA/CSIRT ecosystem) |

Note on serialization: SARIF and CSAF are JSON by definition of their
standards; a CSV version of them would not be ingested by anything. The
tabular formats are `xlsx`, `csv` and `cais`.

## Field mapping highlights

- CVE and CWE ids are parsed from the record's `references`.
- CVSS v3 score/vector are parsed from the Tenable CVSS strings; SARIF/CSAF
  emit scores only when a vector exists.
- Severity maps per target: LOG becomes `Info` (DefectDojo), `note` (SARIF),
  `NONE` (CSAF baseSeverity).
- Hosts become SARIF logical locations (`host:port`) and the CSAF product
  tree.

## Adding a format

One module in `src/mulitaminer/exporters/` with a `to_<name>` function
decorated `@register("<name>", "description")`, imported in the package
`__init__`. It receives the validated records and the run directory.
