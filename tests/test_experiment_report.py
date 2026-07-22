"""HTML report builds from a fabricated experiment tree; pure SVG, self-contained."""
import json
from pathlib import Path

from mulitaminer.experiment_report import build_report


def _fabricate(root: Path) -> None:
    """Two models x one scanner x two runs, with per-run evaluation.json."""
    runs = []
    coverage = {"deepseek": (1.0, 1.0), "ollama": (0.82, 0.97)}
    field_mean = {"deepseek": 0.96, "ollama": 0.74}
    for model in ("deepseek", "ollama"):
        rec, prec = coverage[model]
        for n in (1, 2):
            rd = root / "openvas" / model / f"run_{n}" / "Report"
            rd.mkdir(parents=True)
            (rd / "results.json").write_text("[]", encoding="utf-8")
            (rd / "run.json").write_text("{}", encoding="utf-8")
            (rd / "evaluation.json").write_text(json.dumps({
                "fields": {
                    "description": {"token_f1": {"measured_mean": field_mean[model] + 0.01 * n,
                                                 "mean": 0.9, "n_measured": 30,
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
                             "baseline_count": 34, "missed": [], "spurious": []},
            })
    manifest = {
        "config": {"reports": ["Report.pdf"], "models": ["deepseek", "ollama"],
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
    assert "deepseek" in doc and "ollama" in doc

    # Self-contained: no external resource loads and no chart library.
    for bad in ("<script src", "<link", "@import", "cdnjs", "googleapis", "chart.js"):
        assert bad not in doc


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
