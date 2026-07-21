"""Prioritization: signals, decision tree and queue building. Offline."""
import gzip
import json

import pytest

from mulitaminer.models import Instance, OpenVASRecord, TenableRecord
from mulitaminer.prioritization import (
    build_queue,
    exploitation,
    exposure,
    extract_cve_ids,
    prioritize_run,
    severity_band,
)


def _rec(name="V", cvss=7.5, host="1.2.3.4", refs=()):
    return OpenVASRecord(name=name, severity="HIGH", cvss=cvss, host=host,
                         references=list(refs))


def test_cve_extraction_from_references_and_plugin_details():
    rec = _rec(refs=["cve: CVE-2021-44228", "url: https://x"])
    assert extract_cve_ids(rec) == ["CVE-2021-44228"]
    tn = TenableRecord(name="T", severity="HIGH", cvss=[],
                       plugin_details={"family": "See CVE-2020-1938"})
    assert extract_cve_ids(tn) == ["CVE-2020-1938"]


def test_exposure_heuristics():
    assert exposure(_rec(host="10.0.0.5")) == "internal"
    assert exposure(_rec(host="127.0.0.1")) == "internal"
    assert exposure(_rec(host="srv01")) == "internal"
    assert exposure(_rec(host="app.corp")) == "internal"
    assert exposure(_rec(host="example.com")) == "exposed"
    assert exposure(_rec(host=None)) == "exposed"
    tn = TenableRecord(name="T", severity="HIGH", cvss=[],
                       instances=[Instance(instance="https://shop.example.com/x")])
    assert exposure(tn) == "exposed"


def test_exploitation_levels():
    kev, epss = {"CVE-1"}, {"CVE-2": 0.5, "CVE-3": 0.01}
    assert exploitation(["CVE-1"], kev, epss) == "active"
    assert exploitation(["CVE-2"], kev, epss) == "likely"
    assert exploitation(["CVE-3"], kev, epss) == "none"
    assert exploitation([], kev, epss) == "unknown"


def test_severity_band_prefers_numeric_cvss():
    assert severity_band(_rec(cvss=9.8)) == "high"
    assert severity_band(_rec(cvss=5.0)) == "medium"
    assert severity_band(_rec(cvss=None)) == "high"  # falls back to the HIGH label


def test_queue_orders_by_category():
    kev, epss = {"CVE-2020-0001"}, {"CVE-2020-0002": 0.9}
    records = [
        _rec(name="tracked", cvss=2.0, refs=["CVE-2020-0003"]),   # none/exposed/low -> Track
        _rec(name="likely", cvss=5.0, refs=["CVE-2020-0002"]),    # likely/exposed/medium -> Attend
        _rec(name="kev", cvss=9.0, refs=["CVE-2020-0001"]),       # active/exposed/high -> Act
    ]
    rows = build_queue(records, kev, epss, snapshot_date="2026-07-21")
    assert [r["name"] for r in rows] == ["kev", "likely", "tracked"]
    assert [r["category"] for r in rows] == ["Act", "Attend", "Track"]
    assert rows[0]["kev"] is True and rows[0]["rank"] == 1
    assert "active exploitation (KEV)" in rows[0]["justification"]
    assert all(r["snapshot_date"] == "2026-07-21" for r in rows)


def test_within_category_orders_by_epss():
    kev, epss = set(), {"CVE-2020-0002": 0.9, "CVE-2020-0003": 0.5}
    records = [
        _rec(name="lower", refs=["CVE-2020-0003"]),
        _rec(name="higher", refs=["CVE-2020-0002"]),
    ]
    rows = build_queue(records, kev, epss)
    assert [r["name"] for r in rows] == ["higher", "lower"]


def test_no_cve_is_unknown_not_safe():
    rows = build_queue([_rec(name="xss", refs=())], set(), {})
    assert rows[0]["exploitation"] == "unknown"
    assert rows[0]["category"] == "Act"  # exposed default + high severity


def test_prioritize_run_end_to_end(tmp_path):
    feeds = tmp_path / "feeds"
    feeds.mkdir()
    (feeds / "kev.json").write_text(
        json.dumps({"vulnerabilities": [{"cveID": "CVE-2021-44228"}]}), encoding="utf-8")
    epss_csv = "#model_version:v2025,score_date:2026-07-21T00:00:00Z\ncve,epss,percentile\nCVE-2021-44228,0.97,0.99\n"
    with gzip.open(feeds / "epss.csv.gz", "wt", encoding="utf-8") as fh:
        fh.write(epss_csv)
    (feeds / "meta.json").write_text(
        json.dumps({"synced_at": "2026-07-21T00:00:00+00:00",
                    "epss_score_date": "2026-07-21T00:00:00"}), encoding="utf-8")

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    records = [{"Name": "Log4Shell", "severity": "HIGH", "cvss": 10.0,
                "source": "OPENVAS", "host": "5.5.5.5",
                "references": ["cve: CVE-2021-44228"]}]
    (run_dir / "results.json").write_text(json.dumps(records), encoding="utf-8")

    paths = prioritize_run(run_dir, feeds_dir=feeds)
    assert paths["csv"].exists() and paths["xlsx"].exists()
    content = paths["csv"].read_text(encoding="utf-8-sig")
    assert "Log4Shell" in content and "Act" in content


def test_prioritize_without_feeds_raises(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "results.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="sync-feeds"):
        prioritize_run(run_dir, feeds_dir=tmp_path / "nofeeds")
