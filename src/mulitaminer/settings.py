"""Tunable constants, calibrated empirically against real scanner reports.
Change them only with a parity run to back it up."""
from pathlib import Path

OUTPUTS_DIR = Path("outputs") / "runs"
# Feed cache at repo root, not under outputs/: it is a persistent input and
# must survive run cleanup.
FEEDS_DIR = Path("feeds")

# --- Chunk packing ----------------------------------------------------------
CHUNK_SAFETY_MARGIN = 0.85          # fraction of the token budget actually used
# Char ceiling = max(MIN, chunk_tokens * MULT).
CHUNK_CHAR_CEILING_MIN = 30_000
CHUNK_CHAR_CEILING_TOKEN_MULT = 2
FALLBACK_CHARS_PER_TOKEN = 3.5      # when no tiktoken encoding matches the model

# --- Extraction retry --------------------------------------------------------
RETRY_ROUNDS = 2                    # targeted re-sends for missing block IDs
SDK_MAX_RETRIES = 3                 # provider SDK's transient-error retries
# Per-request deadline; a local call slower than this is a degenerate
# generation. On timeout the chunk goes to retry, never fatal.
REQUEST_TIMEOUT_S = 120.0

# --- Evaluation --------------------------------------------------------------
DEFAULT_ALIGN_THRESHOLD = 0.7       # extraction<->baseline similarity cutoff
