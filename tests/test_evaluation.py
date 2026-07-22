"""Evaluation subsystem: scorers, field mapping, alignment, orchestration."""
import pytest

from mulitaminer.evaluation.align import (
    align, classify_spurious, composite_key, key_parts_for_source,
)
from mulitaminer.evaluation.fields import FieldPlan, field_plans
from mulitaminer.evaluation.scorers import SCORERS, pair_score, render_text, text_scorers
from mulitaminer.models import Instance, OpenVASRecord, PluginDetails, TenableRecord


# --- scorers -----------------------------------------------------------------


def test_scorers_exact_numeric_and_text():
    exact = SCORERS["exact"].fn
    assert exact(8019, "8019.0") == 1.0
    assert exact("TCP", "tcp") == 1.0
    assert exact(7.5, 7.6) == 0.0
    assert exact("high", "low") == 0.0


def test_scorers_set_f1_known_value():
    set_f1 = SCORERS["set_f1"].fn
    # 1 common item, |a|=2, |b|=3 -> P=0.5, R=1/3, F1=0.4
    a = ["CVE-2021-1234", "CVE-2020-0001"]
    b = ["cve-2021-1234", "CVE-2019-9999", "CVE-2018-8888"]
    assert set_f1(a, b) == pytest.approx(0.4)
    assert set_f1(a, a) == 1.0
    assert set_f1(a, ["CVE-0000-0000"]) == 0.0


def test_scorers_token_f1_known_value():
    token_f1 = SCORERS["token_f1"].fn
    # tokens a: [the, server, is, vulnerable], b: [the, server, responded]
    # common=2, P=2/4, R=2/3 -> F1 = 4/7
    assert token_f1("The server is vulnerable", "the server responded") == pytest.approx(4 / 7)
    assert token_f1("same text", "same text") == 1.0


def test_scorers_rouge_l_known_value():
    rouge_l = SCORERS["rouge_l"].fn
    # a: [a, b, c, d], b: [a, c, d, e] -> LCS [a, c, d] = 3, P=R=3/4, F1=0.75
    assert rouge_l("a b c d", "a c d e") == pytest.approx(0.75)
    # Order matters for LCS (unlike token_f1): reversed sequence scores lower.
    assert rouge_l("a b c", "c b a") == pytest.approx(1 / 3)


def test_scorers_pair_rules_vacuous_and_presence():
    token_f1 = SCORERS["token_f1"]
    assert pair_score(token_f1, [], "") == (1.0, True)
    assert pair_score(token_f1, None, []) == (1.0, True)
    assert pair_score(token_f1, "something", "") == (0.0, False)
    assert pair_score(token_f1, [], "something") == (0.0, False)
    score, vacuous = pair_score(token_f1, "same text", "same text")
    assert score == 1.0 and vacuous is False


def test_scorers_render_text_joins_and_strips():
    assert render_text(["a", None, "b"]) == "a\nb"
    assert render_text({"family": "Web", "empty": None}) == "family: Web"
    assert render_text(None) == ""
    assert render_text("  x  ") == "x"


def test_scorers_bertscore_unavailable_is_safe():
    bert = SCORERS["bertscore"]
    if bert.available:
        pytest.skip("bert-score installed in this environment")
    assert "uv sync --group eval" in bert.hint
    with pytest.raises(RuntimeError, match="eval"):
        bert.fn("a", "b")


def test_scorers_kinds_split():
    assert {s.name for s in text_scorers()} == {"token_f1", "rouge_l", "bertscore", "nli"}
    assert SCORERS["exact"].kind == "structural"
    assert SCORERS["set_f1"].kind == "structural"
    assert SCORERS["set_f1_ids"].kind == "structural"


# --- fields ------------------------------------------------------------------


def _plan(plans: list[FieldPlan], name: str) -> FieldPlan:
    return next(p for p in plans if p.name == name)


def test_fields_openvas_inference_matches_spec_table():
    plans = field_plans(OpenVASRecord)
    by_name = {p.name: p.metric for p in plans}
    assert by_name["severity"] == "exact"       # Literal
    assert by_name["protocol"] == "exact"       # Literal | None
    assert by_name["cvss"] == "exact"           # float | int | None
    assert by_name["plugin"] == "exact"         # int | None
    assert by_name["port"] == "exact"           # int | str | None
    assert by_name["name"] == "text"            # str
    assert by_name["description"] == "text"     # list[str]
    assert by_name["plugin_details"] == "structural"  # dict
    assert by_name["instances"] == "text"       # bare list, safe default
    # Pipeline-stamped fields are never evaluated.
    assert "host" not in by_name and "source" not in by_name


def test_fields_tenable_nested_models_are_structural():
    plans = field_plans(TenableRecord)
    pd_plan = _plan(plans, "plugin_details")
    assert pd_plan.metric == "structural" and pd_plan.sub_model is PluginDetails
    inst = _plan(plans, "instances")
    assert inst.metric == "structural" and inst.sub_model is Instance and inst.is_list
    assert _plan(plans, "cvss").metric == "text"  # list[str]; JSON override makes it set_f1


def test_fields_new_field_gets_default_by_type():
    class ExtendedRecord(OpenVASRecord):
        cwe_ids: list[str] = []
        exploitability: float | None = None

    by_name = {p.name: p.metric for p in field_plans(ExtendedRecord)}
    assert by_name["cwe_ids"] == "text"
    assert by_name["exploitability"] == "exact"


def test_fields_overrides_beat_inference_and_skip_removes():
    plans = field_plans(
        OpenVASRecord, overrides={"references": "set_f1", "insight": "skip"}
    )
    by_name = {p.name: p.metric for p in plans}
    assert by_name["references"] == "set_f1"
    assert "insight" not in by_name


def test_fields_unknown_override_rejected():
    with pytest.raises(ValueError, match="valid values"):
        field_plans(OpenVASRecord, overrides={"references": "bogus_metric"})


def test_fields_builtin_configs_carry_overrides():
    from mulitaminer.scanner_engine import get_scanner

    assert dict(get_scanner("openvas").field_metric_overrides) == {"references": "set_f1"}
    assert dict(get_scanner("tenable").field_metric_overrides) == {
        "references": "set_f1",
        "cvss": "set_f1",
    }


# --- align -------------------------------------------------------------------

OV_PARTS = key_parts_for_source("OPENVAS")


def test_align_known_pairs_all_found():
    ext = [{"Name": "SQL Injection", "port": 80, "protocol": "tcp"},
           {"Name": "Weak Cipher", "port": 443, "protocol": "tcp"}]
    base = [{"Name": "Weak Cipher", "port": 443, "protocol": "tcp"},
            {"Name": "SQL Injection", "port": 80, "protocol": "tcp"}]
    res = align(ext, base, OV_PARTS)
    assert sorted(res.pairs) == [(0, 1), (1, 0)]
    assert not res.unmatched_extraction and not res.unmatched_baseline


def test_align_paraphrased_name_threshold():
    base = [{"Name": "Cleartext Transmission of Sensitive Information via HTTP"}]
    close = [{"Name": "Cleartext Transmission of Sensitive Info via HTTP"}]
    far = [{"Name": "Completely Different Finding"}]
    assert align(close, base).pairs == [(0, 0)]
    res = align(far, base)
    assert res.pairs == [] and res.unmatched_extraction == [0]
    assert res.unmatched_baseline == [0]


def test_align_duplicate_names_resolved_by_composite():
    ext = [{"Name": "FTP Unencrypted", "port": 21, "protocol": "tcp"},
           {"Name": "FTP Unencrypted", "port": 2121, "protocol": "tcp"}]
    base = [{"Name": "FTP Unencrypted", "port": 2121, "protocol": "tcp"},
            {"Name": "FTP Unencrypted", "port": 21, "protocol": "tcp"}]
    res = align(ext, base, OV_PARTS)
    assert sorted(res.pairs) == [(0, 1), (1, 0)]


def test_align_surplus_extraction_is_spurious():
    ext = [{"Name": "A thing here"}, {"Name": "Ghost finding xyz"}]
    base = [{"Name": "A thing here"}]
    res = align(ext, base)
    assert res.pairs == [(0, 0)]
    assert res.unmatched_extraction == [1]
    statuses = {d["extraction_index"]: d["status"] for d in res.debug_rows}
    assert statuses[1] == "UNMATCHED"


def test_align_float_port_guard():
    # pandas float64 coercion: 8019.0 must key as "8019", never "80190".
    key = composite_key({"Name": "X", "port": 8019.0, "protocol": "tcp"}, OV_PARTS)
    assert key == "x|8019|tcp"


def test_align_services_no_special_case():
    # 'Services' is keyed like any other name now; the composite key carries the
    # port/protocol that actually distinguishes instances.
    key = composite_key({"Name": "Services", "port": 80, "protocol": "tcp"}, OV_PARTS)
    assert key == "services|80|tcp"


def _cat(ext, base, parts=OV_PARTS):
    res = align(ext, base, parts)
    return {d["extraction_index"]: d["category"]
            for d in classify_spurious(ext, base, res, parts)}


def test_classify_spurious_invention():
    ext = [{"Name": "A thing"}, {"Name": "Ghost finding xyz"}]
    base = [{"Name": "A thing"}]
    assert _cat(ext, base, ()) == {1: "invention"}


def test_classify_spurious_name_mismatch():
    # Same finding, extracted name polluted by segmentation noise: its free
    # baseline twin scores below threshold.
    ext = [{"Name": "phpinfo output reporting 2 results per host 7"}]
    base = [{"Name": "phpinfo output reporting"}]
    assert _cat(ext, base, ()) == {0: "name_mismatch"}


def test_classify_spurious_surplus_distinct_instance():
    # Two report instances on different ports, one baseline row: surplus, but a
    # distinct instance (different key), not a true duplicate.
    ext = [{"Name": "Weak Sig", "port": 25, "protocol": "tcp"},
           {"Name": "Weak Sig", "port": 5432, "protocol": "tcp"}]
    base = [{"Name": "Weak Sig", "port": 5432, "protocol": "tcp"}]
    res = align(ext, base, OV_PARTS)
    d = {s["extraction_index"]: s for s in classify_spurious(ext, base, res, OV_PARTS)}
    assert d[0]["category"] == "surplus" and d[0]["same_key"] is False


def test_classify_spurious_surplus_true_duplicate():
    # Two extractions with the SAME key: surplus flagged as a true duplicate.
    ext = [{"Name": "X", "port": 80, "protocol": "tcp"},
           {"Name": "X", "port": 80, "protocol": "tcp"}]
    base = [{"Name": "X", "port": 80, "protocol": "tcp"}]
    res = align(ext, base, OV_PARTS)
    surplus = [s for s in classify_spurious(ext, base, res, OV_PARTS)
               if s["category"] == "surplus"]
    assert len(surplus) == 1 and surplus[0]["same_key"] is True


def test_align_empty_sides():
    res = align([], [{"Name": "A"}])
    assert res.unmatched_baseline == [0] and not res.pairs
    res = align([{"Name": "A"}], [])
    assert res.unmatched_extraction == [0] and not res.pairs


# --- orchestration -----------------------------------------------------------


@pytest.fixture
def mini_run(tmp_path):
    """A fabricated run dir + baseline XLSX (OpenVAS, 3 findings)."""
    import pandas as pd

    records = [
        OpenVASRecord(
            name="SQL Injection", severity="HIGH", cvss=8.1, port=80, protocol="tcp",
            description=["Injectable parameter found."],
            references=["CVE-2021-1111", "CVE-2020-2222"],
        ),
        OpenVASRecord(
            name="Weak Cipher Suites", severity="MEDIUM", cvss=5.3, port=443, protocol="tcp",
            description=["Server accepts weak TLS ciphers."],
        ),
        OpenVASRecord(  # spurious: not in the baseline
            name="Ghost Finding", severity="LOW", cvss=2.0, port=21, protocol="tcp",
        ),
    ]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(
        __import__("json").dumps(
            [r.model_dump(mode="json", by_alias=True) for r in records]
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "Report.pdf"
    (run_dir / "run.json").write_text(
        __import__("json").dumps({"config": {"input": str(pdf_path)}}), encoding="utf-8"
    )
    baseline = pd.DataFrame(
        [
            {"Name": "SQL Injection", "severity": "HIGH", "cvss": 8.1, "port": 80,
             "protocol": "tcp", "description": "Injectable parameter found.",
             "references": "['CVE-2021-1111', 'CVE-2020-2222']",
             "extra_gt_column": "not in schema"},
            {"Name": "Weak Cipher Suites", "severity": "MEDIUM", "cvss": 5.3, "port": 443,
             "protocol": "tcp", "description": "Server accepts weak TLS ciphers.",
             "references": None, "extra_gt_column": None},
            {"Name": "Missed Finding", "severity": "LOW", "cvss": 1.0, "port": 22,
             "protocol": "tcp", "description": "Never extracted.",
             "references": None, "extra_gt_column": None},
        ]
    )
    baseline.to_excel(tmp_path / "Report.xlsx", index=False)
    return run_dir


def test_orchestration_end_to_end(mini_run):
    from mulitaminer.evaluation import evaluate_run

    res = evaluate_run(mini_run)
    assert res.coverage["matched"] == 2
    assert res.coverage["missed"] == ["Missed Finding"]
    assert res.coverage["spurious"] == ["Ghost Finding"]
    assert res.coverage["recall"] == pytest.approx(2 / 3, abs=1e-4)
    assert res.coverage["precision"] == pytest.approx(2 / 3, abs=1e-4)
    # exact fields perfect on the matched pairs
    assert res.fields["severity"]["exact"]["mean"] == 1.0
    assert res.fields["cvss"]["exact"]["mean"] == 1.0
    # references: override set_f1; pair 1 exact sets, pair 2 vacuous (both empty)
    ref = res.fields["references"]["set_f1"]
    assert ref["mean"] == 1.0 and ref["vacuous_n"] == 1
    # text metrics present for description
    assert res.fields["description"]["token_f1"]["mean"] == 1.0
    # GT column outside the schema is reported, not scored
    assert res.unevaluated_baseline_columns == ["extra_gt_column"]
    assert res.meta["source"] == "OPENVAS"


def test_orchestration_bare_results_needs_baseline(mini_run, tmp_path):
    from mulitaminer.evaluation import evaluate_run

    bare = mini_run / "results.json"
    with pytest.raises(ValueError, match="baseline"):
        evaluate_run(bare)
    res = evaluate_run(bare, baseline=tmp_path / "Report.xlsx")
    assert res.coverage["matched"] == 2


def test_orchestration_metrics_selection(mini_run):
    from mulitaminer.evaluation import evaluate_run
    from mulitaminer.evaluation.runner import resolve_metrics

    res = evaluate_run(mini_run, metrics="token_f1")
    assert "rouge_l" not in res.fields["description"]
    assert "token_f1" in res.fields["description"]
    # structural scorers unaffected by the text filter
    assert "exact" in res.fields["severity"]
    with pytest.raises(ValueError, match="valid"):
        resolve_metrics("nope")
    bert = SCORERS["bertscore"]
    if not bert.available:
        with pytest.raises(RuntimeError, match="eval"):
            resolve_metrics("bert")


def test_orchestration_instances_generated_provenance(tmp_path):
    import pandas as pd

    from mulitaminer.evaluation.runner import load_baseline

    base = pd.DataFrame([{"Name": "A", "instances": None}])
    base.to_excel(tmp_path / "T.xlsx", index=False)
    gen = pd.DataFrame(
        [{"Name": "A", "instances": "[{'instance': 'http://x', 'proof': 'p'}]"}]
    )
    gen.to_excel(tmp_path / "T_instances_generated.xlsx", index=False)

    rows, provenance = load_baseline(tmp_path / "T.xlsx")
    assert provenance["reannotated_from"].endswith("T_instances_generated.xlsx")
    assert provenance["reannotated_columns"] == ["instances"]
    assert rows[0]["instances"] == [{"instance": "http://x", "proof": "p"}]


def test_orchestration_structural_instances_scoring():
    from mulitaminer.evaluation.fields import field_plans
    from mulitaminer.evaluation.runner import _structural_score

    plan = next(p for p in field_plans(TenableRecord) if p.name == "instances")
    ext = [{"instance": "http://a/1", "proof": "same proof"},
           {"instance": "http://a/2", "proof": "other"}]
    base_same = [{"instance": "http://a/1", "proof": "same proof"},
                 {"instance": "http://a/2", "proof": "other"}]
    score, vacuous = _structural_score(plan, ext, base_same)
    assert score == pytest.approx(1.0) and not vacuous
    # a missing base item halves the normalizer's numerator
    score_partial, _ = _structural_score(plan, ext, base_same[:1])
    assert 0.0 < score_partial < 1.0
    assert _structural_score(plan, [], []) == (1.0, True)
    assert _structural_score(plan, ext, []) == (0.0, False)


# --- report ------------------------------------------------------------------


def test_report_writes_json_and_md(mini_run):
    import json as _json

    from mulitaminer.evaluation import evaluate_run
    from mulitaminer.evaluation.report import summary_table, write_reports

    res = evaluate_run(mini_run)
    paths = write_reports(res, mini_run)
    data = _json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["coverage"]["matched"] == 2
    assert data["meta"]["generated_at"] and data["meta"]["tool_version"]
    assert data["fields"]["severity"]["exact"]["mean"] == 1.0

    md = paths["md"].read_text(encoding="utf-8")
    assert "## Coverage" in md
    assert "Missed Finding" in md and "Ghost Finding" in md
    assert "extra_gt_column" in md  # unevaluated column noted

    table = summary_table(res)
    assert "severity" in table and "exact" in table


# --- CLI ---------------------------------------------------------------------


def test_cli_evaluate_run_dir(mini_run):
    from typer.testing import CliRunner

    from mulitaminer.cli import app

    result = CliRunner().invoke(app, ["evaluate", str(mini_run)])
    assert result.exit_code == 0, result.output
    assert "Coverage: 2/3 matched" in result.output
    assert (mini_run / "evaluation.json").exists()
    assert (mini_run / "evaluation.md").exists()


def test_cli_evaluate_metrics_subset_and_errors(mini_run):
    from typer.testing import CliRunner

    from mulitaminer.cli import app

    runner = CliRunner()
    ok = runner.invoke(app, ["evaluate", str(mini_run), "--metrics", "token_f1"])
    assert ok.exit_code == 0, ok.output

    bad = runner.invoke(app, ["evaluate", str(mini_run), "--metrics", "nope"])
    assert bad.exit_code == 1 and "valid" in bad.output

    bare = runner.invoke(app, ["evaluate", str(mini_run / "results.json")])
    assert bare.exit_code == 1 and "baseline" in bare.output.lower()

    if not SCORERS["bertscore"].available:
        unavailable = runner.invoke(app, ["evaluate", str(mini_run), "--metrics", "bert"])
        assert unavailable.exit_code == 1 and "eval" in unavailable.output


def test_cli_evaluate_list_metrics():
    from typer.testing import CliRunner

    from mulitaminer.cli import app

    result = CliRunner().invoke(app, ["evaluate", "--list-metrics"])
    assert result.exit_code == 0
    for name in ("exact", "set_f1", "token_f1", "rouge_l", "bertscore"):
        assert name in result.output


def test_orchestration_severity_map_applied_to_baseline(tmp_path):
    import json as _json

    import pandas as pd

    from mulitaminer.evaluation import evaluate_run

    records = [
        TenableRecord(name="Some Info Finding", severity="LOG", plugin=1234).model_dump(
            mode="json", by_alias=True
        )
    ]
    (tmp_path / "results.json").write_text(_json.dumps(records), encoding="utf-8")
    pd.DataFrame(
        [{"Name": "Some Info Finding", "severity": "INFO", "plugin": 1234}]
    ).to_excel(tmp_path / "base.xlsx", index=False)

    res = evaluate_run(tmp_path / "results.json", baseline=tmp_path / "base.xlsx")
    # INFO->LOG is the scanner's by-design normalization, not a mismatch.
    assert res.fields["severity"]["exact"]["mean"] == 1.0


# --- audit follow-ups: set_f1_ids, measured means, path-aware pairing, nli ---


def test_scorers_set_f1_ids_canonicalizes_format_jitter():
    ids = SCORERS["set_f1_ids"].fn
    # Label prefix jitter: content identical -> 1.0 (strict set_f1 gives 0)
    assert ids(["CVE CVE-2022-22719"], ["CVE-2022-22719"]) == 1.0
    # Granularity jitter: one comma-joined item vs atomic items -> 1.0
    assert ids(["CVE: CVE-2008-5304, CVE-2008-5305"],
               ["CVE-2008-5304", "CVE-2008-5305"]) == 1.0
    assert ids(["BID:32668, 32669"], ["BID:32668", "BID:32669"]) == 1.0
    assert ids(["CWE 125, 20"], ["CWE 125", "CWE 20"]) == 1.0
    # No-id items (WASC names) fall back to exploded normalized text
    assert ids(["WASC Buffer Overflow, Improper Input Handling"],
               ["WASC Buffer Overflow", "WASC Improper Input Handling"]) == 1.0
    # Genuinely different references still mismatch
    assert ids(["CVE-2022-1111"], ["CVE-2022-2222"]) == 0.0


def test_scorers_nli_unavailable_is_safe():
    nli = SCORERS["nli"]
    assert nli.in_all is False  # never runs implicitly via --metrics all
    if nli.available:
        pytest.skip("transformers installed in this environment")
    with pytest.raises(RuntimeError, match="eval"):
        nli.fn("a", "b")


def test_orchestration_measured_mean_excludes_vacuous(mini_run):
    from mulitaminer.evaluation import evaluate_run

    res = evaluate_run(mini_run)
    ref = res.fields["references"]["set_f1"]
    # pair 1 measured (1.0), pair 2 vacuous -> inclusive 1.0, measured n=1
    assert ref["n"] == 2 and ref["vacuous_n"] == 1
    assert ref["n_measured"] == 1 and ref["measured_mean"] == 1.0
    # companion canonical metric present on set_f1 fields
    assert "set_f1_ids" in res.fields["references"]


def test_report_table_shows_na_for_all_vacuous(tmp_path):
    import json as _json

    import pandas as pd

    from mulitaminer.evaluation import evaluate_run
    from mulitaminer.evaluation.report import summary_table

    records = [OpenVASRecord(name="Empty Impact", severity="LOW", cvss=1.0).model_dump(
        mode="json", by_alias=True)]
    (tmp_path / "results.json").write_text(_json.dumps(records), encoding="utf-8")
    pd.DataFrame([{"Name": "Empty Impact", "severity": "LOW", "cvss": 1.0,
                   "impact": None}]).to_excel(tmp_path / "b.xlsx", index=False)
    res = evaluate_run(tmp_path / "results.json", baseline=tmp_path / "b.xlsx")
    table = summary_table(res)
    impact_row = next(line for line in table.splitlines() if line.startswith("impact"))
    assert "n/a" in impact_row


def test_orchestration_instance_pairing_prefers_matching_path():
    from mulitaminer.evaluation.runner import _key_similarity, _structural_score

    host = "https://juice-shop-388277804329.us-west1.run.app"
    # Same host, different endpoints: must NOT clear the 0.7 threshold
    assert _key_similarity(f"{host}/#/login", f"{host}/#/administration") < 0.7
    # Same endpoint, formatting noise (trailing slash, case): high similarity
    assert _key_similarity(f"{host}/#/login/", f"{host.upper()}/#/login") > 0.9

    plan = next(p for p in field_plans(TenableRecord) if p.name == "instances")
    ext = [{"instance": f"{host}/#/login", "proof": "login proof"},
           {"instance": f"{host}/#/administration", "proof": "admin proof"}]
    base = [{"instance": f"{host}/#/administration", "proof": "admin proof"},
            {"instance": f"{host}/#/login", "proof": "login proof"}]
    score, _ = _structural_score(plan, ext, base)
    assert score == pytest.approx(1.0)  # crossed order still pairs correctly
