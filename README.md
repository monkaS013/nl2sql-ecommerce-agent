# NL→SQL agent over Olist e-commerce data

*[Português](README.pt-BR.md)*

Ask a public e-commerce dataset questions in plain language and get back an answer, the SQL behind it, and the model's reasoning. The interesting part isn't the LLM call — it's the safety layer and the self-repair loop around it.

## What it does

You type "which product categories sell the most?"; the agent reads the live database schema, writes a DuckDB query, checks it's a read-only SELECT, runs it, and shows the table plus the SQL it used. If the query errors, the database error is fed back to the model to fix its own SQL.

## Why it's built this way

- **Schema-aware prompting.** The real tables and columns are introspected from the database and put in the prompt, so the model writes SQL against tables that exist instead of guessing names.
- **A SQL safety layer I actually trust.** The LLM's output is never trusted. Two lines of defense: a validator that rejects anything but a single read-only SELECT/CTE (and forces a row cap), and a DuckDB connection opened `read_only=True`, so even a statement that slipped past the validator can't write. The rules are pure functions — the whole safety story is tested without a database or an API key.
- **Self-repair loop.** A failed query (bad validation or a database error) goes back to the model with the error, up to a set number of retries. The agent reports how many attempts it took.
- **One provider boundary.** Every model call lives in `nl2sql/llm.py`. Swapping Anthropic for another provider is a change to that one file; the SDK is imported lazily so the rest of the package imports without it.

## Architecture

```
question
   │
   ▼
describe_schema(con) ──▶ llm.generate_sql() ──▶ safety.validate_sql()
                                                      │  ok            │ error
                                                      ▼                ▼
                                              con.execute()      feed error back (repair)
                                                      │
                                                      ▼
                                                   Answer(sql, rows, attempts)
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
# download the Olist CSVs into data/ — see data/README.md
streamlit run app.py        # build the database from the sidebar, then ask
```

## Tests

The core (safety rules, schema introspection, read-only enforcement, the repair loop with an injected fake model) runs with no API key:

```bash
python -m pytest -q
```

## Stack

Python · DuckDB · Anthropic (Claude) · Streamlit · pytest.

## Dataset

Brazilian E-Commerce Public Dataset by Olist (public, ~100k orders). Not committed — see [data/README.md](data/README.md).
