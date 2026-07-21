"""Exporter seam + generic (DefectDojo) + SARIF mappings."""
import json

import pytest

from mulitaminer.exporters import EXPORTERS, get_exporter
from mulitaminer.exporters.generic import cves_from
from mulitaminer.models import OpenVASRecord

RECORDS = [
    OpenVASRecord(
        name="Ingreslock Backdoor", severity="HIGH", cvss=7.5, port=1524,
        protocol="tcp", host="10.0.0.5",
        description=["A backdoor is installed."],
        solution=["Clean the host."],
        references=["https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2011-0001",
                    "See also CVE-2011-0002 and cve-2011-0001"],
    ),
    OpenVASRecord(name="CGI Scanning Consolidation", severity="LOG", cvss=0.0,
                  port=443, protocol="tcp", host="10.0.0.5"),
]


def test_registry_has_all_formats():
    assert {"xlsx", "csv", "generic", "sarif", "cais", "csaf"} <= set(EXPORTERS)
    with pytest.raises(ValueError, match="Unknown export format"):
        get_exporter("pdf")


def test_cve_extraction_dedupes_case_insensitively():
    assert cves_from(RECORDS[0]) == ["CVE-2011-0001", "CVE-2011-0002"]


def test_generic_defectdojo_mapping(tmp_path):
    path = get_exporter("generic")(RECORDS, OpenVASRecord, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings = payload["findings"]
    assert len(findings) == 2
    high, log = findings
    assert high["title"] == "Ingreslock Backdoor"
    assert high["severity"] == "High"
    assert high["cve"] == "CVE-2011-0001"
    assert high["endpoints"] == ["10.0.0.5:1524"]
    assert high["mitigation"] == "Clean the host."
    assert log["severity"] == "Info"       # LOG -> Info
    assert log["cvssv3_score"] == 0.0      # zero is a value, not missing


def test_sarif_structure_levels_and_rule_dedup(tmp_path):
    path = get_exporter("sarif")(RECORDS + [RECORDS[0]], OpenVASRecord, tmp_path)
    sarif = json.loads(path.read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "MulitaMiner"
    # 3 results but only 2 distinct rules (repeat reuses its rule).
    assert len(run["results"]) == 3
    assert len(run["tool"]["driver"]["rules"]) == 2
    first, log_result, repeat = run["results"]
    assert first["level"] == "error"       # HIGH
    assert log_result["level"] == "note"   # LOG
    assert first["ruleId"] == repeat["ruleId"]
    assert first["locations"][0]["logicalLocations"][0]["fullyQualifiedName"] == "10.0.0.5:1524"
    assert first["properties"]["cvss"] == 7.5


def test_cais_mapping(tmp_path):
    from mulitaminer.models import Instance, TenableRecord

    tenable = TenableRecord(
        name="HSTS Missing", severity="HIGH", plugin=98056, host="example.com",
        description=["No HSTS."], solution=["Enable HSTS."],
        references=["CWE 693", "CVE-2020-0001"],
        cvss=["CVSSV3 BASE SCORE 6.5", "CVSSV3 VECTOR CVSS:3.0/AV:N/AC:L"],
        instances=[Instance(instance="https://a")],
    )
    path = get_exporter("cais")(RECORDS + [tenable], OpenVASRecord, tmp_path)
    assert path.name == "results.cais.csv"
    rows = json.loads((tmp_path / "results.cais.json").read_text(encoding="utf-8"))
    openvas_row, _, tenable_row = rows
    assert openvas_row["definition.name"] == "Ingreslock Backdoor"
    assert openvas_row["asset.display_ipv4_address"] == "10.0.0.5"
    assert openvas_row["asset.system_type"] == "Network Service"
    assert openvas_row["definition.cve"] == "CVE-2011-0001, CVE-2011-0002"
    assert openvas_row["definition.cvss3.base_score"] == 7.5
    assert openvas_row["state"] == "open"
    assert tenable_row["asset.display_fqdn"] == "example.com"
    assert tenable_row["asset.system_type"] == "Web Application"
    assert tenable_row["definition.id"] == "98056"
    assert tenable_row["definition.cwe"] == "CWE-693"
    assert tenable_row["definition.cvss3.base_vector"] == "CVSS:3.0/AV:N/AC:L"


def test_csaf_document_structure(tmp_path):
    path = get_exporter("csaf")(RECORDS, OpenVASRecord, tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["document"]["csaf_version"] == "2.0"
    assert doc["document"]["category"] == "csaf_security_advisory"
    tracking = doc["document"]["tracking"]
    assert tracking["id"].startswith("MULITAMINER-")
    assert tracking["initial_release_date"]
    assert len(doc["vulnerabilities"]) == 2
    high, log = doc["vulnerabilities"]
    assert high["cve"] == "CVE-2011-0001"
    assert high["remediations"][0]["details"] == "Clean the host."
    assert "cve" not in log  # no references -> no cve key
    products = {p["product_id"]: p["name"] for p in doc["product_tree"]["full_product_names"]}
    assert products == {"HOST-1": "10.0.0.5"}
    assert high["product_status"]["known_affected"] == ["HOST-1"]


def test_sarif_rule_help_carries_solution(tmp_path):
    path = get_exporter("sarif")(RECORDS, OpenVASRecord, tmp_path)
    sarif = json.loads(path.read_text(encoding="utf-8"))
    rules = {r["id"]: r for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    backdoor = next(r for rid, r in rules.items() if "Ingreslock" in r["name"])
    assert backdoor["help"]["text"] == "Clean the host."
