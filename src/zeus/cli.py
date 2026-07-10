"""zeus CLI.

    zeus list
    zeus generate <use_case> --count 500 --format jsonl --out output/data.jsonl
    zeus generate <use_case> -o key=value -o other=42   # per-use-case options
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from zeus import generators  # noqa: F401  (importing registers all generators)
from zeus.core.base import GeneratorConfig
from zeus.core.registry import all_generators, get
from zeus.core.writer import FORMATS, write

app = typer.Typer(help="Zeus — synthetic data generator for the Hermes MCP stack.")


@app.command("list")
def list_cmd() -> None:
    """List available use-case generators."""
    gens = all_generators()
    if not gens:
        typer.echo("No generators registered yet.")
        raise typer.Exit()
    width = max(len(n) for n in gens)
    for name, cls in sorted(gens.items()):
        typer.echo(f"{name:<{width}}  {cls.description}")


@app.command()
def generate(
    use_case: str = typer.Argument(..., help="Generator name (see `zeus list`)"),
    count: int = typer.Option(100, "--count", "-n", help="Number of records"),
    fmt: str = typer.Option("jsonl", "--format", "-f", help=f"One of: {', '.join(FORMATS)}"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output path (default: output/<use_case>.<fmt>)"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Deterministic seed"),
    option: list[str] = typer.Option([], "--option", "-o", help="Per-use-case option, key=value"),
) -> None:
    """Generate synthetic data for a use case."""
    opts = dict(kv.split("=", 1) for kv in option)
    cfg = GeneratorConfig(count=count, seed=seed, options=opts)
    gen = get(use_case)(cfg)
    ext = "db" if fmt == "sqlite" else fmt
    path = out or Path("output") / f"{use_case}.{ext}"
    write(gen.generate(), path, fmt, table=use_case)
    typer.echo(f"✓ wrote {count} {use_case} records → {path}")


if __name__ == "__main__":
    app()
