"""Console table rendering."""

from __future__ import annotations

from typing import Any


def pretty_print(columns: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    if not columns:
        return "(empty table)"

    formatted_rows = [[_cell(row.get(column, "")) for column in columns] for row in rows]
    widths = [
        max(len(column), *(len(row[index]) for row in formatted_rows)) if formatted_rows else len(column)
        for index, column in enumerate(columns)
    ]

    header = " | ".join(column.ljust(widths[index]) for index, column in enumerate(columns))
    separator = "-+-".join("-" * width for width in widths)
    body = [
        " | ".join(row[index].ljust(widths[index]) for index in range(len(columns)))
        for row in formatted_rows
    ]
    return "\n".join([header, separator, *body])


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
