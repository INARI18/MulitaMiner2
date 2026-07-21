"""Pack whole blocks into token-budgeted chunks.

Invariants (guarded by tests):
- blocks are never split — a block travels whole or alone;
- chunks never overlap and preserve block order;
- every block ends up in exactly one chunk.

Budgets combine three limits: token budget x safety margin,
character ceiling, and the scanner's max blocks per chunk. Because extraction
output largely mirrors the block text (fields quote it verbatim), the caller
should pass a token budget derived from the model's OUTPUT cap, which is the
binding constraint in practice.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from mulitaminer2 import settings
from mulitaminer2.models import Block, Chunk

log = logging.getLogger(__name__)

# Rough per-block prompt overhead: the "### BLOCK n (context...)" header plus
# the JSON key scaffolding of its response object.
_BLOCK_OVERHEAD_TOKENS = 60


@lru_cache
def _encoding(name: str):
    import tiktoken

    return tiktoken.get_encoding(name)


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """tiktoken count, with a chars-per-token estimate when the encoding is
    unavailable (offline first run, exotic local models)."""
    try:
        return len(_encoding(encoding_name).encode(text))
    except Exception:  # noqa: BLE001 — any tiktoken failure degrades to the estimate
        return int(len(text) / settings.FALLBACK_CHARS_PER_TOKEN)


def pack(
    blocks: list[Block],
    max_blocks_per_chunk: int,
    token_budget: int,
    encoding_name: str = "cl100k_base",
) -> tuple[list[Chunk], list[str]]:
    """Group whole blocks into chunks under all three budgets."""
    effective_budget = int(token_budget * settings.CHUNK_SAFETY_MARGIN)
    char_ceiling = max(
        settings.CHUNK_CHAR_CEILING_MIN,
        token_budget * settings.CHUNK_CHAR_CEILING_TOKEN_MULT,
    )

    chunks: list[Chunk] = []
    warnings: list[str] = []
    current: list[Block] = []
    current_tokens = 0
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_tokens, current_chars
        if current:
            chunks.append(
                Chunk(index=len(chunks), blocks=current, token_estimate=current_tokens)
            )
        current, current_tokens, current_chars = [], 0, 0

    for block in blocks:
        tokens = count_tokens(block.text, encoding_name) + _BLOCK_OVERHEAD_TOKENS
        chars = len(block.text)
        if tokens > effective_budget and not current:
            # Oversized single block: send it alone rather than dropping it.
            warnings.append(
                f"block {block.id} alone exceeds the token budget "
                f"({tokens} > {effective_budget}); sent as its own chunk"
            )
            current = [block]
            current_tokens, current_chars = tokens, chars
            flush()
            continue
        over = (
            len(current) >= max_blocks_per_chunk
            or current_tokens + tokens > effective_budget
            or current_chars + chars > char_ceiling
        )
        if over and current:
            flush()
        current.append(block)
        current_tokens += tokens
        current_chars += chars

    flush()
    log.info("Packed %d blocks into %d chunks", len(blocks), len(chunks))
    return chunks, warnings
