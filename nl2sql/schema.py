"""Introspect the live database into a compact schema description for the LLM.

Feeding the real schema (tables, columns, types) into the prompt is what keeps
the generated SQL grounded in tables that actually exist, instead of guessed.
"""

from __future__ import annotations

import duckdb


def list_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


def describe_schema(con: duckdb.DuckDBPyConnection) -> str:
    """Return a `CREATE TABLE`-like text block describing every table."""
    lines: list[str] = []
    for table in list_tables(con):
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            [table],
        ).fetchall()
        col_text = ",\n  ".join(f"{name} {dtype}" for name, dtype in cols)
        lines.append(f"TABLE {table} (\n  {col_text}\n)")
    return "\n\n".join(lines)
