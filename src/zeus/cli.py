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
from zeus.core.writer import FORMATS, write, write_tables

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
    out: Optional[Path] = typer.Option(None, "--out", help="Output dir (default: output/<use_case>/)"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Deterministic seed"),
    option: list[str] = typer.Option([], "--option", "-o", help="Per-use-case option, key=value"),
) -> None:
    """Generate synthetic data for a use case."""
    opts = dict(kv.split("=", 1) for kv in option)
    cfg = GeneratorConfig(count=count, seed=seed, options=opts)
    gen = get(use_case)(cfg)
    tables = gen.generate_tables()

    if len(tables) == 1 and out is not None:
        # Single-table generator with an explicit output path.
        write(next(iter(tables.values())), out, fmt, table=use_case)
        typer.echo(f"✓ wrote {count} {use_case} records → {out}")
        return

    out_dir = out or Path("output") / use_case
    paths = write_tables(tables, out_dir, fmt, db_name=use_case)
    for name, records in tables.items():
        typer.echo(f"  {name:<24} {len(records):>7} rows")
    typer.echo(f"✓ {use_case}: {len(tables)} table(s) → {paths[0].parent if fmt != 'sqlite' else paths[0]}")


if __name__ == "__main__":
    app()
