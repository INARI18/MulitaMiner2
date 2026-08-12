"""Block-anchored extraction: the LLM fills fields per block, never discovers.
Every block ID must come back exactly once; missing IDs are re-sent in smaller
groups, unknown/duplicate IDs are dropped with a warning."""
from __future__ import annotations

import json
import logging
from collections import Counter
from functools import lru_cache

from openai import APITimeoutError
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from mulitaminer import settings
from mulitaminer.chunking import pack
from mulitaminer.llm import LLMClient
from mulitaminer.models import Block, Chunk, TokenUsage, VulnRecord, extraction_model_for
from mulitaminer.negation import gate_records
from mulitaminer.scanner_engine import ScannerProfile
from mulitaminer.ui import NULL_PROGRESS, Progress

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
    # Backfill from segmentation context what the LLM could not see. OpenVAS
    # emits pseudo-protocols in headers ("general/CPE-T"); those stay context
    # for the LLM but never enter the typed protocol field.
    if record.port is None and block.port is not None:
        record.port = block.port
        if block.protocol in ("tcp", "udp"):
            record.protocol = block.protocol
    return record


def extract_blocks(
    blocks: list[Block],
    profile: ScannerProfile,
    client: LLMClient,
    usage: TokenUsage,
    debug_sink: list | None = None,
    progress: Progress | None = None,
    drops: Counter | None = None,
    retries: Counter | None = None,
) -> tuple[list[VulnRecord], list[str], list[dict]]:
    """Extract every block; returns (records ordered by block id, warnings,
    negation flags).

    drops, if given, is tallied by category (unknown_id, duplicate_id,
    validation_error, unrecovered); retries is tallied by chunk-failure reason
    (bad_json, bad_shape). Both feed the run summary. Negation flags come from
    the flag-only gate in mulitaminer.negation, run against the source blocks."""
    progress = progress or NULL_PROGRESS
    if drops is None:
        drops = Counter()
    if retries is None:
        retries = Counter()
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
        # Shrink chunks each retry round (4 -> 2 -> 1): a response that hit
        # the output cap fails identically at the same size.
        chunks, pack_warnings = pack(
            pending,
            max_blocks_per_chunk=max(1, profile.max_vulns_per_chunk // (2 ** round_no)),
            token_budget=client.profile.max_output_tokens,
            encoding_name=client.profile.encoding,
        )
        if round_no == 0:
            warnings.extend(pack_warnings)
        if round_no:
            progress.retry_round(round_no, len(chunks))

        unresolved: list[Block] = []
        for chunk in chunks:
            unresolved.extend(
                _extract_chunk(chunk, prompt, response_model, profile, client,
                               usage, records, warnings, by_id, debug_sink, progress,
                               drops, retries)
            )
        pending = unresolved

    if pending:
        drops["unrecovered"] += len(pending)
    for block in pending:
        warnings.append(
            f"block {block.id} yielded no record after "
            f"{settings.RETRY_ROUNDS + 1} attempts; dropped"
        )
    negation_flags = gate_records(records, by_id,
                                  dict(profile.field_metric_overrides))
    if negation_flags:
        warnings.append(
            f"negation gate: {len(negation_flags)} flip candidate(s) flagged; "
            "see negation_flags in run.json"
        )
    ordered = [records[i] for i in sorted(records)]
    return ordered, warnings, negation_flags


def _truncate_oversized(chunk: Chunk, client: LLMClient, warnings: list[str]) -> list[Block]:
    """Cut the input tail of a block too big for the model's output cap,
    with an explicit marker and a warning. Core fields at the top survive."""
    if len(chunk.blocks) != 1:
        return chunk.blocks
    budget = int(client.profile.max_output_tokens * settings.CHUNK_SAFETY_MARGIN)
    if chunk.token_estimate <= budget:
        return chunk.blocks
    block = chunk.blocks[0]
    limit = int(budget * settings.FALLBACK_CHARS_PER_TOKEN)
    truncated = block.text[:limit].rsplit("\n", 1)[0] + (
        "\n[TRUNCATED: block exceeded the model's output budget; remaining content omitted]"
    )
    message = (
        f"block {block.id}: input truncated from {len(block.text)} to {len(truncated)} "
        "chars to fit the model's output budget; trailing instances omitted"
    )
    if message not in warnings:  # retry rounds re-truncate; warn once
        warnings.append(message)
    return [block.model_copy(update={"text": truncated})]


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
    progress: Progress = NULL_PROGRESS,
    drops: Counter | None = None,
    retries: Counter | None = None,
) -> list[Block]:
    """Process one chunk; returns the blocks left unresolved."""
    if drops is None:
        drops = Counter()
    if retries is None:
        retries = Counter()
    expected = {b.id for b in chunk.blocks}
    send_blocks = _truncate_oversized(chunk, client, warnings)
    try:
        parsed, call_usage = client.extract(prompt, render_chunk(send_blocks), response_model)
    except (json.JSONDecodeError, ValidationError, APITimeoutError) as exc:
        # bad_json: response was not valid JSON (usually output truncated at the
        # token cap). bad_shape: JSON parsed but did not fit the response schema.
        # timeout: the call outran the client deadline (a slow model on a heavy
        # block generating toward the output cap). All three are chunk-level
        # failures: the blocks go to retry (smaller next round), never fatal.
        if isinstance(exc, json.JSONDecodeError):
            reason = "bad_json"
        elif isinstance(exc, APITimeoutError):
            reason = "timeout"
        else:
            reason = "bad_shape"
        log.warning("Chunk %d: invalid response (%s); its blocks go to retry",
                    chunk.index, type(exc).__name__)
        retries[reason] += 1
        progress.chunk_failed(reason)
        return chunk.blocks

    usage.add(call_usage["prompt_tokens"], call_usage["completion_tokens"],
              call_usage["cost_usd"])
    if debug_sink is not None:
        debug_sink.append({"chunk": chunk.index, "blocks": sorted(expected),
                           "response": call_usage["raw"]})

    seen: set[int] = set()        # ids already consumed in this response
    succeeded: set[int] = set()   # ids that produced a valid record
    for item in parsed.items:
        bid = item.block_id
        if bid not in expected:
            warnings.append(f"chunk {chunk.index}: unknown block_id {bid} dropped")
            drops["unknown_id"] += 1
            continue
        if bid in seen:
            warnings.append(f"chunk {chunk.index}: duplicate block_id {bid} dropped")
            drops["duplicate_id"] += 1
            continue
        seen.add(bid)
        try:
            records[bid] = _to_record(item, by_id[bid], profile)
            succeeded.add(bid)
        except ValidationError as exc:
            warnings.append(f"block {bid}: record failed validation ({exc.error_count()} errors)")
            drops["validation_error"] += 1

    missing = expected - succeeded
    log.info("Chunk %d: %d/%d blocks extracted", chunk.index, len(succeeded), len(expected))
    progress.chunk_done(len(succeeded), len(expected))
    return [by_id[i] for i in sorted(missing)]
