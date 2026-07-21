"""One OpenAI-compatible client for every provider, cloud or local.
Provider differences reduce to a ModelProfile; local profiles are keyless.
Profiles are loaded from JSON configs (built-ins in configs/llms/, user
profiles via MULITAMINER2_LLMS_DIR) — adding a model needs no Python.
Structured output via JSON-Schema where supported, else json_object +
Pydantic validation."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

from openai import APIStatusError, AuthenticationError, OpenAI, PermissionDeniedError
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class FatalLLMError(Exception):
    """Unrecoverable provider error (auth, quota, unknown model); abort the run."""


@dataclass(frozen=True)
class ModelProfile:
    key: str                      # CLI name
    model: str                    # provider model id
    context_window: int
    max_output_tokens: int
    base_url: str | None = None   # None = api.openai.com
    # Absent in local/keyless configs (ollama, lmstudio) — a local model has
    # no API key, so the JSON simply omits the field.
    api_key_env: str | None = None
    supports_json_schema: bool = False
    price_in: float = 0.0         # USD per 1M input tokens (0 for local)
    price_out: float = 0.0
    reasoning_tags: bool = False  # strip <think>…</think> from responses
    temperature: float = 0.0      # deterministic extraction
    encoding: str = "cl100k_base"

    @property
    def is_local(self) -> bool:
        return self.api_key_env is None


_BUILTIN_LLM_DIR = Path(__file__).parent / "configs" / "llms"
_PROFILE_FIELDS = {f.name for f in fields(ModelProfile)}


def load_llm_profile(config_path: Path) -> ModelProfile:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    unknown = set(cfg) - _PROFILE_FIELDS
    if unknown:
        raise ValueError(
            f"LLM config {config_path} has unknown field(s) {sorted(unknown)}; "
            f"valid fields: {sorted(_PROFILE_FIELDS)}"
        )
    try:
        return ModelProfile(**cfg)
    except TypeError as exc:
        raise ValueError(f"LLM config {config_path} is invalid: {exc}") from exc


@lru_cache
def _registry(extra_dir: str | None) -> dict[str, ModelProfile]:
    profiles: dict[str, ModelProfile] = {}
    dirs = [_BUILTIN_LLM_DIR]
    if extra_dir:
        user_dir = Path(extra_dir)
        # Accept both a flat user dir and one mirroring the llms/ split.
        dirs += [user_dir, user_dir / "llms"]
    for directory in dirs:
        for config in sorted(directory.glob("*.json")):
            profile = load_llm_profile(config)
            profiles[profile.key] = profile
    return profiles


def all_models() -> dict[str, ModelProfile]:
    return _registry(os.getenv("MULITAMINER2_LLMS_DIR"))


def get_model(key: str) -> ModelProfile:
    models = all_models()
    try:
        return models[key.lower()]
    except KeyError:
        raise ValueError(f"Unknown model '{key}'. Available: {sorted(models)}")


def _resolve_api_key(profile: ModelProfile) -> str:
    if profile.is_local:
        return "local"  # dummy; keyless servers ignore it
    if value := os.getenv(profile.api_key_env):
        return value
    raise FatalLLMError(
        f"No API key for model '{profile.key}'. "
        f"Set {profile.api_key_env} in your .env (see .env.example)."
    )


def clean_response(text: str, reasoning_tags: bool) -> str:
    """Strip markdown fences and reasoning blocks before JSON parsing."""
    if reasoning_tags:
        text = _THINK_RE.sub("", text)
    text = _FENCE_RE.sub("", text.strip())
    return text.strip()


class LLMClient:
    """Chat calls with structured output and per-call usage accounting."""

    def __init__(
        self,
        profile: ModelProfile,
        model_name: str | None = None,
        transport: OpenAI | None = None,
    ) -> None:
        self.profile = profile
        self.model = model_name or profile.model
        # SDK built-in exponential backoff covers rate limits / transient 5xx.
        self._client = transport or OpenAI(
            base_url=profile.base_url,
            api_key=_resolve_api_key(profile),
            max_retries=3,
            timeout=600.0,
        )

    def extract(
        self, system_prompt: str, user_content: str, response_model: type[BaseModel]
    ) -> tuple[BaseModel, dict]:
        """One structured extraction call. Returns (validated model, usage dict).

        Raises FatalLLMError for auth/quota/unknown-model, and lets Pydantic
        ValidationError / json.JSONDecodeError propagate so the extraction
        loop can apply its targeted-retry policy.
        """
        if self.profile.supports_json_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "vulnerability_extraction",
                    "schema": response_model.model_json_schema(by_alias=True),
                },
            }
        else:
            # json_object mode: providers require the word "JSON" in the
            # conversation; both prompt templates mention it.
            response_format = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=self.profile.temperature,
                max_tokens=self.profile.max_output_tokens,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise FatalLLMError(
                f"Provider rejected the credentials for '{self.profile.key}': {exc}"
            ) from exc
        except APIStatusError as exc:
            if exc.status_code in (402, 404):  # quota exhausted / unknown model
                raise FatalLLMError(
                    f"Fatal provider error for '{self.profile.key}' "
                    f"(HTTP {exc.status_code}): {exc}"
                ) from exc
            raise

        raw = response.choices[0].message.content or ""
        cleaned = clean_response(raw, self.profile.reasoning_tags)
        data = json.loads(cleaned)
        parsed = self._validate_envelope(data, response_model)

        usage = getattr(response, "usage", None)
        return self._package(parsed, usage, raw)

    @staticmethod
    def _validate_envelope(data, response_model: type[BaseModel]) -> BaseModel:
        """Validate, tolerating one shape slip: items returned without the
        {"items": [...]} envelope get re-wrapped. Content is never repaired."""
        try:
            return response_model.model_validate(data)
        except ValidationError:
            if isinstance(data, list):
                return response_model.model_validate({"items": data})
            if isinstance(data, dict) and "block_id" in data:
                return response_model.model_validate({"items": [data]})
            raise

    def _package(self, parsed: BaseModel, usage, raw: str) -> tuple[BaseModel, dict]:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = (
            prompt_tokens / 1e6 * self.profile.price_in
            + completion_tokens / 1e6 * self.profile.price_out
        )
        return parsed, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "raw": raw,
        }
