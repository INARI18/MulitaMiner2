"""Typed data models; single source of truth for the vulnerability record.
The LLM contract (`extraction_model_for`) is derived from the record model."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

# Informational tier: OpenVAS emits LOG, Tenable INFO; consolidation maps INFO->LOG.
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "LOG", "INFO"]

# Marks fields the LLM is NOT responsible for producing; the pipeline fills
# them. Used to derive the LLM response contract (see extraction_model_for).
_PIPELINE_FILLED = {"json_schema_extra": {"llm_produced": False}}


class VulnRecord(BaseModel):
    """Core contract shared by every scanner. Validated, stable.

    Scanner-specific extras live in subclasses (OpenVASRecord / TenableRecord).
    """

    # allow undeclared keys; accept `Name` and `name`; keep post-validation
    # writes schema-checked.
    model_config = ConfigDict(extra="allow", populate_by_name=True, validate_assignment=True)

    name: str = Field(alias="Name")
    description: list[str] = []
    solution: list[str] = []
    impact: list[str] = []
    insight: list[str] = []
    references: list[str] = []

    # Shared wide schema: every scanner emits all fields (null/empty where
    # N/A) so output columns stay stable across scanners.
    detection_result: list[str] = []
    detection_method: list[str] = []
    product_detection_result: list[str] = []
    log_method: list[str] = []
    plugin: int | None = None
    plugin_details: dict = {}
    instances: list = []

    cvss: float | int | None = None  # numeric score; Tenable overrides with raw CVSS strings
    severity: Severity

    # Filled by the pipeline from report context, never by the LLM.
    host: str | None = Field(default=None, **_PIPELINE_FILLED)
    port: int | str | None = None
    protocol: Literal["tcp", "udp"] | None = None

    # Stamped from the scanner profile, never prompted.
    source: str = Field(default="", **_PIPELINE_FILLED)

    @field_validator("plugin_details", "instances", mode="before")
    @classmethod
    def _junk_empty_to_container(cls, value, info):
        """Coerce "-"/""/null (the report's empty idiom) to the empty container."""
        if value in ("", "-", None):
            return {} if info.field_name == "plugin_details" else []
        return value


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
    """LLM response-item model: `block_id` + the record's LLM-produced fields.
    extra="forbid" closes the JSON Schema, as structured-output modes require."""
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
    host/port/protocol/severity_hint are context recovered from headers around
    the block; they feed the prompt header and field backfill."""

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
