"""Command-line interface. Thin consumer of the mulitaminer2 library."""
from __future__ import annotations

import logging
from pathlib import Path

import typer
from dotenv import load_dotenv

from mulitaminer2.llm import MODELS, FatalLLMError
from mulitaminer2.reader import BACKENDS, DEFAULT_BACKEND
from mulitaminer2.scanner_engine import all_scanners

app = typer.Typer(
    name="mulitaminer2",
    help="Extract structured vulnerability records from security-scanner PDF reports using LLMs.",
    no_args_is_help=True,
)


def _setup_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


@app.command()
def extract(
    report: Path = typer.Argument(..., exists=True, readable=True, help="Scanner PDF report"),
    scanner: str = typer.Option(..., "--scanner", "-s", help="See `mulitaminer2 scanners`"),
    model: str = typer.Option("deepseek", "--model", "-m", help=f"One of: {sorted(MODELS)}"),
    model_name: str | None = typer.Option(
        None, "--model-name", help="Provider model id override (for ollama/lmstudio)"
    ),
    pdf_backend: str = typer.Option(
        DEFAULT_BACKEND, "--pdf-backend", help=f"One of: {sorted(BACKENDS)}"
    ),
    export: list[str] = typer.Option(
        [], "--export", "-e",
        help="Extra output formats (repeatable). See `mulitaminer2 formats`.",
    ),
    xlsx: bool = typer.Option(False, "--xlsx", help="Shorthand for --export xlsx"),
    csv: bool = typer.Option(False, "--csv", help="Shorthand for --export csv"),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Run artifacts root"),
    debug: bool = typer.Option(False, "--debug", help="Dump layout/blocks/LLM traffic to the run dir"),
) -> None:
    """Extract vulnerabilities from REPORT into a fresh run directory."""
    _setup_logging(debug)
    load_dotenv()
    from mulitaminer2.pipeline import RunConfig, run

    config = RunConfig(
        input_path=report,
        scanner=scanner,
        model=model,
        model_name=model_name,
        pdf_backend=pdf_backend,
        formats=tuple(dict.fromkeys(
            list(export) + (["xlsx"] if xlsx else []) + (["csv"] if csv else [])
        )),
        output_dir=output_dir,
        debug=debug,
    )
    try:
        result, run_dir = run(config)
    except (FatalLLMError, ValueError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"\n{len(result.records)} records ({result.block_count} blocks) in "
        f"{result.duration_s}s — ${result.usage.cost_usd:.4f} "
        f"({result.usage.prompt_tokens}+{result.usage.completion_tokens} tokens, "
        f"{result.usage.calls} calls)"
    )
    if result.warnings:
        typer.secho(f"{len(result.warnings)} warning(s):", fg=typer.colors.YELLOW)
        for w in result.warnings:
            typer.secho(f"  - {w}", fg=typer.colors.YELLOW)
    typer.echo(f"Artifacts: {run_dir}")


@app.command()
def models() -> None:
    """List available model profiles."""
    for key, p in MODELS.items():
        kind = "local " if p.is_local else "cloud "
        keys = " / ".join(p.api_key_envs) or "no key needed"
        typer.echo(f"{key:<16} {kind} {p.model:<28} {keys}")


@app.command()
def segment(
    report: Path = typer.Argument(..., exists=True, readable=True, help="Scanner PDF report"),
    scanner: str = typer.Option(..., "--scanner", "-s", help="See `mulitaminer2 scanners`"),
    pdf_backend: str = typer.Option(
        DEFAULT_BACKEND, "--pdf-backend", help=f"One of: {sorted(BACKENDS)}"
    ),
    show: int = typer.Option(3, "--show", help="How many blocks to preview"),
    lines: int = typer.Option(6, "--lines", help="Preview lines per block"),
) -> None:
    """Segment REPORT into blocks WITHOUT calling any LLM (free, offline).

    The config-writing feedback loop (docs/SCANNER_CONFIGS.md): the block
    count must equal the report's finding count.
    """
    _setup_logging(debug=False)
    from mulitaminer2.reader import extract_pdf
    from mulitaminer2.scanner_engine import get_scanner

    profile = get_scanner(scanner)
    doc = extract_pdf(report, backend=pdf_backend)
    blocks = profile.segment(doc.text)
    typer.secho(f"\n{len(blocks)} blocks found in {report.name}", bold=True)
    for block in blocks[:show]:
        context = ", ".join(
            f"{k}={v}" for k, v in
            (("host", block.host), ("port", block.port),
             ("protocol", block.protocol), ("severity", block.severity_hint))
            if v is not None
        )
        typer.secho(f"\n--- BLOCK {block.id} ({context or 'no context'}) ---",
                    fg=typer.colors.CYAN)
        for line in block.text.splitlines()[:lines]:
            typer.echo(f"  {line}")
    if len(blocks) > show:
        typer.echo(f"\n... {len(blocks) - show} more blocks (use --show to see more)")


@app.command()
def formats() -> None:
    """List available export formats for --export."""
    from mulitaminer2.exporters import DESCRIPTIONS, EXPORTERS

    for name in sorted(EXPORTERS):
        typer.echo(f"{name:<9} {DESCRIPTIONS.get(name, '')}")


@app.command()
def scanners() -> None:
    """List available scanner profiles (built-in + MULITAMINER2_SCANNERS_DIR)."""
    for key, p in all_scanners().items():
        typer.echo(f"{key:<10} source={p.source:<11} max_vulns_per_chunk={p.max_vulns_per_chunk}")


if __name__ == "__main__":
    app()
