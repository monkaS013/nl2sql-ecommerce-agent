"""Prompt templates for SQL generation."""

from __future__ import annotations

SYSTEM_PROMPT = """You translate a business question into ONE DuckDB SQL query.

Rules:
- Return a single read-only SELECT (a leading WITH ... SELECT is fine). Never
  write, alter, attach, copy, or load anything.
- Use only the tables and columns in the provided schema. Never invent names.
- Prefer explicit JOINs and clear column aliases.
- When the question is vague about time or units, state your assumption in the
  explanation rather than guessing silently.
- Reply as a JSON object with exactly two string fields: "sql" and
  "explanation". No prose outside the JSON.
"""


def build_user_prompt(
    question: str,
    schema_text: str,
    *,
    prior_sql: str | None = None,
    error: str | None = None,
) -> str:
    parts = [
        "Database schema:",
        schema_text,
        "",
        f"Question: {question}",
    ]
    if prior_sql and error:
        parts += [
            "",
            "Your previous query failed. Fix it.",
            f"Previous SQL:\n{prior_sql}",
            f"Database error:\n{error}",
        ]
    return "\n".join(parts)
