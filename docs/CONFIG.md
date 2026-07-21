# Configuration

## API keys

Keys live in `.env` (gitignored), loaded automatically. Each cloud model
profile reads one env var; local profiles need none.

| Env var | Used by |
| --- | --- |
| `DEEPSEEK_API_KEY` | `deepseek` |
| `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
| `GROQ_API_KEY` | `llama-3.3-70b` |

## Model profiles

Profiles are declared in `src/mulitaminer/llm.py` (`MODELS`). Every provider
speaks the OpenAI-compatible API, so a profile is just:

| Field | Meaning |
| --- | --- |
| `key` | CLI name (`--model`) |
| `model` | Provider model id (`--model-name` overrides at runtime) |
| `base_url` | Provider endpoint; `None` means api.openai.com |
| `api_key_env` | Env var with the key; `None` means local/keyless |
| `context_window` / `max_output_tokens` | Token limits; output drives chunk sizing |
| `supports_json_schema` | Strict structured output vs `json_object` + validation |
| `price_in` / `price_out` | USD per 1M tokens, for the run cost report |
| `reasoning_tags` | Strip `<think>` blocks from responses |

To add a model: add one `ModelProfile` entry. Any OpenAI-compatible server
(vLLM, llama.cpp, TGI) works by pointing `base_url` at it.

## Scanners

One JSON + one prompt per scanner. Reference: [SCANNER_CONFIGS.md](SCANNER_CONFIGS.md).
Plug external scanners with the `MULITAMINER_SCANNERS_DIR` env var.

## Tunables

`src/mulitaminer/settings.py`, calibrated empirically:

| Constant | Value | Meaning |
| --- | --- | --- |
| `CHUNK_SAFETY_MARGIN` | 0.85 | Fraction of the token budget actually used |
| `CHUNK_CHAR_CEILING_MIN` | 30000 | Floor of the per-chunk character ceiling |
| `RETRY_ROUNDS` | 2 | Targeted re-send rounds for unresolved blocks |
| `OUTPUTS_DIR` | `outputs/runs` | Default run artifacts root |
