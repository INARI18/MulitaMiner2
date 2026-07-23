"""Consolidation identity and merge rules (policies come from scanner JSONs)."""
from mulitaminer.consolidate import normalize_name
from mulitaminer.models import Instance
from mulitaminer.scanner_engine import get_scanner

OpenVASRecord = get_scanner("openvas").record_type
TenableRecord = get_scanner("tenable").record_type

consolidate_openvas = get_scanner("openvas").consolidate
consolidate_tenable = get_scanner("tenable").consolidate


def _ov(name, port=80, cvss=5.0, host="1.1.1.1", **kw):
    return OpenVASRecord(
        name=name, severity="MEDIUM", cvss=cvss, port=port, protocol="tcp", host=host, **kw
    )


def test_normalize_name_collapses_case_and_whitespace():
    assert normalize_name("  SSL/TLS:   Cert  ") == normalize_name("ssl/tls: cert")


def test_only_fully_identical_records_merge():
    """User rule: a duplicate is an exact repeat (name compared normalized).
    Same key with different content = two real findings, never merged."""
    a = _ov("TLS Weak Cipher")
    identical = _ov("TLS  weak  CIPHER")  # same after name normalization
    different = _ov("TLS Weak Cipher", description=["Weak ciphers enabled."])
    merged, log_lines = consolidate_openvas([a, identical])
    assert len(merged) == 1 and log_lines
    merged, log_lines = consolidate_openvas([a, different])
    assert len(merged) == 2 and not log_lines


def test_openvas_different_port_is_a_different_finding():
    merged, _ = consolidate_openvas([_ov("X", port=80), _ov("X", port=443)])
    assert len(merged) == 2


def test_repeating_findings_with_distinct_content_survive():
    """Legitimate repeats on the same
    host/port with different content stay separate."""
    a = _ov("Services", description=["ssh detected"])
    b = _ov("Services", description=["http detected"])
    merged, _ = consolidate_openvas([a, b])
    assert len(merged) == 2


def _tn(name, plugin=98056, instances=(), **kw):
    return TenableRecord(
        name=name, severity="HIGH", plugin=plugin,
        instances=[Instance(**i) for i in instances], **kw
    )


def test_tenable_base_and_instances_blocks_pair_up_always():
    base = _tn("HSTS Missing", description=["No HSTS header."])
    inst = _tn("HSTS Missing Instances (2)",
               instances=[{"instance": "https://a"}, {"instance": "https://b"}])
    merged, _ = consolidate_tenable([base, inst])
    assert len(merged) == 1
    assert merged[0].description == ["No HSTS header."]
    assert len(merged[0].instances) == 2
    assert merged[0].name == "HSTS Missing"


def test_tenable_keeps_native_info_severity():
    rec = _tn("Info finding")
    rec.severity = "INFO"
    merged, _ = consolidate_tenable([rec])
    assert merged[0].severity == "INFO"  # each scanner keeps its own tier
