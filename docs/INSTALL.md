# Installation

## Requirements

| Component | Requirement |
| --- | --- |
| Python | 3.11+ |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Network | Only for cloud LLM calls; local models work offline |

## Steps

```bash
git clone https://github.com/INARI18/MulitaMiner2.git
cd MulitaMiner2
uv sync
cp .env.example .env
```

Fill in `.env` with the keys for the cloud providers you use:

```env
DEEPSEEK_API_KEY="..."
OPENAI_API_KEY="..."
GROQ_API_KEY="..."
```

Local models (Ollama, LM Studio) need no key. Never commit `.env`.

## Verify

No API key needed for this check:

```bash
uv run mulitaminer segment resources/openvas/OpenVAS_JuiceShop.pdf --scanner openvas
```

Expected: `34 blocks found`. Then a real extraction (uses your key):

```bash
uv run mulitaminer extract resources/openvas/OpenVAS_JuiceShop.pdf -s openvas -m deepseek
```

Expected: `34 records (34 blocks)` and a new folder under `outputs/runs/`.
