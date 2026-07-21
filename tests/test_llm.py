"""LLM client tests with a stubbed transport; no network."""
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from mulitaminer.llm import (
    MODELS,
    FatalLLMError,
    LLMClient,
    clean_response,
    get_model,
    _resolve_api_key,
)


class Items(BaseModel):
    items: list[int]


class FakeTransport:
    def __init__(self, content: str):
        self._content = content
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


def test_local_profiles_are_keyless():
    assert _resolve_api_key(MODELS["ollama"]) == "local"
    assert _resolve_api_key(MODELS["lmstudio"]) == "local"


def test_cloud_profile_without_env_raises_actionable_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(FatalLLMError, match="DEEPSEEK_API_KEY"):
        _resolve_api_key(MODELS["deepseek"])


def test_clean_response_strips_think_and_fences():
    raw = "<think>let me reason...</think>\n```json\n{\"items\": [1]}\n```"
    assert json.loads(clean_response(raw, reasoning_tags=True)) == {"items": [1]}
    # Without reasoning_tags the think block is kept (cloud models don't emit it).
    assert "<think>" in clean_response(raw, reasoning_tags=False)


def test_extract_parses_validates_and_accounts_usage():
    transport = FakeTransport('{"items": [1, 2, 3]}')
    client = LLMClient(MODELS["deepseek"], transport=transport)
    parsed, usage = client.extract("sys", "user", Items)
    assert parsed.items == [1, 2, 3]
    assert usage["prompt_tokens"] == 100 and usage["completion_tokens"] == 50
    assert usage["cost_usd"] == pytest.approx(100 / 1e6 * 0.14 + 50 / 1e6 * 0.28)
    # DeepSeek has no json_schema support -> json_object mode.
    assert transport.last_kwargs["response_format"] == {"type": "json_object"}
    assert transport.last_kwargs["temperature"] == 0.0


def test_extract_uses_json_schema_when_supported():
    transport = FakeTransport('{"items": []}')
    client = LLMClient(MODELS["gpt-4o-mini"], transport=transport)
    client.extract("sys", "user", Items)
    assert transport.last_kwargs["response_format"]["type"] == "json_schema"


def test_extract_propagates_invalid_json_for_retry_policy():
    client = LLMClient(MODELS["deepseek"], transport=FakeTransport("not json at all"))
    with pytest.raises(json.JSONDecodeError):
        client.extract("sys", "user", Items)


def test_envelope_slips_are_rewrapped():
    """Models sometimes skip the {"items": [...]}
    envelope, especially on single-block calls. Shape is adapted; content
    is never repaired."""

    class Item(BaseModel):
        block_id: int

    class Envelope(BaseModel):
        items: list[Item]

    bare_object = FakeTransport('{"block_id": 44}')
    parsed, _ = LLMClient(MODELS["deepseek"], transport=bare_object).extract("s", "u", Envelope)
    assert [i.block_id for i in parsed.items] == [44]

    bare_list = FakeTransport('[{"block_id": 1}, {"block_id": 2}]')
    parsed, _ = LLMClient(MODELS["deepseek"], transport=bare_list).extract("s", "u", Envelope)
    assert [i.block_id for i in parsed.items] == [1, 2]

    garbage = FakeTransport('{"nothing": true}')
    with pytest.raises(Exception):
        LLMClient(MODELS["deepseek"], transport=garbage).extract("s", "u", Envelope)


def test_unknown_model_key_raises():
    with pytest.raises(ValueError, match="Unknown model"):
        get_model("gpt4")
