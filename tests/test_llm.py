"""LLM client tests with a stubbed transport; no network."""
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from mulitaminer.llm import (
    FatalLLMError,
    LLMClient,
    all_models,
    clean_response,
    get_model,
    load_llm_profile,
    _resolve_api_key,
)

# Profiles now come from configs/llms/*.json; the dict shape is unchanged.
MODELS = all_models()


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
    assert _resolve_api_key(MODELS["nuextract"]) == "local"


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


# --- JSON registry -----------------------------------------------------------


def test_registry_loads_builtin_profiles():
    models = all_models()
    for key in ("deepseek", "gpt-4o-mini", "gpt-4o", "llama-3.3-70b",
                "nuextract", "haiku"):
        assert key in models
    assert models["haiku"].api_key_env == "CLAUDE_API_KEY"
    assert models["haiku"].base_url.startswith("https://api.anthropic.com")


def test_registry_local_profile_omits_api_key_field():
    # nuextract.json has no api_key_env at all -> keyless local profile
    assert all_models()["nuextract"].is_local
    assert all_models()["nuextract"].price_in == 0.0


def test_registry_user_dir_plugs_new_model(tmp_path, monkeypatch):
    from mulitaminer.llm import _registry

    (tmp_path / "mymodel.json").write_text(json.dumps({
        "key": "mymodel", "model": "my-model-v1",
        "base_url": "http://localhost:9999/v1",
        "context_window": 16000, "max_output_tokens": 4000,
    }), encoding="utf-8")
    monkeypatch.setenv("MULITAMINER2_LLMS_DIR", str(tmp_path))
    _registry.cache_clear()
    try:
        models = all_models()
        assert "mymodel" in models and models["mymodel"].is_local
    finally:
        _registry.cache_clear()


def test_registry_rejects_unknown_and_missing_fields(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"key": "x", "model": "y", "context_window": 1, '
                   '"max_output_tokens": 1, "api_key": "oops"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown field"):
        load_llm_profile(bad)
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text('{"key": "x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        load_llm_profile(incomplete)
