# Usage

## Commands

| Command | What it does |
| --- | --- |
| `mulitaminer extract REPORT.pdf -s SCANNER -m MODEL` | Full extraction into a new run directory |
| `mulitaminer segment REPORT.pdf -s SCANNER` | Segmentation only, offline and free |
| `mulitaminer export RUN_DIR -e FORMAT` | Generate exports from an existing run, no LLM calls |
| `mulitaminer sync-feeds` | Download the KEV and EPSS feeds for prioritization |
| `mulitaminer prioritize RUN_DIR` | Rank a run into a remediation queue (offline) |
| `mulitaminer models` | List model profiles and their env vars |
| `mulitaminer scanners` | List available scanners |
| `mulitaminer formats` | List export formats and what consumes each |

Run any command with `--help` for all flags.

## extract

```bash
uv run mulitaminer extract report.pdf --scanner openvas --model deepseek
```

| Flag | Effect |
| --- | --- |
| `-s, --scanner` | Scanner profile (`mulitaminer scanners`) |
| `-m, --model` | Model profile (`mulitaminer models`), default `deepseek` |
| `--model-name` | Provider model id override, for `ollama`/`lmstudio` |
| `-e, --export` | Extra output format, repeatable (`mulitaminer formats`) |
| `--xlsx` / `--csv` | Shorthands for `-e xlsx` / `-e csv` |
| `--pdf-backend` | `pypdfium2` (default) or `pdfplumber` |
| `--output-dir` | Run artifacts root, default `outputs/runs/` |
| `--debug` | Also dump layout, blocks and raw LLM traffic |

## Run artifacts

Each run creates `outputs/runs/<timestamp>_<input>_<model>/`:

| File | Content |
| --- | --- |
| `results.json` | Extracted records (primary artifact) |
| `run.json` | Config snapshot, tokens, cost, duration, warnings, merge log |
| `results.raw.json` | Pre-consolidation records, only when merges happened |
| `results.<format>.*` | One file per `--export` |
| `layout.txt`, `blocks.txt`, `llm_traffic.jsonl`, `debug.log` | Only with `--debug` |

## Examples

```bash
# Local model via Ollama, no API key
uv run mulitaminer extract report.pdf -s tenable -m ollama --model-name qwen3

# Multiple exports at extraction time
uv run mulitaminer extract report.pdf -s openvas -m deepseek -e sarif -e generic

# Add exports to a finished run later
uv run mulitaminer export outputs/runs/20260721T033139Z_report_deepseek -e csaf
```
