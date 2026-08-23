import pytest

from nl2sql.safety import UnsafeSQLError, ensure_limit, validate_sql


def test_plain_select_is_allowed_and_capped():
    out = validate_sql("SELECT 1", max_rows=500)
    assert out.lower().startswith("select 1")
    assert out.strip().endswith("LIMIT 500")


def test_cte_is_allowed():
    out = validate_sql("WITH t AS (SELECT 1 AS x) SELECT * FROM t")
    assert out.lower().startswith("with")


def test_existing_limit_is_preserved():
    out = validate_sql("SELECT * FROM orders LIMIT 5")
    assert out.count("LIMIT") == 1
    assert out.strip().endswith("LIMIT 5")


def test_ensure_limit_is_idempotent():
    once = ensure_limit("SELECT 1", 10)
    assert ensure_limit(once, 10) == once


def test_underscore_columns_do_not_false_positive():
    # `created_at` / `update_ts` must not trip the CREATE/UPDATE keyword check.
    out = validate_sql("SELECT created_at, update_ts FROM orders")
    assert "created_at" in out


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET x = 1",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "ALTER TABLE orders ADD COLUMN y int",
        "COPY orders TO 'out.csv'",
        "ATTACH 'evil.db'",
        "PRAGMA database_list",
        "INSTALL httpfs",
    ],
)
def test_write_and_ddl_are_rejected(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


def test_multiple_statements_are_rejected():
    with pytest.raises(UnsafeSQLError):
        validate_sql("SELECT 1; SELECT 2")


def test_hidden_drop_after_select_is_rejected():
    with pytest.raises(UnsafeSQLError):
        validate_sql("SELECT 1; DROP TABLE orders")


def test_empty_is_rejected():
    with pytest.raises(UnsafeSQLError):
        validate_sql("   ")


def test_non_select_is_rejected():
    with pytest.raises(UnsafeSQLError):
        validate_sql("EXPLAIN ANALYZE SELECT 1")
