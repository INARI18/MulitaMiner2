"""The plug-a-scanner promise: a JSON + prompt dropped in a user directory
registers a working scanner with zero Python."""
import json

from mulitaminer.scanner_engine import _registry


CUSTOM_CONFIG = {
    "name": "customscan",
    "source": "CUSTOMSCAN",
    "record": "generic",
    "prompt": "customscan_prompt.txt",
    "max_vulns_per_chunk": 5,
    "marker_pattern": "^FINDING\\s+(HIGH|LOW)\\b",
    "identity": ["name"],
}

REPORT = """\
Intro text without findings.
FINDING HIGH
Something bad on the server.
FINDING LOW
Something mildly bad.
"""


def test_user_scanner_dir_registers_and_segments(tmp_path):
    (tmp_path / "customscan.json").write_text(json.dumps(CUSTOM_CONFIG), encoding="utf-8")
    (tmp_path / "customscan_prompt.txt").write_text("Extract findings.", encoding="utf-8")

    registry = _registry(str(tmp_path))
    assert "customscan" in registry
    assert {"openvas", "tenable"} <= set(registry)  # built-ins still present

    profile = registry["customscan"]
    blocks = profile.segment(REPORT)
    assert [b.severity_hint for b in blocks] == ["HIGH", "LOW"]
    assert blocks[0].text.startswith("FINDING HIGH")
    assert "Intro text" not in blocks[0].text
    assert profile.prompt() == "Extract findings."


FIELD_CONFIG = {
    "name": "fieldscan",
    "source": "FIELDSCAN",
    "prompt": "fieldscan_prompt.txt",
    "max_vulns_per_chunk": 5,
    "marker_pattern": "^FINDING\\s+(HIGH|LOW)\\b",
    "fields": {"category": "str", "tags": "list"},
}


def test_config_fields_extend_record_extraction_and_evaluation(tmp_path):
    """A scanner can declare extra record fields in its JSON, with zero Python;
    they flow into the extraction contract, output, and per-field evaluation."""
    (tmp_path / "fieldscan.json").write_text(json.dumps(FIELD_CONFIG), encoding="utf-8")
    (tmp_path / "fieldscan_prompt.txt").write_text("Extract.", encoding="utf-8")

    record_type = _registry(str(tmp_path))["fieldscan"].record_type
    assert "category" in record_type.model_fields and "tags" in record_type.model_fields

    from mulitaminer.models import extraction_model_for

    assert "category" in extraction_model_for(record_type).model_fields  # LLM can emit it

    from mulitaminer.evaluation.fields import field_plans

    assert {"category", "tags"} <= {p.name for p in field_plans(record_type)}  # scored

    record = record_type(name="x", severity="HIGH", category="Web server", tags=["a", "b"])
    assert record.category == "Web server" and record.tags == ["a", "b"]
