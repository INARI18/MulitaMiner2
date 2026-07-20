# MulitaMiner2

Vulnerability extraction from security-scanner PDF reports using LLMs.

Clean-room rewrite of MulitaMiner: typed pipeline, structured LLM output,
block-anchored extraction, single source of truth per scanner.

**Status:** under construction (see `docs/superpowers/plans/` for progress).

## Quickstart

```bash
uv sync
cp .env.example .env   # fill in cloud API keys; local models need none
uv run mulitaminer2 --help
```
