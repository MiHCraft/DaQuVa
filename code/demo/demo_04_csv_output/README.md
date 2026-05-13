# Demo 04: CSV Output

This demo proves visible CSV transformation:

- filters active subscriptions
- edits the support inbox row to `internal`
- renames `full_name` to `name`

Run it with:

```bash
uv run python -m daquva demo/demo_04_csv_output/csv_output.dqv
```

Generated outputs:

- `output/cleaned_subscriptions.csv`
- `output/csv_output.sqlite`, table `cleaned_subscriptions`

The output CSV is the main proof artifact for this demo.
