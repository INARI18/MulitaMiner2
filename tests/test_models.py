"""Model contract tests: validation, source stamping, derived LLM contract."""
import pytest
from pydantic import ValidationError

from mulitaminer.models import VulnRecord, extraction_model_for
from mulitaminer.scanner_engine import get_scanner

# Record types are now assembled from each scanner's config (core + declared
# "fields"), not hardcoded subclasses.
OpenVASRecord = get_scanner("openvas").record_type
TenableRecord = get_scanner("tenable").record_type

GOOD_OPENVAS = {
    "Name": "Ingreslock Backdoor",
    "description": ["A backdoor is installed on the remote host."],
    "severity": "HIGH",
    "cvss": 7.5,
    "port": 1524,
    "protocol": "tcp",
}


def test_valid_record_accepted_via_alias():
    rec = OpenVASRecord.model_validate(GOOD_OPENVAS)
    assert rec.name == "Ingreslock Backdoor"
    assert rec.cvss == 7.5


def test_source_is_pipeline_filled_not_extracted():
    # source is stamped by the pipeline from the profile (profile.source),
    # never by the LLM, so it defaults empty and is absent from the contract.
    rec = OpenVASRecord.model_validate(GOOD_OPENVAS)
    assert rec.source == ""
    assert "source" not in extraction_model_for(OpenVASRecord).model_fields
    assert get_scanner("openvas").source == "OPENVAS"
    assert get_scanner("tenable").source == "TENABLEWAS"


def test_wrong_severity_rejected():
    with pytest.raises(ValidationError):
        OpenVASRecord.model_validate({**GOOD_OPENVAS, "severity": "BANANA"})


def test_openvas_cvss_is_numeric_tenable_cvss_is_list():
    with pytest.raises(ValidationError):
        OpenVASRecord.model_validate({**GOOD_OPENVAS, "cvss": ["AV:N/AC:L"]})
    rec = TenableRecord.model_validate(
        {"Name": "XSS", "severity": "MEDIUM", "cvss": ["CVSS:3.1/AV:N"]}
    )
    assert rec.cvss == ["CVSS:3.1/AV:N"]


def test_extraction_model_derives_from_record():
    model = extraction_model_for(OpenVASRecord)
    fields = set(model.model_fields)
    assert "block_id" in fields
    # Pipeline-filled fields must NOT be part of the LLM contract.
    assert {"host", "source"}.isdisjoint(fields)
    # LLM-produced fields must all be there.
    assert {"name", "description", "severity", "cvss", "port"} <= fields


def test_extraction_model_respects_scanner_types():
    ext = extraction_model_for(TenableRecord)
    item = ext.model_validate(
        {"block_id": 3, "Name": "XSS", "severity": "INFO", "cvss": ["CVSS:3.1/AV:N"]}
    )
    assert item.block_id == 3
    with pytest.raises(ValidationError):
        extraction_model_for(OpenVASRecord).model_validate(
            {"block_id": 1, "Name": "x", "severity": "LOW", "cvss": ["not-numeric"]}
        )


def test_extraction_model_forbids_unknown_keys():
    with pytest.raises(ValidationError):
        extraction_model_for(OpenVASRecord).model_validate(
            {"block_id": 1, "Name": "x", "severity": "LOW", "hallucinated": True}
        )


def test_extraction_json_schema_closes_objects():
    schema = extraction_model_for(OpenVASRecord).model_json_schema(by_alias=True)
    assert schema["additionalProperties"] is False
    assert "Name" in schema["properties"]


def test_junk_empty_structured_fields_are_coerced():
    """The report's empty-idiom ("-") leaks into the
    LLM's JSON for structured fields; coerce instead of failing the record."""
    rec = TenableRecord.model_validate(
        {"Name": "X", "severity": "LOW", "cvss": [], "plugin_details": "-", "instances": ""}
    )
    assert rec.plugin_details.model_dump()["plugin_id"] is None
    assert rec.instances == []


def test_base_record_requires_name_and_severity():
    with pytest.raises(ValidationError):
        VulnRecord.model_validate({"description": ["no name"]})
