"""The agent loop: question -> SQL -> validate -> execute, with self-repair.

If a generated query fails validation or errors in the database, the failure is
fed back to the model so it can fix its own SQL, up to ``max_repairs`` times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import duckdb

from .safety import UnsafeSQLError, validate_sql
from .schema import describe_schema


@dataclass
class Answer:
    question: str
    sql: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    explanation: str = ""
    attempts: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.sql is not None


def answer_question(
    question: str,
    con: duckdb.DuckDBPyConnection,
    *,
    max_rows: int = 1000,
    max_repairs: int = 2,
    generate: Callable[..., tuple[str, str]] | None = None,
    model: str | None = None,
) -> Answer:
    """Answer a natural-language question against a read-only DuckDB connection.

    ``generate`` defaults to the Anthropic-backed generator but can be injected
    (a fake) in tests so the loop runs without any network call.
    """
    if generate is None:
        from .llm import generate_sql as generate

    schema_text = describe_schema(con)
    prior_sql: str | None = None
    last_error: str | None = None

    for attempt in range(1, max_repairs + 2):
        raw_sql, explanation = generate(
            question, schema_text, model=model, prior_sql=prior_sql, error=last_error
        )
        try:
            safe_sql = validate_sql(raw_sql, max_rows=max_rows)
            cur = con.execute(safe_sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return Answer(
                question=question,
                sql=safe_sql,
                columns=columns,
                rows=rows,
                explanation=explanation,
                attempts=attempt,
            )
        except (UnsafeSQLError, duckdb.Error) as exc:
            prior_sql = raw_sql
            last_error = str(exc)

    return Answer(
        question=question,
        sql=prior_sql,
        explanation="",
        attempts=max_repairs + 1,
        error=last_error,
    )
