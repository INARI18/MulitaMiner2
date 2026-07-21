"""CLI smoke tests (offline commands only)."""
from typer.testing import CliRunner

from mulitaminer2.cli import app

runner = CliRunner()


def test_segment_command_counts_blocks_offline():
    result = runner.invoke(
        app, ["segment", "resources/openvas/OpenVAS_JuiceShop.pdf",
              "--scanner", "openvas", "--show", "1"]
    )
    assert result.exit_code == 0
    assert "34 blocks found" in result.output
    assert "BLOCK 0" in result.output


def test_scanners_and_formats_commands():
    assert "openvas" in runner.invoke(app, ["scanners"]).output
    assert "sarif" in runner.invoke(app, ["formats"]).output
