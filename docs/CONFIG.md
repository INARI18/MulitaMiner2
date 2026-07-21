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

Profiles are declared in `src/mulitaminer/llm.py` (`MODELS`). Adding a model,
cloud or local, is one entry. Full guide with examples and the structured
output tradeoff: [ADDING_A_MODEL.md](ADDING_A_MODEL.md).

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
| `FEEDS_DIR` | `outputs/feeds` | Local KEV/EPSS snapshot for prioritization |

The prioritization EPSS threshold (`EPSS_LIKELY_THRESHOLD`, default 0.10) and
the SSVC decision tree are constants in `src/mulitaminer/prioritization.py`.
See [PRIORITIZATION.md](PRIORITIZATION.md).
