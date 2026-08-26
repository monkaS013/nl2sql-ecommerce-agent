"""The sandbox allows only safe numeric snippets and rejects everything else."""

from __future__ import annotations

import pytest

from nl2sql.sandbox import SandboxError, run_python


def test_arithmetic_and_sum_over_data():
    rows = [{"x": 10}, {"x": 20}, {"x": 30}]
    value = run_python("result = sum(r['x'] for r in rows) / len(rows)", {"rows": rows})
    assert value == 20


def test_builtins_and_comprehension():
    assert run_python("result = round(max([1.5, 2.7, 2.0]), 1)", {}) == 2.7
    assert run_python("result = sorted([3, 1, 2])[0]", {}) == 1


def test_rejects_import_statement():
    with pytest.raises(SandboxError):
        run_python("import os\nresult = 1", {})


def test_rejects_dunder_import_call():
    with pytest.raises(SandboxError):
        run_python("result = __import__('os')", {})


def test_rejects_attribute_access():
    # No attribute access at all -> no dunder escape hatch.
    with pytest.raises(SandboxError):
        run_python("result = (1).__class__", {})


def test_rejects_open_and_eval_and_exec():
    for snippet in ("result = open('x')", "result = eval('1+1')", "result = exec('x=1')"):
        with pytest.raises(SandboxError):
            run_python(snippet, {})


def test_rejects_for_loop():
    with pytest.raises(SandboxError):
        run_python("total = 0\nfor i in range(3):\n    total = total + i\nresult = total", {})


def test_rejects_lambda():
    with pytest.raises(SandboxError):
        run_python("f = lambda x: x\nresult = f(1)", {})


def test_requires_result_assignment():
    with pytest.raises(SandboxError):
        run_python("x = 5", {})


def test_timeout_backstop():
    with pytest.raises(SandboxError):
        run_python("result = sum(1 for _ in range(10**7))", {}, timeout=0.001)
