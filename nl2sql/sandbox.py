"""A tiny allow-list sandbox for computing a value from query results.

The analyst sometimes needs arithmetic that SQL did not do (a ratio, a growth
rate, an average of per-group totals). Rather than let the model do the math in
its head — where it can hallucinate a digit — it emits a short Python snippet
that we execute *here*, under a strict allow-list:

* the snippet is parsed to an AST and **every node is checked against a
  whitelist**; anything else (``import``, attribute access, ``lambda``, ``for``/
  ``while`` loops, function defs) is rejected before a single line runs;
* calls are only allowed to a fixed set of safe builtins;
* any name starting with ``__`` is rejected, and the code runs with
  ``{"__builtins__": {}}`` so there is no path back to the real builtins;
* execution runs in a worker thread with a wall-clock **timeout** as a backstop
  (there are no unbounded loops in the grammar, so this only guards pathological
  comprehensions).

The snippet must assign its answer to a variable named ``result``.
"""

from __future__ import annotations

import ast
import threading
from typing import Any

DEFAULT_TIMEOUT = 2.0

# Builtins the snippet may call. No __import__, open, eval, exec, getattr, etc.
SAFE_BUILTINS: dict[str, Any] = {
    "sum": sum, "min": min, "max": max, "len": len, "round": round, "abs": abs,
    "sorted": sorted, "float": float, "int": int, "bool": bool, "str": str,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "range": range,
    "zip": zip, "enumerate": enumerate, "any": any, "all": all,
}

# AST node types the sandbox permits. Notably ABSENT: Import/ImportFrom,
# Attribute (no ``x.y`` at all -> no dunder escape), Lambda, FunctionDef,
# For/While (no unbounded loops), With/Try, Global/Nonlocal, Starred.
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign,
    ast.Load, ast.Store,
    ast.Name, ast.Constant,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.Subscript, ast.Slice,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.IfExp, ast.Call, ast.keyword,
)


class SandboxError(Exception):
    """Raised when a snippet is rejected by the allow-list or fails to run."""


def _validate(code: str) -> ast.Module:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"snippet is not valid Python: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise SandboxError(
                f"disallowed syntax: {type(node).__name__} is not permitted in the sandbox"
            )
        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise SandboxError(f"disallowed name: {node.id!r}")
        if isinstance(node, ast.Call):
            # Only direct calls to whitelisted builtins by name are allowed.
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_BUILTINS:
                target = getattr(node.func, "id", type(node.func).__name__)
                raise SandboxError(f"disallowed call: {target!r} is not a safe builtin")
    return tree


def run_python(code: str, data: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT) -> Any:
    """Execute *code* over *data* and return the value it assigns to ``result``.

    *data* is exposed as read-only locals (e.g. ``rows``, ``columns``). Raises
    :class:`SandboxError` if the code is rejected, times out, errors, or never
    assigns ``result``.
    """
    tree = _validate(code)
    namespace: dict[str, Any] = {"__builtins__": {}}
    namespace.update(SAFE_BUILTINS)
    namespace.update(data)

    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            exec(compile(tree, "<sandbox>", "exec"), namespace)  # noqa: S102 - guarded by allow-list
            box["result"] = namespace.get("result", _MISSING)
        except Exception as exc:  # surfaced as SandboxError below
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise SandboxError(f"snippet exceeded the {timeout}s time limit")
    if "error" in box:
        raise SandboxError(f"snippet raised {type(box['error']).__name__}: {box['error']}")
    if box.get("result", _MISSING) is _MISSING:
        raise SandboxError("snippet did not assign a variable named `result`")
    return box["result"]


_MISSING = object()
