"""Load the Olist CSVs into a DuckDB file and open read-only connections.

The dataset is built once into a ``.duckdb`` file; every query then runs over a
``read_only=True`` connection, so the query path physically cannot write.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb


def _table_name(csv_path: Path) -> str:
    """Derive a clean table name from an Olist filename.

    ``olist_order_items_dataset.csv`` -> ``order_items``
    ``product_category_name_translation.csv`` -> ``product_category_name_translation``
    """
    stem = csv_path.stem
    if stem.startswith("olist_"):
        stem = stem[len("olist_"):]
    if stem.endswith("_dataset"):
        stem = stem[: -len("_dataset")]
    return stem


def build_database(csv_dir: str | os.PathLike, db_path: str | os.PathLike) -> list[str]:
    """Build the DuckDB file from every CSV in ``csv_dir``. Returns table names."""
    csv_dir = Path(csv_dir)
    db_path = Path(db_path)
    csvs = sorted(csv_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}. See data/README.md.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        created = []
        for csv in csvs:
            table = _table_name(csv)
            con.execute(
                f'CREATE TABLE "{table}" AS '
                f"SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)",
                [str(csv)],
            )
            created.append(table)
        return created
    finally:
        con.close()


def connect_readonly(db_path: str | os.PathLike) -> duckdb.DuckDBPyConnection:
    """Open a read-only connection to the built database."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database {db_path} not found. Run build_database() first."
        )
    return duckdb.connect(str(db_path), read_only=True)
