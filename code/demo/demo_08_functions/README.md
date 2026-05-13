# Demo 08: Functions

This demo shows MVP function support.

`make_adults(source_table, min_age)` receives:
- a table variable (lazy logical plan)
- a scalar parameter

It returns a new table plan:

```dqv
adults = filter source_table where age >= min_age;
return adults;
```

Run it with:

```bash
uv run python -m daquva demo/demo_08_functions/functions_pipeline.dqv
```

Generated outputs:

- `output/adults_via_function.csv`
- `output/functions.sqlite`, table `adults_via_function`
