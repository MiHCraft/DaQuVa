"""SQLite backend for DaQuVa."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SQLiteConnection:
    kind = "sqlite"

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def get_schema(self, table_name: str) -> tuple[str, ...]:
        rows = self.connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
        columns = tuple(str(row["name"]) for row in rows)
        if not columns:
            raise ValueError(f"SQLite table {table_name!r} does not exist in {self.path}")
        return columns

    def fetch_rows(self, table_name: str, columns: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        selected = ", ".join(_quote_identifier(column) for column in columns) if columns else "*"
        cursor = self.connection.execute(f"SELECT {selected} FROM {_quote_identifier(table_name)}")
        return [dict(row) for row in cursor.fetchall()]

    def execute_query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        cursor = self.connection.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def table_exists(self, table_name: str) -> bool:
        row = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def write_table(
        self,
        table_name: str,
        columns: tuple[str, ...],
        rows: list[dict[str, Any]],
        allow_danger: bool,
    ) -> None:
        if self.table_exists(table_name):
            if not allow_danger:
                raise ValueError(
                    f"Refusing to overwrite existing SQLite table {table_name!r}. "
                    "Use allowDanger if this destructive overwrite is intended."
                )
            self.connection.execute(f"DROP TABLE {_quote_identifier(table_name)}")

        if not columns:
            raise ValueError("Cannot save an empty table without schema information")

        column_defs = ", ".join(
            f"{_quote_identifier(column)} {_sqlite_type_for_column(rows, column)}" for column in columns
        )
        self.connection.execute(f"CREATE TABLE {_quote_identifier(table_name)} ({column_defs})")

        placeholders = ", ".join("?" for _ in columns)
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        sql = f"INSERT INTO {_quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})"
        values = [tuple(row.get(column) for column in columns) for row in rows]
        self.connection.executemany(sql, values)
        self.connection.commit()
def _sqlite_type_for_column(rows: list[dict[str, Any]], column: str) -> str:
    values = [row.get(column) for row in rows if row.get(column) not in (None, "")]
    if values and all(isinstance(value, bool) for value in values):
        return "INTEGER"
    if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return "INTEGER"
    if values and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return "REAL"
    return "TEXT"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
