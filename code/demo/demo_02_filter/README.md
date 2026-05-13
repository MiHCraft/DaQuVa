# Demo 02: Filter

This demo filters CSV rows with a relational predicate:

```dqv
adults = filter people where age >= 18;
```

Run it with:

```bash
uv run python -m daquva demo/demo_02_filter/filter.dqv
```

Generated outputs:

- `output/adults.csv`
- `output/filter.sqlite`, table `adults`

The `people` and `adults` variables are lazy logical plans. The filtered rows are materialized only at output/save time.
