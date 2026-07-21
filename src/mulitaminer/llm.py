"""One OpenAI-compatible client for every provider, cloud or local.
Provider differences reduce to a ModelProfile; local profiles are keyless.
Structured output via JSON-Schema where supported, else json_object +
Pydantic validation."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from openai import APIStatusError, AuthenticationError, OpenAI, PermissionDeniedError
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class FatalLLMError(Exception):
    """Unrecoverable provider error (auth, quota, unknown model) — abort the run."""


@dataclass(frozen=True)
class ModelProfile:
    key: str                      # CLI name
    model: str                    # provider model id
    base_url: str | None          # None = api.openai.com
    api_key_env: str | None    # None = local/keyless
    context_window: int
    max_output_tokens: int
    supports_json_schema: bool
    price_in: float               # USD per 1M input tokens (0 for local)
    price_out: float
    reasoning_tags: bool = False  # strip <think>…</think> from responses
    temperature: float = 0.0      # deterministic extraction
    encoding: str = "cl100k_base"

    @property
    def is_local(self) -> bool:
        return self.api_key_env is None


MODELS: dict[str, ModelProfile] = {
    "deepseek": ModelProfile(
        key="deepseek",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        context_window=64_000,
        max_output_tokens=8_000,
        supports_json_schema=False,  # json_object mode + validation
        price_in=0.14,
        price_out=0.28,
    ),
    "gpt-4o-mini": ModelProfile(
        key="gpt-4o-mini",
        model="gpt-4o-mini",
        base_url=None,
        api_key_env="OPENAI_API_KEY",
        context_window=128_000,
        max_output_tokens=16_000,
        supports_json_schema=True,
        price_in=0.15,
        price_out=0.60,
    ),
    "gpt-4o": ModelProfile(
        key="gpt-4o",
        model="gpt-4o",
        base_url=None,
        api_key_env="OPENAI_API_KEY",
        context_window=128_000,
        max_output_tokens=16_000,
        supports_json_schema=True,
        price_in=2.50,
        price_out=10.00,
    ),
    "llama-3.3-70b": ModelProfile(
        key="llama-3.3-70b",
        model="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        context_window=128_000,
        max_output_tokens=8_000,
        supports_json_schema=False,
        price_in=0.59,
        price_out=0.79,
    ),
    "ollama": ModelProfile(
        key="ollama",
        model="llama3",  # override with --model-name
        base_url="http://localhost:11434/v1",
        api_key_env=None,
        context_window=32_000,
        max_output_tokens=8_000,
        supports_json_schema=False,
        price_in=0.0,
        price_out=0.0,
        reasoning_tags=True,
    ),
    "lmstudio": ModelProfile(
        key="lmstudio",
        model="local-model",  # override with --model-name
        base_url="http://localhost:1234/v1",
        api_key_env=None,
        context_window=32_000,
        max_output_tokens=8_000,
        supports_json_schema=True,  # LM Studio supports json_schema natively
        price_in=0.0,
        price_out=0.0,
        reasoning_tags=True,
    ),
}


def get_model(key: str) -> ModelProfile:
    try:
        return MODELS[key.lower()]
    except KeyError:
        raise ValueError(f"Unknown model '{key}'. Available: {sorted(MODELS)}")


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
