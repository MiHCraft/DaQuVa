# Demo 07: Multiple Sources

This demo uses a CSV source and a SQLite source in one DaQuVa program. It does not join them; joins are intentionally future work.

Run it with:

```bash
uv run python -m daquva demo/demo_07_multiple_sources/multiple_sources.dqv
```

Generated outputs:

- `output/moldova_customers.csv`
- `output/large_orders.csv`
- `output/multiple_sources.sqlite`, tables `moldova_customers` and `large_orders`

The demo shows that one runtime can manage several lazy table plans from different backends.
