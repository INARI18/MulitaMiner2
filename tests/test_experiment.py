"""Experiment harness: bucketing, checkpoint, duration accounting (no network)."""
import json
from pathlib import Path

import pytest

from mulitaminer.experiment import ExperimentConfig, bucket_key, run_experiment

OPENVAS_PDF = Path("resources/openvas/OpenVAS_JuiceShop.pdf")


class EchoClient:
    class _Profile:
        max_output_tokens = 100_000
        encoding = "cl100k_base"

    profile = _Profile()

    def extract(self, system_prompt, user_content, response_model):
        import re

        ids = [int(m) for m in re.findall(r"### BLOCK (\d+)", user_content)]
        items = [{"block_id": i, "Name": f"Vuln {i}", "severity": "HIGH", "cvss": 7.5}
                 for i in ids]
        parsed = response_model.model_validate({"items": items})
        return parsed, {"prompt_tokens": 10, "completion_tokens": 5,
                        "cost_usd": 0.001, "raw": json.dumps({"items": items})}


@pytest.fixture(autouse=True)
def _inject_fake_client(monkeypatch):
    """Every model's client is the offline echo client."""
    monkeypatch.setattr("mulitaminer.experiment.LLMClient",
                        lambda *a, **k: EchoClient())


def test_bucket_key_separates_local_and_api():
    # deepseek keyed by its API env; ollama (local) keyed by its base_url.
    assert bucket_key("deepseek") == "DEEPSEEK_API_KEY"
    assert bucket_key("ollama").startswith("http")
    assert bucket_key("deepseek") != bucket_key("ollama")


def test_experiment_layout_and_manifest(tmp_path):
    config = ExperimentConfig(
        reports=[OPENVAS_PDF], models=["deepseek"], runs=2,
        scanner="openvas", metrics="token_f1", output_dir=tmp_path / "exp",
    )
    result = run_experiment(config)
    # Layout: <out>/<scanner>/<model>/run_<n>/<stem>/
    for n in (1, 2):
        d = tmp_path / "exp" / "openvas" / "deepseek" / f"run_{n}" / OPENVAS_PDF.stem
        assert (d / "results.json").is_file() and (d / "run.json").is_file()
        assert (d / "evaluation.json").is_file()  # baseline XLSX exists -> evaluated

    manifest = json.loads((tmp_path / "exp" / "experiment.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True
    assert manifest["totals"]["planned"] == 2 and manifest["totals"]["done"] == 2
    assert manifest["totals"]["active_seconds"] > 0
    # Coverage computed against the real baseline (fake echo names won't match,
    # so only the denominators are meaningful here).
    assert all(r["coverage"]["baseline_count"] == 34 for r in manifest["runs"])
    assert all("matched" in r["coverage"] for r in manifest["runs"])


def test_experiment_checkpoint_skips_completed(tmp_path):
    config = ExperimentConfig(
        reports=[OPENVAS_PDF], models=["deepseek"], runs=1,
        scanner="openvas", metrics="token_f1", output_dir=tmp_path / "exp",
    )
    run_experiment(config)
    # Second invocation: the completed run dir is reused, not re-extracted.
    result = run_experiment(config)
    assert all(r["status"] == "cached" for r in result["records"])


def test_experiment_parallel_buckets_and_active_time(tmp_path):
    config = ExperimentConfig(
        reports=[OPENVAS_PDF], models=["deepseek", "ollama"], runs=1,
        scanner="openvas", metrics="token_f1", output_dir=tmp_path / "exp",
    )
    result = run_experiment(config)
    models_done = {r["model"] for r in result["records"] if r["status"] == "ok"}
    assert models_done == {"deepseek", "ollama"}
    # active_seconds is the sum of run durations, not wall clock.
    manifest = json.loads((tmp_path / "exp" / "experiment.json").read_text(encoding="utf-8"))
    per_run = [r["duration_s"] for r in manifest["runs"] if r["status"] == "ok"]
    assert manifest["totals"]["active_seconds"] == pytest.approx(round(sum(per_run), 2))
