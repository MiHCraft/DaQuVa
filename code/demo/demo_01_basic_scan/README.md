# Demo 01: Basic Scan

This demo scans a CSV file lazily and attaches row-counter metadata with `using_tool row_counter`.

Run it with:

```bash
uv run python -m daquva demo/demo_01_basic_scan/basic_scan.dqv
```

Generated outputs:

- `output/scanned_people.csv`
- `output/basic_scan.sqlite`, table `scanned_people`

The source CSV is not loaded into memory by the table variable. The rows are fetched only when the file output and SQLite save are requested.
