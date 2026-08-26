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


# --- analyst tool-use driver (the --live path for nl2sql.analyst) -----------

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")

_ANALYST_SYSTEM = (
    "You are a data analyst. Answer the user's question by calling tools to run SQL "
    "and compute values. NEVER state a number you did not obtain from a tool result. "
    "When you have the answer, reply in plain text stating it clearly.\n\nSchema:\n{schema}"
)


def _first_number(text: str):
    """Best-effort: pull the first numeric literal out of the model's final text."""
    match = _NUMBER_RE.search(text or "")
    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        return float(token) if ("." in token) else int(token)
    except ValueError:
        return None


def tool_use_driver(model: str | None = None, max_tokens: int = 1024):
    """Return a stateful ``drive(question, schema_text, trace)`` backed by Claude tool-use.

    ``anthropic`` is imported lazily, so the analyst runs offline (with a scripted
    driver) without the SDK or an API key present.
    """
    import anthropic  # lazy

    from .tools import TOOLS

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    state: dict = {"messages": None, "system": None, "last_tool_use_id": None}

    def drive(question: str, schema_text: str, trace: list) -> dict:
        if state["messages"] is None:
            state["system"] = _ANALYST_SYSTEM.format(schema=schema_text)
            state["messages"] = [{"role": "user", "content": f"Question: {question}"}]
        else:
            last = trace[-1]
            payload = last.result if last.ok else {"error": last.error}
            state["messages"].append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": state["last_tool_use_id"],
                            "content": json.dumps(payload, default=str),
                        }
                    ],
                }
            )

        message = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=state["system"],
            tools=TOOLS,
            messages=state["messages"],
        )
        state["messages"].append({"role": "assistant", "content": message.content})

        tool_use = next(
            (b for b in message.content if getattr(b, "type", None) == "tool_use"), None
        )
        if tool_use is not None:
            state["last_tool_use_id"] = tool_use.id
            return {"type": "tool", "tool": tool_use.name, "args": dict(tool_use.input)}

        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
        return {"type": "final", "answer": text.strip(), "value": _first_number(text)}

    return drive
