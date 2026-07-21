"""Block-anchored extraction loop tests with a scripted fake client."""
import json

from mulitaminer.extraction import extract_blocks, render_chunk
from mulitaminer.models import Block, TokenUsage
from mulitaminer.scanner_engine import get_scanner

PROFILE = get_scanner("openvas")


def _item(block_id: int, name: str = "Vuln") -> dict:
    return {"block_id": block_id, "Name": name, "severity": "HIGH", "cvss": 7.5}


class FakeClient:
    """Yields scripted per-call payloads: each entry is a list of items or an
    Exception to raise. Mimics LLMClient.extract's signature."""

    class _Profile:
        max_output_tokens = 100_000
        encoding = "cl100k_base"

    profile = _Profile()

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def extract(self, system_prompt, user_content, response_model):
        self.calls.append(user_content)
        payload = self.script.pop(0)
        if isinstance(payload, Exception):
            raise payload
        parsed = response_model.model_validate({"items": payload})
        return parsed, {"prompt_tokens": 10, "completion_tokens": 5,
                        "cost_usd": 0.0, "raw": "{}"}


def _blocks(n):
    return [Block(id=i, text=f"High (CVSS: 7.5)\nNVT: Vuln {i}", host="1.2.3.4",
                  port=80, protocol="tcp") for i in range(n)]


def test_happy_path_one_record_per_block():
    blocks = _blocks(3)
    client = FakeClient([[_item(0), _item(1), _item(2)]])
    records, warnings = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert len(records) == 3
    assert not warnings
    assert all(r.source == "OPENVAS" for r in records)
    assert all(r.host == "1.2.3.4" for r in records)


def test_missing_ids_are_resent_and_recovered():
    blocks = _blocks(3)
    client = FakeClient([
        [_item(0), _item(2)],   # call 1: block 1 missing
        [_item(1)],             # retry round: only block 1 re-sent
    ])
    records, warnings = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert len(records) == 3
    assert not warnings
    assert "### BLOCK 1" in client.calls[1]
    assert "### BLOCK 0" not in client.calls[1]  # targeted, not whole-chunk


def test_unknown_and_duplicate_ids_dropped_with_warning():
    blocks = _blocks(2)
    client = FakeClient([
        [_item(0), _item(0), _item(99)],  # dup 0, unknown 99, missing 1
        [_item(1)],
    ])
    records, warnings = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert len(records) == 2
    assert any("duplicate block_id 0" in w for w in warnings)
    assert any("unknown block_id 99" in w for w in warnings)


def test_retry_rounds_shrink_chunks():
    """A chunk that hit the output cap fails identically at the same size -
    retry rounds must re-send progressively smaller groups (4 -> 2 -> 1)."""
    blocks = _blocks(4)
    bad = json.JSONDecodeError("bad", "doc", 0)
    client = FakeClient([
        bad,                      # round 0: one chunk of 4 -> fails
        [_item(0), _item(1)],     # round 1: chunks of <=2
        bad,
        [_item(2)],               # round 2: chunks of 1
        [_item(3)],
    ])
    records, warnings = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert len(records) == 4
    assert not warnings
    round1_first = client.calls[1]
    assert "### BLOCK 0" in round1_first and "### BLOCK 1" in round1_first
    assert "### BLOCK 2" not in round1_first  # round 1 capped at 2 blocks
    assert client.calls[3].count("### BLOCK") == 1  # round 2 capped at 1


def test_invalid_json_retries_then_gives_up_with_warning():
    blocks = _blocks(1)
    bad = json.JSONDecodeError("bad", "doc", 0)
    client = FakeClient([bad, bad, bad])  # initial + RETRY_ROUNDS attempts
    records, warnings = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert records == []
    assert any("block 0 yielded no record" in w for w in warnings)


def test_count_parity_guarantee():
    """Raw record count == block count when the model eventually answers."""
    blocks = _blocks(7)
    client = FakeClient([
        [_item(i) for i in range(0, 4)],
        [_item(i) for i in range(4, 7)],
    ])
    records, warnings = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert len(records) == len(blocks)


def test_render_includes_context_header():
    text = render_chunk(_blocks(1))
    assert text.startswith("### BLOCK 0 (host: 1.2.3.4, port: 80/tcp)")


def test_port_backfill_from_block_context():
    blocks = _blocks(1)
    item = {"block_id": 0, "Name": "V", "severity": "LOW", "cvss": 1.0,
            "port": None, "protocol": None}
    client = FakeClient([[item]])
    records, _ = extract_blocks(blocks, PROFILE, client, TokenUsage())
    assert records[0].port == 80 and records[0].protocol == "tcp"


def test_oversized_single_block_is_truncated_with_declared_marker():
    """A block whose output cannot fit the
    model's cap is truncated at the INPUT tail (declared, never silent) so
    the finding survives with partial instances instead of being dropped."""
    big = Block(id=0, text="High (CVSS: 7.5)\nNVT: Huge\n" + ("instance line\n" * 40_000))
    seen = {}

    class CapturingClient(FakeClient):
        def extract(self, system_prompt, user_content, response_model):
            seen["content"] = user_content
            return super().extract(system_prompt, user_content, response_model)

    client = CapturingClient([[_item(0, "Huge")]])
    records, warnings = extract_blocks([big], PROFILE, client, TokenUsage())
    assert len(records) == 1
    assert "[TRUNCATED:" in seen["content"]
    assert len(seen["content"]) < len(big.text)
    assert any("input truncated" in w for w in warnings)
    assert sum("input truncated" in w for w in warnings) == 1  # warned once


def test_pseudo_protocol_context_never_enters_the_record():
    """OpenVAS 'general/CPE-T' headers are context for the LLM, not data."""
    block = Block(id=0, text="Log (CVSS: 0.0)\nNVT: CPE Inventory",
                  port="general", protocol="cpe-t")
    item = {"block_id": 0, "Name": "CPE Inventory", "severity": "LOG", "cvss": 0.0,
            "port": None, "protocol": None}
    records, warnings = extract_blocks([block], PROFILE, FakeClient([[item]]), TokenUsage())
    assert records[0].port == "general"
    assert records[0].protocol is None
    assert not warnings
