"""The analyst loop computes the number, keeps a trace, and guards grounding."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2sql.analyst import ScriptedDriver, analyze
from nl2sql.db import build_database, connect_readonly

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def con(tmp_path):
    db = tmp_path / "analyst.duckdb"
    build_database(SAMPLE, db)
    connection = connect_readonly(db)
    yield connection
    connection.close()


_AVG_SCRIPT = [
    {
        "type": "tool",
        "tool": "run_sql",
        "args": {"sql": "SELECT order_id, SUM(price) AS order_total FROM order_items GROUP BY order_id"},
    },
    {
        "type": "tool",
        "tool": "run_python",
        "args": {"code": "result = round(sum(r['order_total'] for r in rows) / len(rows), 2)"},
    },
    {"type": "final", "answer": "average order value", "value": "$last_python"},
]


def test_analyze_computes_a_grounded_value(con):
    result = analyze("average order value?", con, drive=ScriptedDriver(_AVG_SCRIPT))
    assert result.value == 159.0
    assert result.grounded is True
    assert [c.tool for c in result.trace] == ["run_sql", "run_python"]
    assert len(result.source_rows) == 10  # per-order totals from the last SQL step


def test_fabricated_number_is_not_grounded(con):
    script = [
        {"type": "tool", "tool": "run_sql", "args": {"sql": "SELECT SUM(price) AS total FROM order_items"}},
        {"type": "final", "answer": "made up", "value": 999999},  # not in any tool result
    ]
    result = analyze("q", con, drive=ScriptedDriver(script))
    assert result.value == 999999
    assert result.grounded is False


def test_value_present_in_sql_result_is_grounded(con):
    script = [
        {"type": "tool", "tool": "run_sql", "args": {"sql": "SELECT SUM(price) AS total FROM order_items"}},
        {"type": "final", "answer": "total item revenue", "value": 1590.0},
    ]
    result = analyze("q", con, drive=ScriptedDriver(script))
    assert result.grounded is True


def test_sql_error_is_tolerated_not_raised(con):
    script = [
        {"type": "tool", "tool": "run_sql", "args": {"sql": "SELECT * FROM nonexistent_table"}},
        {"type": "final", "answer": "n/a", "value": None},
    ]
    result = analyze("q", con, drive=ScriptedDriver(script))
    assert result.trace[0].ok is False
    assert result.grounded is False
