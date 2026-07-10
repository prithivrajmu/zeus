"""Output writers.

zaia (the MCP server) will read these artifacts, so formats are kept simple
and self-describing: json, jsonl, csv, and sqlite.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

FORMATS = ("json", "jsonl", "csv", "sqlite")


def write(records: Iterable[dict[str, Any]], out: Path, fmt: str, table: str = "records") -> Path:
    records = list(records)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        out.write_text(json.dumps(records, indent=2, default=str))
    elif fmt == "jsonl":
        with out.open("w") as f:
            for r in records:
                f.write(json.dumps(r, default=str) + "\n")
    elif fmt == "csv":
        if not records:
            out.write_text("")
        else:
            keys = list(records[0].keys())
            with out.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows({k: _flat(v) for k, v in r.items()} for r in records)
    elif fmt == "sqlite":
        _write_sqlite(records, out, table)
    else:
        raise ValueError(f"Unknown format {fmt!r}. Choose from: {', '.join(FORMATS)}")
    return out


def write_tables(
    tables: dict[str, list[dict[str, Any]]], out_dir: Path, fmt: str, db_name: str = "raw"
) -> list[Path]:
    """Write a set of related raw tables.

    - json/jsonl/csv → one file per table under ``out_dir``
    - sqlite         → a single ``<db_name>.db`` containing every table,
                       which is the friendliest shape for downstream ETL/ELT.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if fmt == "sqlite":
        db = out_dir / f"{db_name}.db"
        db.unlink(missing_ok=True)
        for name, records in tables.items():
            _write_sqlite(records, db, name)
        written.append(db)
    else:
        for name, records in tables.items():
            written.append(write(records, out_dir / f"{name}.{fmt}", fmt, table=name))
    return written


def _flat(v: Any) -> Any:
    """CSV cells can't hold nested structures — serialize them."""
    return json.dumps(v, default=str) if isinstance(v, (dict, list)) else v


def _write_sqlite(records: list[dict[str, Any]], out: Path, table: str) -> None:
    if not records:
        return
    keys = list(records[0].keys())
    cols = ", ".join(f'"{k}"' for k in keys)
    placeholders = ", ".join("?" for _ in keys)
    con = sqlite3.connect(out)
    try:
        con.execute(f'DROP TABLE IF EXISTS "{table}"')
        con.execute(f'CREATE TABLE "{table}" ({cols})')
        con.executemany(
            f'INSERT INTO "{table}" VALUES ({placeholders})',
            ([_flat(r.get(k)) for k in keys] for r in records),
        )
        con.commit()
    finally:
        con.close()
