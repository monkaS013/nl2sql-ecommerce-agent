"""The two tools the analyst can call: ``run_sql`` and ``run_python``.

``run_sql`` runs one read-only SELECT (through the existing safety layer) against
the DuckDB connection and returns columns + rows. ``run_python`` runs a numeric
snippet over the rows from the most recent ``run_sql`` in the sandbox. Every
number the analyst reports comes from one of these *executed* tools — never from
the model's free text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb

from .safety import UnsafeSQLError, validate_sql
from .sandbox import SandboxError, run_python

# Tool schemas, in the shape an Anthropic tool-use request expects.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_sql",
        "description": (
            "Run ONE read-only SQL SELECT against the database and get the rows back. "
            "Use it to fetch the raw numbers you need. Only a single SELECT/WITH is allowed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single read-only SELECT query."}},
            "required": ["sql"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Run a short Python snippet to compute a value from the most recent run_sql result. "
            "Available names: `rows` (list of dicts) and `columns` (list of names). Assign the "
            "answer to a variable called `result`. No imports, no attribute access, no loops "
            "(use comprehensions)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python snippet assigning `result`."}},
            "required": ["code"],
        },
    },
]


@dataclass
class ToolCall:
    """One executed tool call and its outcome (kept in the analysis trace)."""

    tool: str
    args: dict[str, Any]
    result: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ToolContext:
    """Holds the DB connection and the rows produced by the last ``run_sql``."""

    def __init__(self, con: duckdb.DuckDBPyConnection, *, max_rows: int = 1000) -> None:
        self.con = con
        self.max_rows = max_rows
        self.last_rows: list[dict[str, Any]] = []
        self.last_columns: list[str] = []


def _run_sql(ctx: ToolContext, sql: str) -> dict[str, Any]:
    safe_sql = validate_sql(sql, max_rows=ctx.max_rows)
    cur = ctx.con.execute(safe_sql)
    columns = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(columns, r)) for r in cur.fetchall()]
    ctx.last_columns = columns
    ctx.last_rows = rows
    return {"sql": safe_sql, "columns": columns, "rows": rows}


def _run_python(ctx: ToolContext, code: str) -> dict[str, Any]:
    value = run_python(code, {"rows": ctx.last_rows, "columns": ctx.last_columns})
    return {"code": code, "result": value}


def dispatch(ctx: ToolContext, name: str, args: dict[str, Any]) -> ToolCall:
    """Execute a tool call, capturing a clean error instead of raising."""
    call = ToolCall(tool=name, args=args)
    try:
        if name == "run_sql":
            call.result = _run_sql(ctx, args["sql"])
        elif name == "run_python":
            call.result = _run_python(ctx, args["code"])
        else:
            call.error = f"unknown tool: {name!r}"
    except (UnsafeSQLError, SandboxError, duckdb.Error) as exc:
        call.error = str(exc)
    except KeyError as exc:
        call.error = f"missing tool argument: {exc}"
    return call
