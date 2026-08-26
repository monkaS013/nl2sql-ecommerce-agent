"""The run_sql / run_python tools, over the synthetic sample database (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2sql.db import build_database, connect_readonly
from nl2sql.tools import ToolContext, dispatch

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def con(tmp_path):
    db = tmp_path / "tools.duckdb"
    build_database(SAMPLE, db)
    connection = connect_readonly(db)
    yield connection
    connection.close()


def test_run_sql_returns_rows(con):
    ctx = ToolContext(con)
    call = dispatch(ctx, "run_sql", {"sql": "SELECT COUNT(*) AS n FROM orders"})
    assert call.ok
    assert call.result["rows"][0]["n"] == 10


def test_run_sql_rejects_non_select(con):
    ctx = ToolContext(con)
    call = dispatch(ctx, "run_sql", {"sql": "DROP TABLE orders"})
    assert not call.ok  # the safety layer rejects it; dispatch returns a clean error


def test_run_python_computes_over_last_sql(con):
    ctx = ToolContext(con)
    dispatch(ctx, "run_sql", {"sql": "SELECT price FROM order_items"})
    call = dispatch(ctx, "run_python", {"code": "result = round(sum(r['price'] for r in rows), 2)"})
    assert call.ok
    assert call.result["result"] == 1590.0


def test_run_python_sandbox_error_is_clean(con):
    ctx = ToolContext(con)
    call = dispatch(ctx, "run_python", {"code": "import os"})
    assert not call.ok
    assert "disallowed" in call.error.lower()


def test_unknown_tool_is_a_clean_error(con):
    ctx = ToolContext(con)
    call = dispatch(ctx, "frobnicate", {})
    assert not call.ok
