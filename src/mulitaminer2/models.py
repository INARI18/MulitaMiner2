"""Typed data models — the single source of truth for the vulnerability record.

Ported from MulitaMiner v1 `configs/vuln_schema.py` (field names, types, and the
lessons in its comments), with two v2 changes:

- `source` is no longer produced by the LLM: it is pinned per scanner record
  type and stamped by the pipeline (the scanner is already known from the CLI).
- The LLM response contract (`extraction_model_for`) is *derived* from the
  record model instead of hand-copied, so the two can never drift.

Everything between pipeline stages travels as these objects; nothing is written
to disk except final run artifacts and optional debug dumps.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

# Severity spans both scanners' vocabularies: OpenVAS uses LOG for the
# informational tier, Tenable WAS uses INFO. One shared Literal on purpose —
# consolidation normalizes INFO -> LOG post-extraction, so a Tenable record is
# INFO before that step and LOG after; a single field must accept both.
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "LOG", "INFO"]

# Marks fields the LLM is NOT responsible for producing; the pipeline fills
# them. Used to derive the LLM response contract (see extraction_model_for).
_PIPELINE_FILLED = {"json_schema_extra": {"llm_produced": False}}


class VulnRecord(BaseModel):
    """Core contract shared by every scanner. Validated, stable.

    Scanner-specific extras never live here — they go in `scanner_specific`
    or in a subclass (see OpenVASRecord / TenableRecord).
    """

    # extra="allow": tolerate keys a scanner emits that we didn't declare,
    # rather than hard-failing. Safety net, not the organizing mechanism.
    # populate_by_name: accept BOTH the JSON key `Name` (v1 output format,
    # kept for baseline compatibility) and the pythonic attribute `name`.
    # validate_assignment: post-validation writes (context backfill, merge
    # backfill, severity normalization) must obey the schema too — a bad
    # value can never enter a record after the fact.
    model_config = ConfigDict(extra="allow", populate_by_name=True, validate_assignment=True)

    name: str = Field(alias="Name")
    description: list[str] = []
    solution: list[str] = []
    impact: list[str] = []
    insight: list[str] = []
    references: list[str] = []

    # Both scanners' prompts emit all of these: OpenVAS fills detection_*/
    # log_method with real content and plugin/plugin_details/instances as
    # null/empty; Tenable does the reverse. The base declares them all;
    # subclasses refine the types of the ones a scanner really populates.
    detection_result: list[str] = []
    detection_method: list[str] = []
    product_detection_result: list[str] = []
    log_method: list[str] = []
    plugin: int | None = None
    plugin_details: dict = {}
    instances: list = []

    # cvss on the base is the OpenVAS shape: one numeric score (int or float,
    # so 7 vs 7.0 isn't a type error) or null. Tenable overrides it to a list
    # of raw CVSS strings — genuinely a different type per scanner.
    cvss: float | int | None = None
    severity: Severity

    # host is not extracted by the LLM — the pipeline assigns it from the
    # report's per-host section (OpenVAS `Host scan start` recovery).
    host: str | None = Field(default=None, **_PIPELINE_FILLED)
    port: int | str | None = None
    protocol: Literal["tcp", "udp"] | None = None

    # v2: stamped from the scanner profile, never prompted (removes a
    # hallucination surface). Subclasses pin it with a Literal default.
    source: str = Field(default="", **_PIPELINE_FILLED)

    # Overflow bucket: a new scanner can dump anything here with zero changes
    # to this file. Promote entries to a subclass when they deserve typing.
    scanner_specific: dict = Field(default_factory=dict, **_PIPELINE_FILLED)


class PluginDetails(BaseModel):
    """Tenable's Plugin Details block. Empty ({}) for OpenVAS."""

    model_config = ConfigDict(extra="allow")

    publication_date: str | None = None
    modification_date: str | None = None
    family: str | None = None
    severity: str | None = None
    plugin_id: int | None = None


class Instance(BaseModel):
    """One Tenable WAS instance (a URL/endpoint the finding was seen on)."""

    model_config = ConfigDict(extra="allow")

    instance: str = ""
    input_type: str = ""
    input_name: str = ""
    payload: str = ""
    proof: str = ""
    output: str = ""
    request_method: str = ""
    http_status_code: int | None = None
    http_protocol: str = ""
    response_content_type: str = ""


class OpenVASRecord(VulnRecord):
    """OpenVAS/Greenbone. Network scan: CVE-rich, has detection metadata."""

    source: Literal["OPENVAS"] = Field(default="OPENVAS", **_PIPELINE_FILLED)


class TenableRecord(VulnRecord):
    """Tenable WAS. Web app scan: mostly CVE-less, per-URL instances."""

    source: Literal["TENABLEWAS"] = Field(default="TENABLEWAS", **_PIPELINE_FILLED)

    cvss: list[str] = []
    plugin_details: PluginDetails = Field(default_factory=PluginDetails)
    instances: list[Instance] = []


def _is_llm_produced(field) -> bool:
    extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
    return extra.get("llm_produced", True)


@lru_cache
def extraction_model_for(record_type: type[VulnRecord]) -> type[BaseModel]:
    """Derive the LLM response-item model for a scanner's record type.

    The extraction model is `block_id` plus every LLM-produced field of the
    record (pipeline-filled fields — host, source, scanner_specific — are
    excluded). Derived, not hand-copied: change the record, the LLM contract
    follows. `extra="forbid"` so the generated JSON Schema closes the object
    (`additionalProperties: false`), which structured-output modes require.
    """
    fields: dict = {"block_id": (int, Field(description="ID of the source block (### BLOCK n)"))}
    for name, f in record_type.model_fields.items():
        if not _is_llm_produced(f):
            continue
        fields[name] = (f.annotation, f)
    return create_model(
        f"{record_type.__name__}Extraction",
        __config__=ConfigDict(extra="forbid", populate_by_name=True),
        **fields,
    )


# --- Pipeline flow objects ---------------------------------------------------


class Block(BaseModel):
    """One marker-delimited report segment: exactly one candidate finding.

    host/port/protocol/severity_hint are context recovered by the scanner's
    segmentation from headers *around* the block (they may not appear inside
    its text). They are rendered into the block's prompt header and used to
    backfill fields the LLM could not see.
    """

    id: int
    text: str
    host: str | None = None
    port: int | str | None = None
    protocol: str | None = None
    severity_hint: str | None = None


class Chunk(BaseModel):
    """An ordered group of whole blocks sent to the LLM in one call."""

    index: int
    blocks: list[Block]
    token_estimate: int


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0

    def add(self, prompt: int, completion: int, cost: float) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.calls += 1
        self.cost_usd += cost


class RunResult(BaseModel):
    """Everything a run produced, in memory. Writers serialize from this."""

    records: list[VulnRecord]
    warnings: list[str] = []
    usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_s: float = 0.0
    block_count: int = 0
    chunk_count: int = 0
    config: dict = {}
