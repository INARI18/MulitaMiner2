"""Directory extraction: scanner auto-detection and batch behavior."""
import json
import shutil
from pathlib import Path

import pytest

from mulitaminer.llm import FatalLLMError
from mulitaminer.pipeline import RunConfig, run_directory
from mulitaminer.scanner_engine import detect_scanner

OPENVAS_PDF = Path("resources/openvas/OpenVAS_JuiceShop.pdf")
TENABLE_PDF = Path("resources/tenable/TenableWAS_bWAAP.pdf")

OPENVAS_TEXT = "High (CVSS: 9.8)\nNVT: Some Finding\nSummary:\nx\n"
TENABLE_TEXT = "Some Finding\nVULNERABILITY HIGH PLUGIN ID 12345\nDescription:\nx\n"


class EchoClient:
    """Answers every chunk correctly from the block IDs it sees in the prompt."""

    class _Profile:
        max_output_tokens = 100_000
        encoding = "cl100k_base"

    profile = _Profile()

    def extract(self, system_prompt, user_content, response_model):
        import re

        ids = [int(m) for m in re.findall(r"### BLOCK (\d+)", user_content)]
        items = [
            {"block_id": i, "Name": f"Vuln {i}", "severity": "HIGH", "cvss": 7.5}
            for i in ids
        ]
        parsed = response_model.model_validate({"items": items})
        return parsed, {"prompt_tokens": 10, "completion_tokens": 5,
                        "cost_usd": 0.001, "raw": json.dumps({"items": items})}


class FatalClient(EchoClient):
    def extract(self, *args, **kwargs):
        raise FatalLLMError("no API key")


# --- detection ---------------------------------------------------------------


def test_detect_openvas_only():
    name, counts = detect_scanner(OPENVAS_TEXT)
    assert name == "openvas" and counts["tenable"] == 0


def test_detect_tenable_only():
    name, counts = detect_scanner(TENABLE_TEXT)
    assert name == "tenable" and counts["openvas"] == 0


def test_detect_ambiguous_returns_none():
    name, counts = detect_scanner(OPENVAS_TEXT + TENABLE_TEXT)
    assert name is None
    assert counts["openvas"] > 0 and counts["tenable"] > 0


def test_detect_junk_returns_none():
    name, counts = detect_scanner("just some random text, no findings here")
    assert name is None and not any(counts.values())


# --- batch -------------------------------------------------------------------


@pytest.fixture
def mixed_dir(tmp_path):
    d = tmp_path / "reports"
    d.mkdir()
    shutil.copy(OPENVAS_PDF, d / OPENVAS_PDF.name)
    shutil.copy(TENABLE_PDF, d / TENABLE_PDF.name)
    (d / "junk.pdf").write_bytes(b"this is not a pdf at all")
    return d


def test_batch_mixed_dir_autodetects_and_survives_junk(mixed_dir, tmp_path):
    config = RunConfig(input_path=mixed_dir, scanner=None, model="deepseek",
                       output_dir=tmp_path / "out")
    summaries = run_directory(config, client=EchoClient())
    by_file = {s["file"]: s for s in summaries}

    assert by_file[OPENVAS_PDF.name]["status"] == "ok"
    assert by_file[OPENVAS_PDF.name]["scanner"] == "openvas"
    assert by_file[TENABLE_PDF.name]["status"] == "ok"
    assert by_file[TENABLE_PDF.name]["scanner"] == "tenable"
    assert by_file["junk.pdf"]["status"] == "failed"

    # Each extracted file produced a normal run dir with artifacts.
    run_dir = Path(by_file[OPENVAS_PDF.name]["run_dir"])
    assert (run_dir / "results.json").exists() and (run_dir / "run.json").exists()


def test_batch_scanner_override_forces_profile(mixed_dir, tmp_path):
    config = RunConfig(input_path=mixed_dir, scanner="openvas", model="deepseek",
                       output_dir=tmp_path / "out")
    summaries = run_directory(config, client=EchoClient())
    by_file = {s["file"]: s for s in summaries}
    assert by_file[OPENVAS_PDF.name]["status"] == "ok"
    # Forcing openvas on a tenable report finds 0 blocks -> failed, not garbage.
    assert by_file[TENABLE_PDF.name]["status"] == "failed"
    assert "No finding blocks" in by_file[TENABLE_PDF.name]["detail"]


def test_batch_fatal_error_aborts(mixed_dir, tmp_path):
    config = RunConfig(input_path=mixed_dir, scanner=None, model="deepseek",
                       output_dir=tmp_path / "out")
    with pytest.raises(FatalLLMError):
        run_directory(config, client=FatalClient())


def test_batch_empty_dir_raises(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    config = RunConfig(input_path=empty, scanner=None, model="deepseek")
    with pytest.raises(ValueError, match="No PDF"):
        run_directory(config, client=EchoClient())
