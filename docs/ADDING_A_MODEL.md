# Adding a Model

Every provider MulitaMiner talks to speaks the OpenAI-compatible chat API, so
adding a model means **dropping one JSON file** — no Python. Built-in profiles
live in `src/mulitaminer/configs/llms/`; your own profiles go in any directory
pointed to by the `MULITAMINER2_LLMS_DIR` environment variable (same plug-in
mechanism as scanners).

## The three cases

| Case | base_url | api_key_env |
| --- | --- | --- |
| Cloud provider | The provider's endpoint | The env var holding the key |
| Local server (Ollama, LM Studio) | The localhost endpoint | **Omit the field** (keyless) |
| Any OpenAI-compatible server (vLLM, llama.cpp, TGI) | Wherever it runs | Omit, or a var if it needs one |

## Cloud model

`mistral-large.json` in your `MULITAMINER2_LLMS_DIR`:

```json
{
  "key": "mistral-large",
  "model": "mistral-large-latest",
  "base_url": "https://api.mistral.ai/v1",
  "api_key_env": "MISTRAL_API_KEY",
  "context_window": 128000,
  "max_output_tokens": 8000,
  "price_in": 2.0,
  "price_out": 6.0
}
```

Then `uv run mulitaminer extract report.pdf -s openvas -m mistral-large`.

Anthropic's Claude works through its OpenAI-compatible endpoint — see the
built-in `claude-haiku.json` (`base_url` `https://api.anthropic.com/v1/`,
key in `ANTHROPIC_API_KEY`).

## Local model

Ollama and LM Studio expose an OpenAI-compatible server on localhost and need
no key — their configs simply **have no `api_key_env` field**. The two
built-in profiles (`ollama`, `lmstudio`) are generic: pick the actual model at
runtime with `--model-name`.

```bash
# Ollama, any pulled model
uv run mulitaminer extract report.pdf -s openvas -m ollama --model-name qwen3

# LM Studio, whatever is loaded
uv run mulitaminer extract report.pdf -s openvas -m lmstudio --model-name my-model
```

To pin a specific local model as its own profile, copy `ollama.json`, change
`key` and `model`, and leave `api_key_env` out. Any other OpenAI-compatible
server works by setting `base_url` to its address.

## Structured output: the one field that matters

`supports_json_schema` decides how the model is asked to return JSON:

- `true`: strict JSON-Schema response format. The server guarantees the shape.
  Use it for OpenAI models and LM Studio (which supports it natively).
- `false` (the default): `json_object` mode plus validation on our side. Use
  it for providers without strict schema support (DeepSeek, Groq, Ollama).

If unsure, leave it out. A wrong `true` fails fast with a provider error;
`false` always works, just with our validation and retry doing the enforcing.

## Field reference

Required: `key`, `model`, `context_window`, `max_output_tokens`. Everything
else is optional with sensible defaults.

| Field | Meaning |
| --- | --- |
| `key` | CLI name (`--model`) |
| `model` | Provider model id (`--model-name` overrides at runtime) |
| `base_url` | Provider endpoint; omit for api.openai.com |
| `api_key_env` | Env var with the key; **omit for local/keyless** |
| `context_window` | Provider context limit (informational) |
| `max_output_tokens` | Output cap; this drives chunk sizing, so keep it honest |
| `supports_json_schema` | Strict schema vs `json_object` + validation (default `false`) |
| `price_in` / `price_out` | USD per 1M tokens, for the run cost report (default 0) |
| `reasoning_tags` | `true` strips `<think>` blocks (reasoning models like Qwen3) |
| `temperature` | Defaults to 0 for deterministic extraction |
| `encoding` | tiktoken encoding for token counting; default `cl100k_base` |

A config with an unknown or missing field fails at load with an error naming
the file and the valid field list.

## Verify

```bash
uv run mulitaminer models    # your new profile should be listed
```

Then run a small extraction. If a cloud key is missing you get a clear
`No API key for model '...'` naming the env var to set.
