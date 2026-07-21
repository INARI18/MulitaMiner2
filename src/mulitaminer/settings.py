"""Tunable constants, calibrated empirically against real scanner reports.
Change them only with a parity run to back it up."""
from pathlib import Path

# Root for all run artifacts (each run gets its own subdirectory).
OUTPUTS_DIR = Path("outputs") / "runs"
# Local KEV/EPSS feed snapshot (regenerable daily cache).
FEEDS_DIR = Path("outputs") / "feeds"

# --- Chunk packing ----------------------------------------------------------
# Fraction of the theoretical token budget actually used, leaving headroom for
# the prompt template and tokenizer estimation error.
CHUNK_SAFETY_MARGIN = 0.85
# Absolute floor for the chunk character ceiling, and the token multiplier
# above it: ceiling = max(MIN, chunk_tokens * MULT).
CHUNK_CHAR_CEILING_MIN = 30_000
CHUNK_CHAR_CEILING_TOKEN_MULT = 2
# Chars-per-token estimate when no tiktoken encoding matches the model.
FALLBACK_CHARS_PER_TOKEN = 3.5

# --- Extraction retry --------------------------------------------------------
# Rounds of targeted re-sends for blocks whose IDs are missing from the LLM
# response, before giving up with a warning. (v2 design §6)
RETRY_ROUNDS = 2
