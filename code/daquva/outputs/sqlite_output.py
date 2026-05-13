"""SQLite output writer."""

from __future__ import annotations

from typing import Any

from daquva.connections.sqlite_connection import SQLiteConnection


def write_sqlite(
    connection: SQLiteConnection,
    table_name: str,
    columns: tuple[str, ...],
    rows: list[dict[str, Any]],
    allow_danger: bool,
) -> None:
    ordered_rows = [{column: row.get(column) for column in columns} for row in rows]
    connection.write_table(table_name, columns, ordered_rows, allow_danger)
