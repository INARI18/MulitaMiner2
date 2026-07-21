"""CLI smoke tests (offline commands only)."""
from typer.testing import CliRunner

from mulitaminer.cli import app

runner = CliRunner()


def test_segment_command_counts_blocks_offline():
    result = runner.invoke(
        app, ["segment", "resources/openvas/OpenVAS_JuiceShop.pdf",
              "--scanner", "openvas", "--show", "1"]
    )
    assert result.exit_code == 0
    assert "34 blocks found" in result.output
    assert "BLOCK 0" in result.output


def test_export_command_regenerates_from_results_json(tmp_path):
    import json

    records = [{"Name": "X", "severity": "HIGH", "cvss": 7.5, "source": "OPENVAS"}]
    (tmp_path / "results.json").write_text(json.dumps(records), encoding="utf-8")
    result = runner.invoke(app, ["export", str(tmp_path), "-e", "sarif", "-e", "generic"])
    assert result.exit_code == 0
    assert (tmp_path / "results.sarif").exists()
    assert (tmp_path / "results.generic.json").exists()


def test_scanners_and_formats_commands():
    assert "openvas" in runner.invoke(app, ["scanners"]).output
    assert "sarif" in runner.invoke(app, ["formats"]).output
