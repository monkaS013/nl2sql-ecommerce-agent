# NL→SQL agent over Olist e-commerce data

*[Português](README.pt-BR.md)*

Ask a public e-commerce dataset questions in plain language. You get back an answer, plus the SQL behind it and the model's reasoning. The LLM call is the easy part; the safety layer and the self-repair loop around it are where the work went.

## What it does

You type "which product categories sell the most?". The agent reads the live database schema, writes a DuckDB query, checks that it's a read-only SELECT, runs it, and shows the table along with the SQL it used. If the query errors, the database error goes back to the model so it can fix its own SQL.

## Why it's built this way

- **Schema-aware prompting.** The real tables and columns are introspected from the database and go into the prompt, so the model writes SQL against names it can actually see.
- **A SQL safety layer.** I treat the model's output as untrusted, so there are two lines of defense. A validator rejects anything that isn't a single read-only SELECT/CTE, and forces a row cap. Underneath it, the DuckDB connection is opened with `read_only=True`, so a statement that slipped past the validator still can't write through that connection. Both rules are pure functions, which is why the safety tests run without a database or an API key.
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

## Analyst mode

Text-to-SQL hands you rows. But when the real question is *"what's the average order value?"*, what you want back is a single number, and a language model can recite a number without ever having computed it.

Analyst mode closes that gap with tool-calling over a sandbox. The agent gets two tools. `run_sql` runs a read-only SELECT through the same safety layer; `run_python` runs a short snippet in a restricted AST sandbox. It has to *compute* the figure by calling them. Every number in the final answer must appear in an executed tool result, and if it doesn't, the answer comes back flagged `grounded=False`. The executed SQL and the executed code travel with the answer, and so do the source rows.

The sandbox works off an allow-list. The snippet is parsed to an AST, and the whitelist rejects `import`, attribute access (which closes the usual `__class__`/`__globals__` route), `lambda`, `for`/`while` loops, and calls to anything but a fixed set of safe builtins, all before a line runs. Execution happens under `{"__builtins__": {}}`, with a wall-clock timeout as a backstop. It's a pure function, with its own tests in `tests/test_sandbox.py`. It's an allow-list, not a security boundary: I wouldn't run untrusted user code behind it.

### Offline demo (no API key, no download)

A tiny synthetic dataset ships in `sample_data/`, so the whole thing runs with a deterministic scripted driver:

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
# download the Olist CSVs into data/ (see data/README.md)
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

Brazilian E-Commerce Public Dataset by Olist (public, ~100k orders). Not committed to the repo; see [data/README.md](data/README.md).
