"""Command-line interface. Thin consumer of the mulitaminer2 library."""

import typer

app = typer.Typer(
    name="mulitaminer2",
    help="Extract structured vulnerability records from security-scanner PDF reports using LLMs.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """MulitaMiner2 CLI."""


if __name__ == "__main__":
    app()
