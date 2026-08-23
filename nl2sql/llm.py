"""LLM boundary — the only module that talks to a model provider.

Isolated on purpose: swapping Anthropic for another provider is a change to this
file alone. ``anthropic`` is imported lazily so the rest of the package (and its
tests) import without the SDK or an API key present.
"""

from __future__ import annotations

import json
import os
import re

DEFAULT_MODEL = os.environ.get("NL2SQL_MODEL", "claude-haiku-4-5-20251001")

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Parse the model reply into {sql, explanation}, tolerating fenced output."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return json.loads(match.group(0))
    # Last resort: treat the whole reply as the SQL.
    return {"sql": text.strip(), "explanation": ""}


def generate_sql(
    question: str,
    schema_text: str,
    *,
    model: str | None = None,
    prior_sql: str | None = None,
    error: str | None = None,
    max_tokens: int = 1024,
) -> tuple[str, str]:
    """Ask the model for a SQL query. Returns ``(sql, explanation)``."""
    import anthropic  # lazy: keeps the package importable without the SDK

    from .prompts import SYSTEM_PROMPT, build_user_prompt

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    message = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(
                    question, schema_text, prior_sql=prior_sql, error=error
                ),
            }
        ],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    payload = _extract_json(text)
    return payload.get("sql", "").strip(), payload.get("explanation", "").strip()
