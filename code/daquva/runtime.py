"""Runtime orchestration for DaQuVa AST execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from daquva.ast_nodes import (
    AddColumnsExpression,
    AddRowsExpression,
    Assignment,
    Condition,
    ConnectionDecl,
    DeleteColumnsExpression,
    DeleteRowsExpression,
    EditRowsExpression,
    FilterExpression,
    FindDuplicatesExpression,
    Literal,
    MergeExpression,
    OutputStatement,
    Program,
    RenameColumnExpression,
    SaveStatement,
    ScanExpression,
    TableReference,
    ValueNode,
    VariableReference,
)
from daquva.connections.csv_connection import CSVConnection
from daquva.connections.sqlite_connection import SQLiteConnection
from daquva.execution_engine import ExecutionEngine
from daquva.outputs.csv_output import write_csv
from daquva.outputs.sqlite_output import write_sqlite
from daquva.table import SourcePlan, Table
from daquva.utils.pretty_print import pretty_print


class Runtime:
    def __init__(self, base_path: Path | str | None = None):
        self.base_path = Path(base_path or ".").resolve()
        self.connections: dict[str, CSVConnection | SQLiteConnection] = {}
        self.memory: dict[str, Any] = {}
        self.engine = ExecutionEngine(self.connections)

    def run(self, program: Program) -> None:
        for connection in program.connections:
            self._register_connection(connection)

        for statement in program.statements:
            self._execute_statement(statement)

    def _register_connection(self, declaration: ConnectionDecl) -> None:
        path = self._resolve_path(declaration.path)
        if declaration.kind == "sqlite":
            self.connections[declaration.name] = SQLiteConnection(declaration.name, path)
            return
        if declaration.kind == "csv":
            self.connections[declaration.name] = CSVConnection(declaration.name, path)
            return
        raise ValueError(f"Unknown connection type {declaration.kind!r}")

    def _execute_statement(self, statement: object) -> None:
        if isinstance(statement, Assignment):
            self.memory[statement.target] = self._evaluate(statement.expression)
            return

        if isinstance(statement, OutputStatement):
            self._execute_output(statement)
            return

        if isinstance(statement, SaveStatement):
            self._execute_save(statement)
            return

        self._evaluate(statement)

    def _evaluate(self, expression: object) -> Any:
        if isinstance(expression, Literal):
            return expression.value

        if isinstance(expression, VariableReference):
            if expression.name not in self.memory:
                raise ValueError(f"Unknown variable {expression.name!r}")
            return self.memory[expression.name]

        if isinstance(expression, ScanExpression):
            table = self._resolve_table_reference(expression.source)
            params = self._resolve_values(expression.tool_params)
            if expression.tool:
                return table.with_tool(expression.tool, params)
            return table

        if isinstance(expression, FilterExpression):
            table = self._resolve_table_reference(expression.source)
            return table.filter(self._resolve_condition(expression.condition))

        if isinstance(expression, FindDuplicatesExpression):
            table = self._resolve_table_reference(expression.source, project_selected_columns=False)
            columns = expression.source.columns or _default_duplicate_columns(table)
            params = self._resolve_values(expression.params)
            return table.find_duplicates(columns, expression.tool, params)

        if isinstance(expression, MergeExpression):
            source = self.memory.get(expression.source_name)
            if not isinstance(source, Table):
                raise ValueError(f"merge expected duplicate-analysis table variable {expression.source_name!r}")
            return source.merge_duplicates()

        if isinstance(expression, AddRowsExpression):
            table = self._expect_table_variable(expression.source_name)
            return table.add_rows(self._resolve_values(expression.values))

        if isinstance(expression, AddColumnsExpression):
            table = self._expect_table_variable(expression.source_name)
            return table.add_columns(expression.columns)

        if isinstance(expression, EditRowsExpression):
            table = self._expect_table_variable(expression.source_name)
            assignments = tuple((column, self._resolve_value(value)) for column, value in expression.assignments)
            return table.edit_rows(self._resolve_condition(expression.condition), assignments)

        if isinstance(expression, RenameColumnExpression):
            table = self._expect_table_variable(expression.source_name)
            return table.rename_column(expression.old_name, expression.new_name)

        if isinstance(expression, DeleteColumnsExpression):
            table = self._expect_table_variable(expression.source_name)
            return table.delete_columns(expression.columns)

        if isinstance(expression, DeleteRowsExpression):
            table = self._expect_table_variable(expression.source_name)
            return table.delete_rows(self._resolve_condition(expression.condition))

        raise TypeError(f"Unsupported AST node: {type(expression).__name__}")

    def _execute_output(self, statement: OutputStatement) -> None:
        value = self._resolve_value(statement.value)
        destination = statement.destination

        if destination.kind == "console":
            if isinstance(value, Table):
                materialized = self.engine.materialize(value)
                print(pretty_print(materialized.columns, materialized.rows))
            else:
                print(value)
            return

        if not isinstance(value, Table):
            raise ValueError(f"Output destination {destination.kind!r} expects a table")

        materialized = self.engine.materialize(value)
        if destination.kind == "file":
            if destination.target is None:
                raise ValueError("File output requires a path")
            write_csv(self._resolve_path(destination.target), materialized.columns, materialized.rows)
            return

        if destination.kind == "database":
            if destination.target is None:
                raise ValueError("Database output requires a connection name")
            connection = self._sqlite_connection(destination.target)
            table_name = self._output_table_name(statement.value)
            write_sqlite(connection, table_name, materialized.columns, materialized.rows, allow_danger=True)
            return

        raise ValueError(f"Unknown output destination {destination.kind!r}")

    def _execute_save(self, statement: SaveStatement) -> None:
        table = self._resolve_table_reference(statement.source)
        materialized = self.engine.materialize(table)
        connection = self._default_output_sqlite_connection()
        write_sqlite(
            connection,
            statement.table_name,
            materialized.columns,
            materialized.rows,
            statement.allow_danger,
        )

    def _resolve_table_reference(
        self, reference: TableReference, project_selected_columns: bool = True
    ) -> Table:
        if reference.connection:
            connection = self.connections.get(reference.connection)
            if connection is None:
                raise ValueError(f"Unknown connection {reference.connection!r}")
            full_schema = connection.get_schema(reference.name)
            selected_columns = reference.columns if project_selected_columns else ()
            if selected_columns:
                _require_columns(full_schema, selected_columns)
            schema = selected_columns or full_schema
            return Table(SourcePlan(reference.connection, reference.name, selected_columns), schema)

        value = self.memory.get(reference.name)
        if not isinstance(value, Table):
            raise ValueError(f"Unknown table variable {reference.name!r}")
        if reference.columns and project_selected_columns:
            return value.project(reference.columns)
        return value

    def _expect_table_variable(self, name: str) -> Table:
        value = self.memory.get(name)
        if not isinstance(value, Table):
            raise ValueError(f"Unknown table variable {name!r}")
        return value

    def _resolve_condition(self, condition: Condition) -> Condition:
        return Condition(condition.column, condition.operator, Literal(self._resolve_value(condition.value)))

    def _resolve_values(self, values: tuple[ValueNode, ...]) -> tuple[Any, ...]:
        return tuple(self._resolve_value(value) for value in values)

    def _resolve_value(self, value: ValueNode | Any) -> Any:
        if isinstance(value, Literal):
            return value.value
        if isinstance(value, VariableReference):
            if value.name not in self.memory:
                raise ValueError(f"Unknown variable {value.name!r}")
            return self.memory[value.name]
        return value

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.base_path / candidate

    def _sqlite_connection(self, name: str) -> SQLiteConnection:
        connection = self.connections.get(name)
        if not isinstance(connection, SQLiteConnection):
            raise ValueError(f"Connection {name!r} is not a SQLite connection")
        return connection

    def _default_output_sqlite_connection(self) -> SQLiteConnection:
        sqlite_connections = [
            connection for connection in self.connections.values() if isinstance(connection, SQLiteConnection)
        ]
        if not sqlite_connections:
            raise ValueError("Saving requires at least one sqlite connection")
        for preferred in ("out", "output"):
            connection = self.connections.get(preferred)
            if isinstance(connection, SQLiteConnection):
                return connection
        return sqlite_connections[-1]

    def _output_table_name(self, value: ValueNode) -> str:
        if isinstance(value, VariableReference):
            return value.name
        return "output"


def _default_duplicate_columns(table: Table) -> tuple[str, ...]:
    for preferred in ("name", "email"):
        if preferred in table.columns:
            return (preferred,)
    if not table.columns:
        raise ValueError("find_duplicates needs at least one column")
    return (table.columns[0],)


def _require_columns(schema: tuple[str, ...], columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in schema]
    if missing:
        raise ValueError(f"Unknown column(s): {', '.join(missing)}")
