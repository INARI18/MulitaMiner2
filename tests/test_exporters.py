"""Exporter seam + generic (DefectDojo) + SARIF mappings."""
import json

import pytest

from mulitaminer2.exporters import EXPORTERS, get_exporter
from mulitaminer2.exporters.generic import cves_from
from mulitaminer2.models import OpenVASRecord

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
    assert {"xlsx", "csv", "generic", "sarif"} <= set(EXPORTERS)
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
    assert run["tool"]["driver"]["name"] == "MulitaMiner2"
    # 3 results but only 2 distinct rules (repeat reuses its rule).
    assert len(run["results"]) == 3
    assert len(run["tool"]["driver"]["rules"]) == 2
    first, log_result, repeat = run["results"]
    assert first["level"] == "error"       # HIGH
    assert log_result["level"] == "note"   # LOG
    assert first["ruleId"] == repeat["ruleId"]
    assert first["locations"][0]["logicalLocations"][0]["fullyQualifiedName"] == "10.0.0.5:1524"
    assert first["properties"]["cvss"] == 7.5


def test_sarif_rule_help_carries_solution(tmp_path):
    path = get_exporter("sarif")(RECORDS, OpenVASRecord, tmp_path)
    sarif = json.loads(path.read_text(encoding="utf-8"))
    rules = {r["id"]: r for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    backdoor = next(r for rid, r in rules.items() if "Ingreslock" in r["name"])
    assert backdoor["help"]["text"] == "Clean the host."
