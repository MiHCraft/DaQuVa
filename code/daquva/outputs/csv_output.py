"""CSV output writer."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _format_cell(row.get(column, "")) for column in columns})


def _format_cell(value: Any) -> Any:
    if value is None:
        return ""
    return value
