"""Tunable constants, calibrated empirically against real scanner reports.
Change them only with a parity run to back it up."""
from pathlib import Path

# Root for all run artifacts (each run gets its own subdirectory).
OUTPUTS_DIR = Path("outputs") / "runs"
# Local KEV/EPSS feed snapshot (regenerable daily cache). Lives at the repo
# root, NOT under outputs/: it is a persistent input for prioritization, and
# cleaning old runs must not destroy it. Deliberately a visible project-local
# dir (not an OS user-data dir), so the cache never accumulates silently
# outside the project; the path is CWD-relative as a documented consequence.
FEEDS_DIR = Path("feeds")

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
