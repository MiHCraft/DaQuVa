# Demo 03: Duplicate Detection

This demo runs fuzzy duplicate detection on the `name` column and then merges the duplicate-analysis result.

Run it with:

```bash
uv run python -m daquva demo/demo_03_duplicates/duplicates.dqv
```

Generated outputs:

- `output/duplicate_analysis.csv`, including logical metadata columns such as `duplicate_group_id`
- `output/merged_people.csv`
- `output/duplicates.sqlite`, table `merged_people`

`merge` is valid here because `dupes` was produced by `find_duplicates`. Calling `merge people;` would raise a semantic runtime error.
