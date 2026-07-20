"""Consolidation identity and merge rules (policies come from scanner JSONs)."""
from mulitaminer2.consolidate import normalize_name
from mulitaminer2.models import Instance, OpenVASRecord, TenableRecord
from mulitaminer2.scanners import get_scanner

consolidate_openvas = get_scanner("openvas").consolidate
consolidate_tenable = get_scanner("tenable").consolidate


def _ov(name, port=80, cvss=5.0, host="1.1.1.1", **kw):
    return OpenVASRecord(
        name=name, severity="MEDIUM", cvss=cvss, port=port, protocol="tcp", host=host, **kw
    )


def test_normalize_name_collapses_case_and_whitespace():
    assert normalize_name("  SSL/TLS:   Cert  ") == normalize_name("ssl/tls: cert")


def test_openvas_dedupe_merges_same_identity_keeps_most_complete():
    a = _ov("TLS Weak Cipher")
    b = _ov("TLS  weak  cipher", **{"description": ["Weak ciphers enabled."]})
    merged, log_lines = consolidate_openvas([a, b], False)
    assert len(merged) == 1
    assert merged[0].description == ["Weak ciphers enabled."]
    assert log_lines


def test_openvas_different_port_is_a_different_finding():
    merged, _ = consolidate_openvas([_ov("X", port=80), _ov("X", port=443)], False)
    assert len(merged) == 2


def test_openvas_allow_duplicates_keeps_everything():
    merged, _ = consolidate_openvas([_ov("X"), _ov("X")], True)
    assert len(merged) == 2


def test_cvss_zero_counts_as_filled():
    """v1 nuance: a Log finding's 0.0 must not lose to a null-cvss duplicate."""
    with_zero = _ov("Log finding", cvss=0.0)
    without = _ov("Log finding", cvss=None, description=["text"])
    merged, _ = consolidate_openvas([with_zero, without], False)
    assert merged[0].cvss == 0.0


def _tn(name, plugin=98056, instances=(), **kw):
    return TenableRecord(
        name=name, severity="HIGH", plugin=plugin,
        instances=[Instance(**i) for i in instances], **kw
    )


def test_tenable_base_and_instances_blocks_pair_up_always():
    base = _tn("HSTS Missing", description=["No HSTS header."])
    inst = _tn("HSTS Missing Instances (2)",
               instances=[{"instance": "https://a"}, {"instance": "https://b"}])
    merged, _ = consolidate_tenable([base, inst], True)
    assert len(merged) == 1
    assert merged[0].description == ["No HSTS header."]
    assert len(merged[0].instances) == 2
    assert merged[0].name == "HSTS Missing"


def test_tenable_info_normalizes_to_log_after_pairing():
    rec = _tn("Info finding")
    rec.severity = "INFO"
    merged, _ = consolidate_tenable([rec], True)
    assert merged[0].severity == "LOG"
