<div align="center">

  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="imgs/MulitaMiner_logo_light.png">
    <source media="(prefers-color-scheme: light)" srcset="imgs/MulitaMiner_logo_dark.png">
    <img src="imgs/MulitaMiner_logo_light.png" width="500" alt="MulitaMiner logo">
  </picture>

**Vulnerability Extraction from Security Reports using LLMs**

_Block-anchored · Multi-scanner · Multi-LLM_

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-brightgreen)

</div>

# MulitaMiner

MulitaMiner turns the PDF reports that security scanners produce — each in its
own layout and vocabulary — into a single, structured, analysis-ready
vulnerability schema. Its LLM pipeline is **block-anchored**: the report is
split deterministically into findings *before* any model call, so the model
fills the fields of each finding instead of "discovering" vulnerabilities, and
the output count always matches the report.

Beyond extraction it unifies heterogeneous scanners (OpenVAS/Greenbone,
Tenable WAS, or your own via a JSON config) under one record model, exports to
the formats real tools ingest (SARIF, CSAF, DefectDojo, CAIS, CSV, XLSX),
ranks findings into a KEV/EPSS/SSVC remediation queue, and ships a
schema-driven evaluation subsystem that scores extraction quality against
ground-truth baselines.

## Pipeline

![MulitaMiner pipeline](docs/imgs/pipeline.svg)

1. **PDF**: the scanner report goes in.
2. **Extract text**: pull clean text out of the PDF.
3. **Split blocks**: cut the text into one block per finding, deterministically, so the finding count is known before any LLM call.
4. **Pack chunks**: group whole blocks into token-budgeted chunks (blocks are never split).
5. **LLM extract**: each chunk is sent to the model with the scanner's prompt, which fills the fields of every block; block ids keep one record per finding. Blocks that fail loop back to step 4 in smaller chunks.
6. **Consolidate**: pair base and instances, normalize severity, merge identical records.
7. **results.json**: the structured records, the primary artifact.
8. **Exports**: optional SARIF, CSAF, DefectDojo Generic, CAIS, CSV, XLSX.

## Supported

| | |
| --- | --- |
| Scanners | OpenVAS/Greenbone, Tenable WAS (add your own with a JSON config) |
| Cloud models | DeepSeek, OpenAI (gpt-4o, gpt-4o-mini), Groq (Llama 3.3 70B), Claude (Haiku) |
| Local models | Ollama, LM Studio, any OpenAI-compatible server. No API key needed |
| Exports | XLSX, CSV, SARIF 2.1.0, DefectDojo Generic JSON, CAIS, CSAF 2.0 |
| Evaluation | Coverage + per-field metrics (exact, set F1, token F1, ROUGE-L, optional BERTScore/NLI) |

## Requirements

| Component | Requirement |
| --- | --- |
| Python | 3.11+ |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| RAM | 4 GB+ (8 GB for large reports) |
| Network | Only for cloud LLM calls; local models work fully offline |

## Installation

**1. Install uv** (once, if you don't have it):

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Clone and sync:**

```bash
git clone https://github.com/INARI18/MulitaMiner2.git
cd MulitaMiner2
uv sync
```

**3. Configure API keys** (skip if you only use local models):

```bash
# Linux / macOS
cp .env.example .env
```

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

Then fill in the keys for the providers you use (`.env` is gitignored — never
commit it):

```env
DEEPSEEK_API_KEY="..."
OPENAI_API_KEY="..."
GROQ_API_KEY="..."
CLAUDE_API_KEY="..."
```

Optional heavy metrics (BERTScore/NLI, pulls torch): `uv sync --group eval`.

## Quickstart

Verify the install with a free, offline command (no API key needed):

```bash
uv run mulitaminer segment resources/openvas/OpenVAS_JuiceShop.pdf --scanner openvas
```

Expected: `34 blocks found`. Then a real extraction (uses your key):

```bash
# Extract and also write a spreadsheet
uv run mulitaminer extract resources/openvas/OpenVAS_JuiceShop.pdf --scanner openvas --model deepseek --export xlsx

# Generate more exports later from the same run, no LLM calls
uv run mulitaminer export outputs/runs/<run_dir> -e sarif -e csaf

# Rank findings into a remediation queue (KEV/EPSS/SSVC)
uv run mulitaminer sync-feeds
uv run mulitaminer prioritize outputs/runs/<run_dir>

# Score a finished run against a ground-truth XLSX (offline, no LLM)
uv run mulitaminer evaluate outputs/runs/<run_dir>
```

The `uv run mulitaminer ...` commands are identical on Linux, macOS and
Windows. Each run creates `outputs/runs/<timestamp>_<input>_<model>/` with
`results.json` (the records), `run.json` (config, tokens, cost, warnings) and
one file per requested export.

## Evaluation

`mulitaminer evaluate <run_dir>` aligns a run's records to a baseline XLSX
(auto-discovered next to the source PDF, or `--baseline`) and writes
`evaluation.json` + `evaluation.md` into the run directory: coverage
(recall/precision, missed/spurious findings) and per-field scores. Metrics are
derived from the record schema — exact match for numeric/categorical fields,
set F1 for reference lists, token F1 + ROUGE-L for text (select with
`--metrics`, list with `--list-metrics`). BERTScore and an NLI contradiction
check are optional and heavy: `uv sync --group eval`.

## Experiments

`mulitaminer experiment <dir> --models deepseek,ollama --runs 5` runs X
extractions per (model, report) over a directory of PDFs (scanner
auto-detected per file), evaluating each against its baseline. Local and
cloud models run **in parallel** (grouped by the credential/server that
enforces rate limits); completed runs are checkpointed so an interrupted
batch resumes where it stopped. Output lands under
`output_experiments/<scanner>/<model>/run_<n>/`.

## Security Concerns

- **API keys** live in a `.env` file that is gitignored. Never commit it.
- **What leaves your machine**: only the report's text chunks, sent to the
  LLM provider you choose. With local models (Ollama, LM Studio) nothing
  leaves the machine at all. There is no telemetry.
- **Network egress** is limited to the endpoint of the provider you configure
  (e.g. `api.deepseek.com`, `api.openai.com`, `api.groq.com`,
  `api.anthropic.com`). Local models talk only to `localhost`.
- **Sensitive output**: extracted records contain hosts, ports and
  vulnerability detail. Run artifacts under `outputs/` are gitignored, but you
  are responsible for how they are stored and shared.

## Documentation

| Document | Description |
| --- | --- |
| [docs/USAGE.md](docs/USAGE.md) | All commands, flags, run artifacts and examples |
| [docs/CONFIG.md](docs/CONFIG.md) | API keys, model profiles and tunables |
| [docs/ADDING_A_MODEL.md](docs/ADDING_A_MODEL.md) | Plug a new LLM, cloud or local |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline stages, modules and design rules |
| [docs/SCANNER_CONFIGS.md](docs/SCANNER_CONFIGS.md) | Adding a scanner and the built-in config rationale |
| [docs/EXPORTS.md](docs/EXPORTS.md) | Export formats, who consumes each, field mapping |
| [docs/PRIORITIZATION.md](docs/PRIORITIZATION.md) | KEV/EPSS/SSVC remediation queue for a run |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Symptoms, causes and fixes |

## Development

```bash
uv run pytest    # full suite, offline (fake LLM)
```

## License

[MIT](LICENSE). Free to use, modify and distribute, including commercially.
Provided "as is", without warranties; you are responsible for the secure
handling of your data and API keys.
