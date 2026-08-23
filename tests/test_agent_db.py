import duckdb
import pytest

from nl2sql.agent import answer_question
from nl2sql.db import build_database, connect_readonly
from nl2sql.schema import describe_schema, list_tables


@pytest.fixture
def con(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / "olist_orders_dataset.csv").write_text(
        "order_id,customer_id,order_status\n"
        "1,10,delivered\n2,11,delivered\n3,12,shipped\n",
        encoding="utf-8",
    )
    (csv_dir / "olist_customers_dataset.csv").write_text(
        "customer_id,customer_state\n10,SP\n11,SP\n12,RJ\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "olist.duckdb"
    build_database(csv_dir, db_path)
    connection = connect_readonly(db_path)
    yield connection
    connection.close()


def test_tables_and_schema(con):
    assert set(list_tables(con)) == {"orders", "customers"}
    schema = describe_schema(con)
    assert "orders" in schema and "customers" in schema
    assert "order_status" in schema


def test_readonly_connection_blocks_writes(con):
    with pytest.raises(duckdb.Error):
        con.execute("CREATE TABLE z (x INTEGER)")


def test_agent_runs_a_generated_query(con):
    def fake_generate(question, schema_text, *, model=None, prior_sql=None, error=None):
        return (
            "SELECT order_status, COUNT(*) AS n FROM orders GROUP BY order_status",
            "Count orders by status.",
        )

    ans = answer_question("orders by status", con, generate=fake_generate)
    assert ans.ok
    assert ans.attempts == 1
    assert "LIMIT" in ans.sql
    assert dict(zip([c for c in ans.columns], range(len(ans.columns))))  # columns present
    result = {row[0]: row[1] for row in ans.rows}
    assert result == {"delivered": 2, "shipped": 1}


def test_agent_repairs_a_broken_query(con):
    calls = {"n": 0}

    def flaky_generate(question, schema_text, *, model=None, prior_sql=None, error=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("SELECT nope FROM orders", "first try")
        assert error is not None  # the failure was fed back for repair
        return ("SELECT COUNT(*) AS n FROM orders", "fixed")

    ans = answer_question("how many orders", con, generate=flaky_generate, max_repairs=2)
    assert ans.ok
    assert ans.attempts == 2
    assert ans.rows == [(3,)]


def test_agent_gives_up_after_max_repairs(con):
    def always_broken(question, schema_text, *, model=None, prior_sql=None, error=None):
        return ("SELECT nope FROM orders", "nope")

    ans = answer_question("bad", con, generate=always_broken, max_repairs=1)
    assert not ans.ok
    assert ans.error is not None
    assert ans.attempts == 2
