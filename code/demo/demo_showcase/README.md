# Demo Showcase: End-to-End Data Quality Pipeline

This is the headline demo. It exercises every major DaQuVa feature in one
narrative pipeline over a 30-row customer dataset that contains deliberate
near-duplicates and email typos.

Features demonstrated:

- CSV connection and lazy `scan` with `typo_detector` metadata
- compound `AND` / `OR` filters with correct precedence
- string predicates `contains` and `ends_with`
- top-N exploration with `sort` and `limit`
- fuzzy duplicate detection (`find_duplicates`) and duplicate-aware `merge`
- CSV and SQLite materialization
- `summarize` — an aggregate **proof table** that reports before/after row
  counts per stage instead of just appending more columns

Run it with:

```bash
uv run python -m daquva demo/demo_showcase/showcase.dqv
```

Generated outputs:

- `output/duplicates.csv` — duplicate-analysis rows with group metadata
- `output/cleaned_customers.csv` — merged, cleaned customers
- `output/proof_summary.csv` — one metrics row per pipeline stage
- `output/showcase.sqlite` — tables `clean_customers` and `proof_summary`

The proof summary makes the pipeline auditable at a glance. For this dataset it
shows 30 raw rows reduced to 25 paid adults, 10 duplicate groups across 20
candidate rows, and a final 15 merged rows representing all 25 inputs (10 rows
removed by merge).

## Presenting the demo

From the `code/` directory, `present.ps1` walks through the whole pipeline with
a pause before each step (source, tokens, AST, execution, output artifacts, and
an optional REPL session):

```powershell
.\present.ps1
```

The tables remain logical plans until the output, save, and summarize statements
force materialization.
