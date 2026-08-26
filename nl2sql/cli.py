"""CLI for the NL data analyst over a DuckDB database.

Commands
--------
build-sample   Build a DuckDB from the bundled synthetic ``sample_data/`` (zero download).
analyze "Q"    Answer a question, printing the computed value + the tool trace + source rows.

Offline by default: a deterministic :class:`~nl2sql.analyst.ScriptedDriver` replays the bundled
demo, so it runs with no API key and no network. ``--live`` uses the Anthropic tool-use driver to
answer arbitrary questions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyst import ScriptedDriver, analyze
from .db import build_database, connect_readonly

SAMPLE_DIR = "sample_data"
DEFAULT_DB = "analyst.duckdb"

# The bundled offline demo: a question plus the exact tool plan that answers it.
DEMO_QUESTION = "What is the average order value (total item price per order, averaged across orders)?"
_DEMO_SCRIPT = [
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
    {
        "type": "final",
        "answer": "The average order value is the mean of the per-order item totals computed above.",
        "value": "$last_python",
    },
]


def cmd_build_sample(args: argparse.Namespace) -> int:
    tables = build_database(args.sample_dir, args.db)
    print(f"Built {len(tables)} tables into {args.db}: {', '.join(tables)}")
    return 0


def _print_analysis(analysis) -> None:
    print(f"Q: {analysis.question}\n")
    print(f"Answer:   {analysis.answer_text}")
    print(f"Value:    {analysis.value}")
    print(f"Grounded: {analysis.grounded}   (steps: {analysis.steps})")
    if analysis.error:
        print(f"Note:     {analysis.error}")
    print("\nTrace (every number came from one of these executed steps):")
    for i, call in enumerate(analysis.trace, 1):
        if call.tool == "run_sql":
            body = call.result["sql"] if call.ok else f"ERROR: {call.error}"
            print(f"  [{i}] run_sql     {body}")
        elif call.tool == "run_python":
            suffix = "" if call.ok else f"   ERROR: {call.error}"
            print(f"  [{i}] run_python  {call.args.get('code')}{suffix}")
    if analysis.source_rows:
        print(f"\nSource rows ({len(analysis.source_rows)} from the last SQL step):")
        for row in analysis.source_rows[:12]:
            print(f"  {row}")


def cmd_analyze(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(
            f"Database {args.db!r} not found. Build it first:\n"
            f"  python -m nl2sql.cli build-sample",
            file=sys.stderr,
        )
        return 2
    con = connect_readonly(args.db)

    if args.live:
        analysis = analyze(args.question, con)  # Anthropic tool-use driver
    else:
        if args.question != DEMO_QUESTION:
            print(
                "(offline mode replays the bundled scripted demo; pass --live to answer "
                "arbitrary questions with a real model)\n",
                file=sys.stderr,
            )
        analysis = analyze(DEMO_QUESTION, con, drive=ScriptedDriver(_DEMO_SCRIPT))

    _print_analysis(analysis)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nl2sql-analyst",
        description="A natural-language data analyst that COMPUTES the number and proves it "
        "(tool-calling + a sandbox), instead of only generating SQL.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build-sample", help="build a DuckDB from the bundled synthetic sample_data/")
    p_build.add_argument("--sample-dir", default=SAMPLE_DIR)
    p_build.add_argument("--db", default=DEFAULT_DB)
    p_build.set_defaults(func=cmd_build_sample)

    p_analyze = sub.add_parser("analyze", help="answer a question (offline demo by default)")
    p_analyze.add_argument("question", nargs="?", default=DEMO_QUESTION, help="the question to answer")
    p_analyze.add_argument("--db", default=DEFAULT_DB)
    p_analyze.add_argument("--live", action="store_true", help="use the real Anthropic tool-use driver")
    p_analyze.set_defaults(func=cmd_analyze)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
