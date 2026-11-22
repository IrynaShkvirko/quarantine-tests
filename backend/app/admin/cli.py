"""``fq-admin``: operator commands. Later tasks add seed-demo, purge-demo and so on."""

from importlib.metadata import version as package_version

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Flaky Test Quarantine admin tools."""


@app.command()
def version() -> None:
    """Print the backend version."""
    typer.echo(package_version("fq-backend"))


if __name__ == "__main__":
    app()
