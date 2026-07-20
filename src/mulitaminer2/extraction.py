"""Block-anchored extraction: the LLM fills fields per block, never discovers.

Segmentation already knows the exact candidate count, so validation is exact:
- every input block ID must come back exactly once;
- missing IDs are re-sent alone (targeted retry, RETRY_ROUNDS rounds);
- unknown or duplicate IDs are dropped with a warning.

This is what makes the raw output count equal the marker count regardless of
deduplication — v1's chunk-level "discovery" extraction could silently gain or
lose findings at chunk boundaries.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from mulitaminer2 import settings
from mulitaminer2.chunking import pack
from mulitaminer2.llm import LLMClient
from mulitaminer2.models import Block, Chunk, TokenUsage, VulnRecord, extraction_model_for
from mulitaminer2.scanners.profile import ScannerProfile

log = logging.getLogger(__name__)


@lru_cache
def response_model_for(record_type: type[VulnRecord]) -> type[BaseModel]:
    """Container object for one call's items (top-level arrays are not allowed
    by providers' structured-output modes)."""
    item = extraction_model_for(record_type)
    return create_model(
        f"{record_type.__name__}Response",
        __config__=ConfigDict(extra="forbid"),
        items=(list[item], ...),
    )


def render_block(block: Block) -> str:
    context = []
    if block.host:
        context.append(f"host: {block.host}")
    if block.port is not None and block.protocol:
        context.append(f"port: {block.port}/{block.protocol}")
    suffix = f" ({', '.join(context)})" if context else ""
    return f"### BLOCK {block.id}{suffix}\n{block.text}"


def render_chunk(blocks: list[Block]) -> str:
    return "\n\n".join(render_block(b) for b in blocks)


def _to_record(item: BaseModel, block: Block, profile: ScannerProfile) -> VulnRecord:
    data = item.model_dump(by_alias=True, exclude={"block_id"})
    record = profile.record_type.model_validate({**data, "host": block.host})
    if not record.source:  # generic record types carry no pinned source
        record.source = profile.source
    # Backfill from segmentation context what the LLM could not see.
    if record.port is None and block.port is not None:
        record.port = block.port
        record.protocol = block.protocol
    return record


def extract_blocks(
    blocks: list[Block],
    profile: ScannerProfile,
    client: LLMClient,
    usage: TokenUsage,
    debug_sink: list | None = None,
) -> tuple[list[VulnRecord], list[str]]:
    """Extract every block; returns (records ordered by block id, warnings)."""
    prompt = profile.prompt()
    response_model = response_model_for(profile.record_type)
    by_id = {b.id: b for b in blocks}

    records: dict[int, VulnRecord] = {}
    warnings: list[str] = []
    pending = blocks

    for round_no in range(settings.RETRY_ROUNDS + 1):
        if not pending:
            break
        if round_no:
            log.info(
                "Retry round %d: re-sending %d unresolved block(s)", round_no, len(pending)
            )
        chunks, pack_warnings = pack(
            pending,
            max_blocks_per_chunk=profile.max_vulns_per_chunk,
            token_budget=client.profile.max_output_tokens,
            encoding_name=client.profile.encoding,
        )
        if round_no == 0:
            warnings.extend(pack_warnings)

        unresolved: list[Block] = []
        for chunk in chunks:
            unresolved.extend(
                _extract_chunk(chunk, prompt, response_model, profile, client,
                               usage, records, warnings, by_id, debug_sink)
            )
        pending = unresolved

    for block in pending:
        warnings.append(
            f"block {block.id} yielded no record after "
            f"{settings.RETRY_ROUNDS + 1} attempts; dropped"
        )
    ordered = [records[i] for i in sorted(records)]
    return ordered, warnings


def _extract_chunk(
    chunk: Chunk,
    prompt: str,
    response_model: type[BaseModel],
    profile: ScannerProfile,
    client: LLMClient,
    usage: TokenUsage,
    records: dict[int, VulnRecord],
    warnings: list[str],
    by_id: dict[int, Block],
    debug_sink: list | None,
) -> list[Block]:
    """Process one chunk; returns the blocks left unresolved."""
    expected = {b.id for b in chunk.blocks}
    try:
        parsed, call_usage = client.extract(prompt, render_chunk(chunk.blocks), response_model)
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning("Chunk %d: invalid response (%s); its blocks go to retry",
                    chunk.index, type(exc).__name__)
        return chunk.blocks

    usage.add(call_usage["prompt_tokens"], call_usage["completion_tokens"],
              call_usage["cost_usd"])
    if debug_sink is not None:
        debug_sink.append({"chunk": chunk.index, "blocks": sorted(expected),
                           "response": call_usage["raw"]})

    returned: set[int] = set()
    for item in parsed.items:
        bid = item.block_id
        if bid not in expected:
            warnings.append(f"chunk {chunk.index}: unknown block_id {bid} dropped")
            continue
        if bid in returned:
            warnings.append(f"chunk {chunk.index}: duplicate block_id {bid} dropped")
            continue
        returned.add(bid)
        try:
            records[bid] = _to_record(item, by_id[bid], profile)
        except ValidationError as exc:
            warnings.append(f"block {bid}: record failed validation ({exc.error_count()} errors)")

    missing = expected - returned
    log.info("Chunk %d: %d/%d blocks extracted", chunk.index, len(returned), len(expected))
    return [by_id[i] for i in sorted(missing)]
