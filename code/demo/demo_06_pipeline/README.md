# Demo 06: Pipeline

This demo chains several lazy operations:

- CSV scan
- typo metadata generation on `email`
- adult filtering
- fuzzy duplicate detection on `name`
- duplicate-aware merge
- CSV and SQLite materialization

Run it with:

```bash
uv run python -m daquva demo/demo_06_pipeline/pipeline.dqv
```

Generated outputs:

- `output/typo_analysis.csv`
- `output/duplicate_analysis.csv`
- `output/pipeline_cleaned.csv`
- `output/pipeline.sqlite`, table `cleaned_leads`

The pipeline remains a logical plan until the final output and save statements.
