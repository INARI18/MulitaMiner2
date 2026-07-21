# MulitaMiner

Vulnerability extraction from security-scanner PDF reports using LLMs.

Clean-room rewrite of MulitaMiner with a typed in-memory pipeline, native
structured LLM output, and **block-anchored extraction**: segmentation counts
the report's findings deterministically before any LLM call, and the model
fills fields per block instead of "discovering" vulnerabilities — so the raw
output count matches the report, with or without deduplication.

## Supported

| | |
| --- | --- |
| Scanners | OpenVAS/Greenbone, Tenable WAS |
| Cloud models | DeepSeek, OpenAI (gpt-4o / gpt-4o-mini), Groq (Llama 3.3 70B) |
| Local models | Ollama, LM Studio — and any OpenAI-compatible server (vLLM, llama.cpp); **no API key needed** |
| Outputs | JSON (primary) + `run.json` metadata; exports: XLSX, CSV, SARIF 2.1.0, DefectDojo Generic JSON, CAIS, CSAF 2.0 |

## Install

```bash
uv sync
cp .env.example .env    # cloud API keys only; local models need none
```

## Usage

```bash
# Cloud (DeepSeek)
uv run mulitaminer extract report.pdf --scanner openvas --model deepseek --export xlsx

# Interoperability exports: SARIF (GitHub/DefectDojo/SonarQube) and
# DefectDojo Generic Findings JSON
uv run mulitaminer extract report.pdf --scanner openvas --model deepseek -e sarif -e generic

# Local (Ollama), keyless
uv run mulitaminer extract report.pdf --scanner tenable --model ollama --model-name qwen3

# Inspection artifacts (layout, blocks, raw LLM traffic) in the run dir
uv run mulitaminer extract report.pdf --scanner openvas --model deepseek --debug

uv run mulitaminer models    # list model profiles
uv run mulitaminer scanners  # list scanner profiles
```

Each run writes to `outputs/runs/<timestamp>_<input>_<model>/`:
`results.json` (+ `results.xlsx`/`.csv` on request) and `run.json` with the
config snapshot, token/cost accounting, duration, and any warnings.
Consolidation (Tenable base+instances pairing, severity normalization,
identical-record merging) always runs — block-anchored extraction already
yields one record per report finding, so there is no dedup knob to tune.

## Design

- `docs/superpowers/specs/` — the approved architecture spec.
- `docs/superpowers/plans/` — the phased implementation plan with per-phase
  verification state (kept current; a fresh session can resume from it).
- `tools/compare_backends.py` — PDF backend bake-off (pypdfium2 is the default
  after matching pdfplumber's marker counts 10-40x faster).
- `tools/compare_v1_v2.py` — golden parity against MulitaMiner v1 outputs.

## Tests

```bash
uv run pytest
```

Unit + end-to-end tests run offline (fake LLM); the live smoke test uses
DeepSeek cloud.

## License

MIT.
