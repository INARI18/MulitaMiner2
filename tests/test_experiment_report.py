"""HTML report builds from a fabricated experiment tree; pure SVG, self-contained."""
import json
from pathlib import Path

from mulitaminer.experiment_report import _aggregate, build_report


def _fabricate(root: Path) -> None:
    """Two models x one scanner x two runs, with per-run evaluation.json."""
    runs = []
    coverage = {"deepseek": (1.0, 1.0), "nuextract": (0.82, 0.97)}
    field_mean = {"deepseek": 0.96, "nuextract": 0.74}
    for model in ("deepseek", "nuextract"):
        rec, prec = coverage[model]
        for n in (1, 2):
            rd = root / "openvas" / model / f"run_{n}" / "Report"
            rd.mkdir(parents=True)
            (rd / "results.json").write_text("[]", encoding="utf-8")
            (rd / "run.json").write_text("{}", encoding="utf-8")
            (rd / "evaluation.json").write_text(json.dumps({
                "fields": {
                    "description": {
                        "token_f1": {"measured_mean": field_mean[model] + 0.01 * n,
                                     "mean": 0.9, "n_measured": 30,
                                     "fill_rate_baseline": 1.0, "fill_rate_extraction": 0.9},
                        "nli": {"measured_mean": 0.95, "mean": 0.95, "n_measured": 30,
                                "fill_rate_baseline": 1.0, "fill_rate_extraction": 0.9}},
                    "severity": {"exact": {"measured_mean": 0.97, "mean": 0.97, "n_measured": 30,
                                           "fill_rate_baseline": 1.0, "fill_rate_extraction": 1.0}},
                    "references": {"set_f1": {"measured_mean": 0.8, "mean": 0.9, "n_measured": 20,
                                              "fill_rate_baseline": 0.9, "fill_rate_extraction": 0.6}},
                },
                "pairs": [
                    {"scores": {"description": {"token_f1": {"score": field_mean[model], "vacuous": False}}}},
                    {"scores": {"description": {"token_f1": {"score": 0.65, "vacuous": False}}}},
                ],
            }), encoding="utf-8")
            runs.append({
                "scanner": "openvas", "model": model, "run": n, "report": "Report.pdf",
                "run_dir": str(rd), "status": "ok",
                "duration_s": 300.0 + 10 * n, "cost_usd": 0.015,
                "coverage": {"recall": rec, "precision": prec, "matched": 34,
                             "baseline_count": 34, "false_negatives": [],
                             "false_positives": []},
            })
    manifest = {
        "config": {"reports": ["Report.pdf"], "models": ["deepseek", "nuextract"],
                   "runs": 2, "scanner": None, "metrics": "all"},
        "complete": True,
        "totals": {"planned": 4, "done": 4, "failed": 0, "skipped_reports": 0,
                   "active_seconds": 1220.0, "cost_usd": 0.06},
        "runs": runs, "skipped": [],
    }
    (root / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_report_builds_and_is_self_contained(tmp_path):
    _fabricate(tmp_path)
    out = build_report(tmp_path)
    assert out == tmp_path / "report.html"
    doc = out.read_text(encoding="utf-8")

    # Inline-SVG dashboard: embedded data + the English sections + rendered marks.
    assert "MulitaMiner" in doc and "const DATA=" in doc and "<svg" in doc
    for heading in ("Coverage", "Consistency", "Field quality", "Omission", "Distribution"):
        assert heading in doc
    assert "deepseek" in doc and "nuextract" in doc

    # Self-contained: no external resource loads and no chart library.
    for bad in ("<script src", "<link", "@import", "cdnjs", "googleapis", "chart.js"):
        assert bad not in doc

    # A scored metric beyond the common ones (nli) is carried through, not dropped.
    assert "nli" in doc


def test_metric_families_track_the_scorer_registry():
    from mulitaminer.evaluation.scorers import SCORERS
    from mulitaminer.experiment_report import _DET, _TEXT

    assert set(_TEXT) == {n for n, s in SCORERS.items() if s.kind == "text"}
    assert "nli" in _TEXT
    assert set(_DET) == {n for n, s in SCORERS.items() if s.kind == "structural"} | {"structural"}


def test_report_handles_missing_coverage(tmp_path):
    # A run with no evaluation (no baseline) still produces a valid report.
    rd = tmp_path / "tenable" / "deepseek" / "run_1" / "Rep"
    rd.mkdir(parents=True)
    (rd / "results.json").write_text("[]", encoding="utf-8")
    (rd / "run.json").write_text("{}", encoding="utf-8")
    (tmp_path / "experiment.json").write_text(json.dumps({
        "config": {"reports": ["Rep.pdf"], "models": ["deepseek"], "runs": 1,
                   "scanner": "tenable", "metrics": "all"},
        "complete": True,
        "totals": {"planned": 1, "done": 1, "failed": 0, "skipped_reports": 0,
                   "active_seconds": 200.0, "cost_usd": 0.01},
        "runs": [{"scanner": "tenable", "model": "deepseek", "run": 1,
                  "report": "Rep.pdf", "run_dir": str(rd), "status": "ok",
                  "duration_s": 200.0, "cost_usd": 0.01}],
        "skipped": [],
    }), encoding="utf-8")
    out = build_report(tmp_path)
    assert out.is_file() and "MulitaMiner" in out.read_text(encoding="utf-8")


def test_drilldown_detail_folds_runs(tmp_path):
    # Two runs of one model; one baseline finding is missed in both, one
    # invention appears in one. Pairs are keyed by baseline_index, so the same
    # finding across runs folds into a single row.
    runs = []
    for n in (1, 2):
        rd = tmp_path / "openvas" / "m" / f"run_{n}"
        rd.mkdir(parents=True)
        (rd / "results.json").write_text("[]", encoding="utf-8")
        (rd / "evaluation.json").write_text(json.dumps({
            "meta": {"threshold": 0.7},
            "fields": {},
            "pairs": [
                {"baseline_index": 0, "name": "SQL Injection", "scores": {
                    "description": {"token_f1": {"score": 0.6 if n == 1 else 0.8,
                                                 "vacuous": False}},
                    "impact": {"token_f1": {"score": 0.0, "vacuous": True}}}},
            ],
        }), encoding="utf-8")
        runs.append({
            "scanner": "openvas", "model": "m", "run": n, "report": "R.pdf",
            "run_dir": str(rd), "status": "ok", "duration_s": 10.0, "cost_usd": 0.0,
            "coverage": {"recall": 0.5, "precision": 0.5, "baseline_count": 2,
                         "extraction_count": 2 if n == 1 else 1, "matched": 1,
                         "false_negatives": ["XSS"],
                         "false_positives": ["Ghost", "Ghost"] if n == 1 else [],
                         "false_positive_detail": [
                             {"name": "Ghost", "category": "invention",
                              "best_baseline": "XSS", "best_similarity": 0.4}
                         ] * 2 if n == 1 else []},
        })
    (tmp_path / "experiment.json").write_text(json.dumps({
        "config": {"reports": ["R.pdf"], "models": ["m"], "runs": 2,
                   "scanner": "openvas", "metrics": "all"},
        "complete": True,
        "totals": {"planned": 2, "done": 2, "failed": 0, "skipped_reports": 0,
                   "active_seconds": 20.0, "cost_usd": 0.0},
        "runs": runs, "skipped": [],
    }), encoding="utf-8")

    data = _aggregate(tmp_path)
    cell = data["detail"]["R|m"]
    assert data["threshold"] == 0.7
    assert cell["runs"] == 2 and cell["base"] == 2.0 and cell["extr"] == 1.5
    # [name, runs hit, total hits]: XSS is missed once in each run, and run 1
    # reports Ghost twice, so its hits outnumber the runs it appeared in.
    assert cell["fn"] == [["XSS", 2, 2]]
    assert cell["fp"] == [["Ghost", "invention", "XSS", 0.4, 1, 2]]
    # One row per baseline finding, scores averaged; the vacuous field is absent.
    # The trailing count is how many runs matched it: the row set is the union
    # over runs, so a 2-run average must not read as a 5-run one.
    assert cell["pairs"] == [["SQL Injection", {"token_f1": {"description": 0.7}}, 2]]


def test_every_scanner_has_a_column_abbreviation(tmp_path):
    # The report shortens report names to "<scanner>·<name>". A hardcoded chain
    # ending in 'OV' once labelled every unlisted scanner as OpenVAS, so ZAP
    # reports read "OV·ZAP_JBoss7". Keep an explicit entry per shipped scanner.
    from mulitaminer.experiment_report import _JS
    from mulitaminer.scanner_engine import all_scanners

    abbr = _JS.split("const SCAN_ABBR={", 1)[1].split("};", 1)[0]
    missing = [name for name in all_scanners()
               if f"{name}:" not in abbr and f"'{name}':" not in abbr]
    assert not missing, f"no column abbreviation for {missing}"
