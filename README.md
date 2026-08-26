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

## Analyst mode — computes the number, doesn't just write SQL

Text-to-SQL hands you rows. But when the real question is *"what's the average order value?"*, the answer is a **number**, and a language model reciting a number is a number you can't trust.

Analyst mode closes that gap with **tool-calling over a sandbox**. The agent has two tools — `run_sql` (a read-only SELECT through the same safety layer) and `run_python` (a short snippet run in a locked-down sandbox) — and it has to *compute* the figure by calling them. Every number it reports must appear in an executed tool result; if it doesn't, the answer is flagged `grounded=False` instead of being trusted. The executed SQL, the executed code, and the source rows travel with the answer.

The sandbox is allow-list based: the snippet is parsed to an AST, and anything outside a small whitelist — `import`, attribute access (so there's no `__class__`/`__globals__` escape), `lambda`, `for`/`while` loops, calls to anything but a fixed set of safe builtins — is rejected before a line runs, under `{"__builtins__": {}}` with a wall-clock timeout as a backstop. It's pure and fully unit-tested (`tests/test_sandbox.py`).

### Offline demo (no API key, no download)

A tiny **synthetic** dataset ships in `sample_data/`, so the whole thing runs with a deterministic scripted driver:

```bash
pip install -r requirements.txt
python -m nl2sql.cli build-sample     # build a DuckDB from sample_data/
python -m nl2sql.cli analyze          # the bundled demo question
```

```
Answer:   The average order value is the mean of the per-order item totals computed above.
Value:    159.0
Grounded: True   (steps: 3)

Trace (every number came from one of these executed steps):
  [1] run_sql     SELECT order_id, SUM(price) AS order_total FROM order_items GROUP BY order_id ...
  [2] run_python  result = round(sum(r['order_total'] for r in rows) / len(rows), 2)
```

Add `--live` (with `ANTHROPIC_API_KEY` set) to let Claude drive the tools and answer arbitrary questions.

## Run it (the Streamlit NL→SQL app)

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
