# Demo 05: SQLite Output

This demo reads from a real SQLite input database, pushes the simple salary filter down to SQL, then writes transformed results to both CSV and SQLite output.

Run it with:

```bash
uv run python -m daquva demo/demo_05_sqlite_output/sqlite_output.dqv
```

Generated outputs:

- `output/senior_employees.csv`
- `output/sqlite_output.sqlite`, table `senior_employees`

The output database is separate from the input database.
