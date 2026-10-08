"""Exporter seam + generic (DefectDojo) + SARIF mappings."""
import json

import pytest

from mulitaminer.exporters import EXPORTERS, get_exporter
from mulitaminer.exporters.generic import cves_from
from mulitaminer.scanner_engine import get_scanner

OpenVASRecord = get_scanner("openvas").record_type

RECORDS = [
    OpenVASRecord(
        name="Ingreslock Backdoor", severity="HIGH", cvss=7.5, port=1524,
        protocol="tcp", host="10.0.0.5", source="OPENVAS",
        description=["A backdoor is installed."],
        solution=["Clean the host."],
        references=["https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2011-0001",
                    "See also CVE-2011-0002 and cve-2011-0001"],
    ),
    OpenVASRecord(name="CGI Scanning Consolidation", severity="LOG", cvss=0.0,
                  port=443, protocol="tcp", host="10.0.0.5", source="OPENVAS"),
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
    from mulitaminer.models import Instance

    TenableRecord = get_scanner("tenable").record_type

    tenable = TenableRecord(
        name="HSTS Missing", severity="HIGH", plugin=98056, host="example.com",
        source="TENABLEWAS",
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
    # The backdoor cites 2 CVEs -> 2 entries; the LOG finding has none -> 1 entry.
    assert len(doc["vulnerabilities"]) == 3
    high, high2, log = doc["vulnerabilities"]
    assert (high["cve"], high2["cve"]) == ("CVE-2011-0001", "CVE-2011-0002")
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


ZAPRecord = get_scanner("zap").record_type


def _zap_record():
    from mulitaminer.models import Instance

    return ZAPRecord(
        name="SQL Injection", severity="High", plugin="40018", source="ZAP",
        solution=["Use prepared statements."],
        instances=[Instance(instance="http://172.30.7.1:3000/rest/products/search?q=1"),
                   Instance(instance="http://172.30.7.1:3000/rest/products/search?q=1"),
                   Instance(instance="http://172.30.7.1:3000/api/Users")],
    )


def test_severity_mapping_ignores_case(tmp_path):
    # ZAP emits title case ("High"); the LLM sometimes does too.
    finding = json.loads(get_exporter("generic")([_zap_record()], ZAPRecord, tmp_path)
                         .read_text(encoding="utf-8"))["findings"][0]
    result = json.loads(get_exporter("sarif")([_zap_record()], ZAPRecord, tmp_path)
                        .read_text(encoding="utf-8"))["runs"][0]["results"][0]
    assert finding["severity"] == "High"
    assert result["level"] == "error"


def test_hostless_record_falls_back_to_instance_urls(tmp_path):
    finding = json.loads(get_exporter("generic")([_zap_record()], ZAPRecord, tmp_path)
                         .read_text(encoding="utf-8"))["findings"][0]
    assert finding["endpoints"] == ["http://172.30.7.1:3000/rest/products/search?q=1",
                                    "http://172.30.7.1:3000/api/Users"]

    result = json.loads(get_exporter("sarif")([_zap_record()], ZAPRecord, tmp_path)
                        .read_text(encoding="utf-8"))["runs"][0]["results"][0]
    assert result["locations"][0]["logicalLocations"][0]["fullyQualifiedName"] == \
        "http://172.30.7.1:3000/rest/products/search?q=1"

    doc = json.loads(get_exporter("csaf")([_zap_record()], ZAPRecord, tmp_path)
                     .read_text(encoding="utf-8"))
    assert doc["product_tree"]["full_product_names"] == [
        {"product_id": "HOST-1", "name": "172.30.7.1:3000"}]
    vuln = doc["vulnerabilities"][0]
    assert vuln["product_status"]["known_affected"] == ["HOST-1"]
    assert vuln["remediations"][0]["product_ids"] == ["HOST-1"]


def test_generic_vulnerability_ids_are_strings(tmp_path):
    # DefectDojo docs: "List of strings", added after `cve`.
    finding = json.loads(get_exporter("generic")(RECORDS, OpenVASRecord, tmp_path)
                         .read_text(encoding="utf-8"))["findings"][0]
    assert finding["cve"] == "CVE-2011-0001"
    assert finding["vulnerability_ids"] == ["CVE-2011-0002"]


def test_sarif_has_physical_location_for_github(tmp_path):
    # GitHub code scanning drops results without a physicalLocation; network
    # findings have no file, so the host stands in (as Trivy does for images).
    result = json.loads(get_exporter("sarif")(RECORDS, OpenVASRecord, tmp_path)
                        .read_text(encoding="utf-8"))["runs"][0]["results"][0]
    physical = result["locations"][0]["physicalLocation"]
    assert physical["artifactLocation"]["uri"] == "10.0.0.5"
    assert physical["region"]["startLine"] == 1


@pytest.mark.parametrize("scanner, cvss", [
    ("nessus", ["CVSS v2.0 Base Score 5.8 (CVSS2#AV:A/AC:L/Au:N/C:P/I:P/A:P)",
                "CVSS v3.0 Base Score 6.5 (CVSS:3.0/AV:A/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:L)"]),
    ("tenable", ["CVSSV3 BASE SCORE 6.5",
                 "CVSSV3 VECTOR CVSS:3.0/AV:A/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:L"]),
])
def test_csaf_score_parses_both_formats_and_rates_by_score(tmp_path, scanner, cvss):
    record_type = get_scanner(scanner).record_type
    # Scanner says HIGH, score says MEDIUM: CSAF test 6.1.9 requires the latter.
    record = record_type(name="X", severity="HIGH", host="10.0.0.5",
                         source=scanner.upper(), cvss=cvss)
    doc = json.loads(get_exporter("csaf")([record], record_type, tmp_path)
                     .read_text(encoding="utf-8"))
    assert doc["vulnerabilities"][0]["scores"][0]["cvss_v3"] == {
        "version": "3.0",
        "vectorString": "CVSS:3.0/AV:A/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:L",
        "baseScore": 6.5,
        "baseSeverity": "MEDIUM",
    }


def test_port_zero_means_whole_host(tmp_path):
    # Nessus uses port 0 for host-level findings; DefectDojo drops "host:0".
    record = get_scanner("nessus").record_type(
        name="Traceroute Information", severity="NONE", host="10.0.0.5", port=0,
        source="NESSUS")
    finding = json.loads(get_exporter("generic")([record], type(record), tmp_path)
                         .read_text(encoding="utf-8"))["findings"][0]
    result = json.loads(get_exporter("sarif")([record], type(record), tmp_path)
                        .read_text(encoding="utf-8"))["runs"][0]["results"][0]
    assert finding["endpoints"] == ["10.0.0.5"]
    assert result["locations"][0]["logicalLocations"][0]["fullyQualifiedName"] == "10.0.0.5"


def test_sarif_rules_carry_security_severity(tmp_path):
    # GitHub and DefectDojo read it to show Critical/High/Medium/Low.
    sarif = json.loads(get_exporter("sarif")(RECORDS, OpenVASRecord, tmp_path)
                       .read_text(encoding="utf-8"))
    backdoor, log = sarif["runs"][0]["tool"]["driver"]["rules"]
    assert backdoor["properties"] == {"security-severity": "7.5", "tags": ["security"]}
    assert "properties" not in log  # informational: no security severity
    zap = json.loads(get_exporter("sarif")([_zap_record()], ZAPRecord, tmp_path)
                     .read_text(encoding="utf-8"))["runs"][0]["tool"]["driver"]["rules"][0]
    assert zap["properties"]["security-severity"] == "8.0"  # no CVSS: label midpoint


def test_csaf_carries_scanner_severity_as_impact_threat(tmp_path):
    doc = json.loads(get_exporter("csaf")(RECORDS, OpenVASRecord, tmp_path)
                     .read_text(encoding="utf-8"))
    assert doc["vulnerabilities"][0]["threats"] == [
        {"category": "impact", "details": "HIGH", "product_ids": ["HOST-1"]}]


def test_csaf_locationless_record_gets_placeholder_product(tmp_path):
    # Every vulnerability needs product_status (CSAF test 6.1.27.6).
    record = ZAPRecord(name="CSP Header Not Set", severity="Medium", source="ZAP")
    doc = json.loads(get_exporter("csaf")([record], ZAPRecord, tmp_path)
                     .read_text(encoding="utf-8"))
    assert doc["product_tree"]["full_product_names"] == [
        {"product_id": "HOST-1", "name": "unidentified target"}]
    assert doc["vulnerabilities"][0]["product_status"]["known_affected"] == ["HOST-1"]


def _openvas(name, host, refs, severity="HIGH", solution=()):
    return OpenVASRecord(name=name, severity=severity, host=host, source="OPENVAS",
                         references=list(refs), solution=list(solution))


def _csaf(tmp_path, records):
    return json.loads(get_exporter("csaf")(records, OpenVASRecord, tmp_path)
                      .read_text(encoding="utf-8"))["vulnerabilities"]


def test_csaf_one_entry_per_cve(tmp_path):
    # A finding citing 2 CVEs yields 2 entries; none is dropped (test 6.1.23 needs unique cve).
    vulns = _csaf(tmp_path, [_openvas("PHP Multiple", "10.0.0.5", ["CVE-2014-3668", "CVE-2014-3669"])])
    assert [v["cve"] for v in vulns] == ["CVE-2014-3668", "CVE-2014-3669"]
    assert vulns[1]["notes"][0]["title"] == "PHP Multiple"


def test_csaf_findings_sharing_a_cve_merge(tmp_path):
    # Two OpenVAS checks covering the same CVE (the real bwapp PHP case).
    vulns = _csaf(tmp_path, [
        _openvas("PHP Jan 2015", "10.0.0.5", ["CVE-2014-3668"], solution=["Update PHP."]),
        _openvas("PHP < 5.4.39", "10.0.0.5", ["CVE-2014-3668"], severity="MEDIUM",
                 solution=["Update PHP."]),
    ])
    assert len(vulns) == 1
    v = vulns[0]
    assert v["title"] == "PHP Jan 2015; PHP < 5.4.39"
    assert [n["title"] for n in v["notes"]] == ["PHP Jan 2015", "PHP < 5.4.39"]
    assert v["product_status"]["known_affected"] == ["HOST-1"]
    assert v["remediations"] == [{"category": "mitigation", "details": "Update PHP.",
                                  "product_ids": ["HOST-1"]}]
    assert [(t["details"], t["product_ids"]) for t in v["threats"]] == [
        ("HIGH", ["HOST-1"]), ("MEDIUM", ["HOST-1"])]


def test_csaf_same_finding_on_many_hosts_is_one_entry(tmp_path):
    # Nessus "IP Forwarding Enabled" on 3 hosts; also covers findings without a CVE.
    with_cve = [_openvas("IP Forwarding", h, ["CVE-1999-0511"]) for h in ("a", "b", "c")]
    no_cve = [_openvas("TCP Timestamps", h, [], severity="LOW") for h in ("a", "b")]
    vulns = _csaf(tmp_path, with_cve + no_cve)
    assert len(vulns) == 2
    assert vulns[0]["product_status"]["known_affected"] == ["HOST-1", "HOST-2", "HOST-3"]
    assert "cve" not in vulns[1]
    assert vulns[1]["product_status"]["known_affected"] == ["HOST-1", "HOST-2"]


def test_csaf_one_score_per_product(tmp_path):
    # CSAF test 6.1.7: at most one cvss_v3 score per product in a vulnerability.
    rt = get_scanner("tenable").record_type
    def rec(score):
        return rt(name=f"X{score}", severity="HIGH", host="h", source="TENABLEWAS",
                  references=["CVE-2020-0001"],
                  cvss=[f"CVSSV3 BASE SCORE {score}", "CVSSV3 VECTOR CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"])
    vulns = json.loads(get_exporter("csaf")([rec(9.8), rec(7.5)], rt, tmp_path)
                       .read_text(encoding="utf-8"))["vulnerabilities"]
    assert [s["cvss_v3"]["baseScore"] for s in vulns[0]["scores"]] == [9.8]


def test_generic_maps_scanner_detail_fields(tmp_path):
    # Real bwapp PHP case: v4 left description empty but extracted insight/detection.
    record = OpenVASRecord(
        name="PHP < 5.5.33", severity="CRITICAL", host="10.0.0.5", source="OPENVAS",
        description=["PHP is prone to multiple vulnerabilities."],
        insight=["The following flaws exist:", "- Use-after-free in wddx.c"],
        detection_method=["Checks if a vulnerable version is present."],
        detection_result=["Installed version: 5.5.9", "Fixed version: 5.5.33"],
    )
    finding = json.loads(get_exporter("generic")([record], OpenVASRecord, tmp_path)
                         .read_text(encoding="utf-8"))["findings"][0]
    assert finding["description"] == (
        "PHP is prone to multiple vulnerabilities.\n\n"
        "**Insight**\nThe following flaws exist:\n- Use-after-free in wddx.c")
    assert finding["steps_to_reproduce"] == (
        "**Detection method**\nChecks if a vulnerable version is present.\n\n"
        "**Detection result**\nInstalled version: 5.5.9\nFixed version: 5.5.33")


def test_csaf_threat_severity_case_insensitive(tmp_path):
    # Same CVE from two findings labelled "HIGH" and "High" -> one impact threat.
    vulns = _csaf(tmp_path, [_openvas("A", "h", ["CVE-2014-3668"], severity="HIGH"),
                             _openvas("B", "h", ["CVE-2014-3668"], severity="High")])
    assert [t["details"] for t in vulns[0]["threats"]] == ["HIGH"]


def test_sarif_run_category_per_scanner(tmp_path):
    # GitHub replaces earlier analyses of the same category; one category per
    # scanner keeps a Nessus upload from wiping OpenVAS alerts in the same repo.
    sarif = json.loads(get_exporter("sarif")(RECORDS, OpenVASRecord, tmp_path)
                       .read_text(encoding="utf-8"))
    assert sarif["runs"][0]["automationDetails"] == {"id": "mulitaminer/openvas/"}
