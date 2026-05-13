"""CSV backend for DaQuVa."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class CSVConnection:
    kind = "csv"

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path

    def get_schema(self, table_name: str | None = None) -> tuple[str, ...]:
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"CSV file {self.path} does not have a header row")
            return tuple(reader.fieldnames)

    def fetch_rows(
        self, table_name: str | None = None, columns: tuple[str, ...] = ()
    ) -> list[dict[str, Any]]:
        schema = self.get_schema(table_name)
        selected_columns = columns or schema
        missing = [column for column in selected_columns if column not in schema]
        if missing:
            raise ValueError(f"CSV {self.path} has no column(s): {', '.join(missing)}")

        with self.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for row in reader:
                rows.append({column: _parse_cell(row[column]) for column in selected_columns})
            return rows


def _parse_cell(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        if "." not in text:
            return int(text)
        return float(text)
    except ValueError:
        return value
