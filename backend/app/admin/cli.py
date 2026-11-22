"""``fq-admin``: operator commands. Later tasks add seed-demo, purge-demo and so on."""

import json
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import typer

from app.config.loader import MODELS, ConfigError, load_config, model_for

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Flaky Test Quarantine admin tools."""


@app.command()
def version() -> None:
    """Print the backend version."""
    typer.echo(package_version("fq-backend"))


@app.command("export-schemas")
def export_schemas(
    out: Annotated[Path, typer.Option(help="Output directory")] = Path("config-example/schemas"),
) -> None:
    """Write one JSON Schema per config file (for editor autocomplete and fq-cli)."""
    out.mkdir(parents=True, exist_ok=True)
    for stem, model in MODELS.items():
        schema = json.dumps(model.model_json_schema(), indent=2) + "\n"
        (out / f"{stem}.schema.json").write_text(schema, encoding="utf-8")


@app.command("validate-config")
def validate_config(files: list[Path]) -> None:
    """Validate config files (type detected from the file name); print all errors or OK."""
    problems: list[str] = []
    for path in files:
        try:
            load_config(path, model_for(path))
        except ConfigError as exc:
            problems += exc.problems
    if problems:
        typer.echo("\n".join(problems), err=True)
        raise typer.Exit(1)
    typer.echo("OK")


if __name__ == "__main__":
    app()
