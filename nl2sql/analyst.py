"""The analyst: a tool-calling loop that COMPUTES the answer and proves it.

A *driver* decides the next action from the question, the schema and the trace so
far — either a tool call (``run_sql`` / ``run_python``) or a final answer. We
execute tool calls, append each to a ``trace``, and stop on the final answer.

The number the analyst reports must appear in a tool result; if it does not, the
result is flagged ``grounded=False`` instead of being trusted. That is the
anti-hallucination guarantee: the figure is executed, and the executed code plus
the source rows travel with it.

Two drivers ship here:

* :class:`ScriptedDriver` — deterministic, offline, no API key. Replays a fixed
  list of actions; used by the CLI demo and the tests.
* the Anthropic tool-use driver lives in :mod:`nl2sql.llm` (the ``--live`` path).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import duckdb

from .schema import describe_schema
from .tools import ToolCall, ToolContext, dispatch

# A driver is called with (question, schema_text, trace) and returns an action:
#   {"type": "tool", "tool": "run_sql"|"run_python", "args": {...}}
#   {"type": "final", "answer": str, "value": Any}
Driver = Callable[[str, str, list[ToolCall]], dict[str, Any]]


@dataclass
class Analysis:
    question: str
    answer_text: str = ""
    value: Any = None
    trace: list[ToolCall] = field(default_factory=list)
    source_rows: list[dict[str, Any]] = field(default_factory=list)
    grounded: bool = False
    steps: int = 0
    error: str | None = None


def analyze(
    question: str,
    con: duckdb.DuckDBPyConnection,
    *,
    drive: Driver | None = None,
    max_steps: int = 6,
    max_rows: int = 1000,
) -> Analysis:
    """Answer *question* by driving tools against a read-only DuckDB connection."""
    if drive is None:
        from .llm import tool_use_driver

        drive = tool_use_driver()

    schema_text = describe_schema(con)
    ctx = ToolContext(con, max_rows=max_rows)
    analysis = Analysis(question=question)

    for step in range(1, max_steps + 1):
        analysis.steps = step
        action = drive(question, schema_text, analysis.trace)
        if action.get("type") == "final":
            analysis.answer_text = str(action.get("answer", "")).strip()
            analysis.value = action.get("value")
            break
        call = dispatch(ctx, action.get("tool", ""), action.get("args", {}))
        analysis.trace.append(call)
    else:
        analysis.error = "reached max_steps without a final answer"

    analysis.source_rows = _last_sql_rows(analysis.trace)
    analysis.grounded = _is_grounded(analysis.value, analysis.trace)
    return analysis


# --- grounding -------------------------------------------------------------


def _num_eq(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return str(a) == str(b)


def _is_grounded(value: Any, trace: list[ToolCall]) -> bool:
    """True iff *value* matches a value that some executed tool actually produced."""
    if value is None:
        return False
    for call in trace:
        if not call.ok:
            continue
        if call.tool == "run_python" and _num_eq(value, call.result.get("result")):
            return True
        if call.tool == "run_sql":
            for row in call.result.get("rows", []):
                if any(_num_eq(value, cell) for cell in row.values()):
                    return True
    return False


def _last_sql_rows(trace: list[ToolCall]) -> list[dict[str, Any]]:
    for call in reversed(trace):
        if call.tool == "run_sql" and call.ok:
            return call.result.get("rows", [])
    return []


def _last_python_value(trace: list[ToolCall]) -> Any:
    for call in reversed(trace):
        if call.tool == "run_python" and call.ok:
            return call.result.get("result")
    return None


# --- offline driver --------------------------------------------------------


class ScriptedDriver:
    """A deterministic driver that replays a fixed list of actions (offline, no key).

    A final action may set ``"value": "$last_python"`` to report the most recent
    ``run_python`` result, so a demo shows the real computed number and stays
    grounded without the script hard-coding it.
    """

    def __init__(self, actions: list[dict[str, Any]]) -> None:
        self._actions = [dict(a) for a in actions]
        self._i = 0

    def __call__(self, question: str, schema_text: str, trace: list[ToolCall]) -> dict[str, Any]:
        if self._i >= len(self._actions):
            return {"type": "final", "answer": "(script exhausted)", "value": None}
        action = dict(self._actions[self._i])
        self._i += 1
        if action.get("type") == "final" and action.get("value") == "$last_python":
            action["value"] = _last_python_value(trace)
        return action
