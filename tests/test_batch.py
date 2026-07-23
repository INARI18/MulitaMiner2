"""Directory extraction: the folder-name scanner convention and batch behavior."""
import json
import shutil
from pathlib import Path

import pytest

from mulitaminer.llm import FatalLLMError
from mulitaminer.pipeline import RunConfig, run_directory

OPENVAS_PDF = Path("resources/openvas/OpenVAS_JuiceShop.pdf")
TENABLE_PDF = Path("resources/tenable/TenableWAS_bWAPP.pdf")


class EchoClient:
    """Answers every chunk correctly from the block IDs it sees in the prompt.
    Emits only the always-present fields, so it validates for any scanner."""

    class _Profile:
        max_output_tokens = 100_000
        encoding = "cl100k_base"

    profile = _Profile()

    def extract(self, system_prompt, user_content, response_model):
        import re

        ids = [int(m) for m in re.findall(r"### BLOCK (\d+)", user_content)]
        items = [{"block_id": i, "Name": f"Vuln {i}", "severity": "HIGH"} for i in ids]
        parsed = response_model.model_validate({"items": items})
        return parsed, {"prompt_tokens": 10, "completion_tokens": 5,
                        "cost_usd": 0.001, "raw": json.dumps({"items": items})}


class FatalClient(EchoClient):
    def extract(self, *args, **kwargs):
        raise FatalLLMError("no API key")


@pytest.fixture
def scanner_tree(tmp_path):
    """The resources/<scanner>/report.pdf layout the folder convention expects."""
    d = tmp_path / "reports"
    (d / "openvas").mkdir(parents=True)
    (d / "tenable").mkdir(parents=True)
    shutil.copy(OPENVAS_PDF, d / "openvas" / OPENVAS_PDF.name)
    shutil.copy(TENABLE_PDF, d / "tenable" / TENABLE_PDF.name)
    (d / "openvas" / "junk.pdf").write_bytes(b"this is not a pdf at all")
    return d


def test_batch_folder_convention_and_survives_junk(scanner_tree, tmp_path):
    config = RunConfig(input_path=scanner_tree, scanner=None, model="deepseek",
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


def test_batch_unknown_folder_fails_clearly(tmp_path):
    holder = tmp_path / "reports" / "notascanner"
    holder.mkdir(parents=True)
    shutil.copy(OPENVAS_PDF, holder / OPENVAS_PDF.name)
    config = RunConfig(input_path=tmp_path / "reports", scanner=None,
                       model="deepseek", output_dir=tmp_path / "out")
    summaries = run_directory(config, client=EchoClient())
    assert summaries[0]["status"] == "failed"
    assert "not a known scanner" in summaries[0]["detail"]


def test_batch_scanner_override_forces_profile(scanner_tree, tmp_path):
    config = RunConfig(input_path=scanner_tree, scanner="openvas", model="deepseek",
                       output_dir=tmp_path / "out")
    summaries = run_directory(config, client=EchoClient())
    by_file = {s["file"]: s for s in summaries}
    assert by_file[OPENVAS_PDF.name]["status"] == "ok"
    # Forcing openvas on a tenable report finds 0 blocks -> failed, not garbage.
    assert by_file[TENABLE_PDF.name]["status"] == "failed"
    assert "No finding blocks" in by_file[TENABLE_PDF.name]["detail"]


def test_batch_fatal_error_aborts(scanner_tree, tmp_path):
    config = RunConfig(input_path=scanner_tree, scanner="openvas", model="deepseek",
                       output_dir=tmp_path / "out")
    with pytest.raises(FatalLLMError):
        run_directory(config, client=FatalClient())


def test_batch_empty_dir_raises(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    config = RunConfig(input_path=empty, scanner=None, model="deepseek")
    with pytest.raises(ValueError, match="No PDF"):
        run_directory(config, client=EchoClient())
