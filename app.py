"""Streamlit UI for the NL->SQL agent over the Olist dataset."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from nl2sql.agent import answer_question
from nl2sql.db import build_database, connect_readonly
from nl2sql.schema import list_tables

DATA_DIR = os.environ.get("NL2SQL_DATA_DIR", "data")
DB_PATH = os.environ.get("NL2SQL_DB", "olist.duckdb")

st.set_page_config(page_title="NL to SQL over Olist", layout="wide")


@st.cache_resource
def get_connection():
    if not Path(DB_PATH).exists():
        return None
    return connect_readonly(DB_PATH)


with st.sidebar:
    st.header("Dataset")
    st.write("Point to a folder of Olist CSVs, then build the DuckDB database.")
    data_dir = st.text_input("CSV folder", DATA_DIR)
    if st.button("Build / rebuild database"):
        with st.spinner("Loading CSVs into DuckDB..."):
            tables = build_database(data_dir, DB_PATH)
        get_connection.clear()
        st.success(f"Built {len(tables)} tables: {', '.join(tables)}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.warning("Set ANTHROPIC_API_KEY to enable question answering.")

st.title("Ask the Olist e-commerce data in plain language")

con = get_connection()
if con is None:
    st.info("No database yet. Build it from the sidebar — see data/README.md to get the CSVs.")
    st.stop()

st.caption("Tables: " + ", ".join(list_tables(con)))

question = st.text_input(
    "Your question", placeholder="Which product categories sell the most?"
)
max_rows = st.slider("Max rows", 10, 5000, 1000, step=10)

if st.button("Run", type="primary") and question:
    with st.spinner("Thinking..."):
        ans = answer_question(question, con, max_rows=max_rows)

    if ans.explanation:
        st.write(ans.explanation)
    if ans.sql:
        st.code(ans.sql, language="sql")
    if ans.ok:
        df = pd.DataFrame(ans.rows, columns=ans.columns)
        st.dataframe(df, use_container_width=True)
        st.caption(f"{len(df)} rows · {ans.attempts} attempt(s)")
    else:
        st.error(
            f"Couldn't produce a valid query after {ans.attempts} attempts: {ans.error}"
        )
