# Adding a Model

Every provider MulitaMiner talks to speaks the OpenAI-compatible chat API, so
adding a model means adding one `ModelProfile` entry in
`src/mulitaminer/llm.py` (the `MODELS` dict). No other code changes.

## The three cases

| Case | base_url | api_key_env |
| --- | --- | --- |
| Cloud provider | The provider's endpoint | The env var holding the key |
| Local server (Ollama, LM Studio) | The localhost endpoint | `None` (keyless) |
| Any OpenAI-compatible server (vLLM, llama.cpp, TGI) | Wherever it runs | `None` or a var if it needs one |

## Cloud model

```python
"mistral-large": ModelProfile(
    key="mistral-large",             # the --model name
    model="mistral-large-latest",    # the provider's model id
    base_url="https://api.mistral.ai/v1",
    api_key_env="MISTRAL_API_KEY",   # add this var to .env and .env.example
    context_window=128_000,
    max_output_tokens=8_000,
    supports_json_schema=False,       # see "Structured output" below
    price_in=2.00,                    # USD per 1M tokens, for the cost report
    price_out=6.00,
),
```

Then `uv run mulitaminer extract report.pdf -s openvas -m mistral-large`.

## Local model

Ollama and LM Studio expose an OpenAI-compatible server on localhost and need
no key. The two built-in profiles (`ollama`, `lmstudio`) are generic: pick the
actual model at runtime with `--model-name`.

```bash
# Ollama, any pulled model
uv run mulitaminer extract report.pdf -s openvas -m ollama --model-name qwen3

# LM Studio, whatever is loaded
uv run mulitaminer extract report.pdf -s openvas -m lmstudio --model-name my-model
```

To pin a specific local model as its own profile, copy the `ollama` entry,
give it a `key` and `model`, and keep `api_key_env=None`. Any other
OpenAI-compatible server works by setting `base_url` to its address.

## Structured output: the one field that matters

`supports_json_schema` decides how the model is asked to return JSON:

- `True`: strict JSON-Schema response format. The server guarantees the shape.
  Use it for OpenAI models and LM Studio (which supports it natively).
- `False`: `json_object` mode plus validation on our side. Use it for
  providers without strict schema support (DeepSeek, Groq, Ollama).

If unsure, start with `False`. A wrong `True` fails fast with a provider error;
`False` always works, just with our validation and retry doing the enforcing.

## Field reference

| Field | Meaning |
| --- | --- |
| `key` | CLI name (`--model`) |
| `model` | Provider model id (`--model-name` overrides at runtime) |
| `base_url` | Provider endpoint; `None` means api.openai.com |
| `api_key_env` | Env var with the key; `None` means local/keyless |
| `context_window` | Provider context limit (informational) |
| `max_output_tokens` | Output cap; this drives chunk sizing, so keep it honest |
| `supports_json_schema` | Strict schema vs `json_object` + validation |
| `price_in` / `price_out` | USD per 1M tokens, for the run cost report (0 for local) |
| `reasoning_tags` | `True` strips `<think>` blocks (reasoning models like Qwen3) |
| `temperature` | Defaults to 0 for deterministic extraction |
| `encoding` | tiktoken encoding for token counting; default `cl100k_base` |

## Verify

```bash
uv run mulitaminer models    # your new profile should be listed
```

Then run a small extraction. If a cloud key is missing you get a clear
`No API key for model '...'` naming the env var to set.
