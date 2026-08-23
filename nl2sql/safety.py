"""SQL safety layer.

The LLM writes the SQL, so nothing it produces is trusted. Two lines of defense:

1. This module rejects anything that isn't a single read-only SELECT/CTE before
   the query ever runs, and forces a row cap.
2. The query connection is opened read-only (see ``db.connect_readonly``), so
   even a statement that slipped past here cannot write.

Keeping the rules in pure functions means the whole safety story is testable
without a database or an API key.
"""

from __future__ import annotations

import re

# Keywords that write, change settings, touch the filesystem, or load code.
# Function-like words (replace, ...) are deliberately absent — the read-only
# connection is the hard guarantee; this set is the early, friendly reject.
DISALLOWED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT", "INSTALL", "LOAD",
    "PRAGMA", "VACUUM", "CALL", "GRANT", "REVOKE",
}

_LIMIT_RE = re.compile(r"\blimit\b\s+\d+", re.IGNORECASE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_WORD_RE = re.compile(r"[A-Za-z_]+")


class UnsafeSQLError(ValueError):
    """Raised when a statement is not a single read-only SELECT."""


def strip_comments(sql: str) -> str:
    """Remove block and line comments so they can't hide a second statement."""
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", sql))


def ensure_limit(sql: str, max_rows: int = 1000) -> str:
    """Append ``LIMIT max_rows`` when the query has no explicit limit."""
    clean = sql.rstrip().rstrip(";").rstrip()
    if _LIMIT_RE.search(clean):
        return clean
    return f"{clean}\nLIMIT {max_rows}"


def validate_sql(sql: str, max_rows: int = 1000) -> str:
    """Return a cleaned, row-capped SELECT, or raise ``UnsafeSQLError``.

    Rejects: empty input, multiple statements, anything that doesn't start with
    SELECT or WITH, and any disallowed (write/DDL/attach/load) keyword.
    """
    without_comments = strip_comments(sql).strip()
    statement = without_comments.rstrip(";").strip()

    if not statement:
        raise UnsafeSQLError("Empty query.")

    if ";" in statement:
        raise UnsafeSQLError("Only a single statement is allowed.")

    lowered = statement.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise UnsafeSQLError("Only SELECT (or WITH ... SELECT) queries are allowed.")

    tokens = {t.upper() for t in _WORD_RE.findall(statement)}
    offending = sorted(tokens & DISALLOWED_KEYWORDS)
    if offending:
        raise UnsafeSQLError(f"Disallowed keyword(s): {', '.join(offending)}.")

    return ensure_limit(statement, max_rows)
