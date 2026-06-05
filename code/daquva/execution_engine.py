"""Hybrid execution engine for DaQuVa logical plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from daquva.ast_nodes import Condition, CompoundCondition, Literal
from daquva.connections.csv_connection import CSVConnection
from daquva.connections.sqlite_connection import SQLiteConnection
from daquva.table import (
    AddColumnsPlan,
    AddRowsPlan,
    DeleteColumnsPlan,
    DeleteRowsPlan,
    DuplicateDetectionPlan,
    EditRowsPlan,
    FilterPlan,
    LimitPlan,
    LogicalPlan,
    MergePlan,
    ProjectPlan,
    RenameColumnPlan,
    SortPlan,
    SourcePlan,
    Table,
    ToolPlan,
)
from daquva.tools.fuzzy_duplicates import annotate_duplicates, merge_duplicate_rows
from daquva.tools.typo_detector import annotate_typos, choose_typo_column


@dataclass(frozen=True)
class MaterializedTable:
    columns: tuple[str, ...]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class _SQLQuery:
    connection: SQLiteConnection
    table_name: str
    columns: tuple[str, ...]
    conditions: tuple[str, ...]
    params: tuple[Any, ...]
    order_by: str | None = None
    order_desc: bool = False
    limit: int | None = None


class ExecutionEngine:
    def __init__(self, connections: dict[str, CSVConnection | SQLiteConnection]):
        self.connections = connections

    def materialize(self, table: Table) -> MaterializedTable:
        rows = self._execute(table.plan)
        columns = table.columns
        normalized_rows = [_order_row(row, columns) for row in rows]
        return MaterializedTable(columns, normalized_rows)

    def _execute(self, plan: LogicalPlan) -> list[dict[str, Any]]:
        sql_query = self._compile_sql(plan)
        if sql_query is not None:
            return self._run_sql(sql_query)

        if isinstance(plan, SourcePlan):
            connection = self.connections[plan.connection_name]
            if isinstance(connection, CSVConnection):
                return connection.fetch_rows(plan.table_name, plan.selected_columns)
            if isinstance(connection, SQLiteConnection):
                return connection.fetch_rows(plan.table_name, plan.selected_columns)

        if isinstance(plan, ProjectPlan):
            rows = self._execute(plan.source)
            return [{column: row.get(column, "") for column in plan.columns} for row in rows]

        if isinstance(plan, FilterPlan):
            rows = self._execute(plan.source)
            return [row for row in rows if _matches(row, plan.condition)]

        if isinstance(plan, ToolPlan):
            return self._execute_tool(plan)

        if isinstance(plan, DuplicateDetectionPlan):
            rows = self._execute(plan.source)
            threshold = _first_int_param(plan.params, default=2)
            if plan.tool not in {"fuzzy_duplicates", "levenshtein_matcher"}:
                raise ValueError(f"Unknown duplicate tool {plan.tool!r}")
            return annotate_duplicates(rows, plan.columns, max_distance=threshold)

        if isinstance(plan, MergePlan):
            rows = self._execute(plan.source)
            ordered_columns = _columns_from_rows(rows)
            return merge_duplicate_rows(rows, ordered_columns, plan.duplicate_metadata_columns)

        if isinstance(plan, AddRowsPlan):
            rows = self._execute(plan.source)
            rows.append(dict(zip(plan.columns, plan.values, strict=True)))
            return rows

        if isinstance(plan, AddColumnsPlan):
            rows = self._execute(plan.source)
            for row in rows:
                for column, _ in plan.columns:
                    row[column] = ""
            return rows

        if isinstance(plan, EditRowsPlan):
            rows = self._execute(plan.source)
            for row in rows:
                if _matches(row, plan.condition):
                    for column, value in plan.assignments:
                        row[column] = value
            return rows

        if isinstance(plan, RenameColumnPlan):
            rows = self._execute(plan.source)
            renamed_rows: list[dict[str, Any]] = []
            for row in rows:
                renamed = {}
                for column, value in row.items():
                    renamed[plan.new_name if column == plan.old_name else column] = value
                renamed_rows.append(renamed)
            return renamed_rows

        if isinstance(plan, DeleteColumnsPlan):
            rows = self._execute(plan.source)
            return [
                {column: value for column, value in row.items() if column not in plan.columns}
                for row in rows
            ]

        if isinstance(plan, DeleteRowsPlan):
            rows = self._execute(plan.source)
            return [row for row in rows if not _matches(row, plan.condition)]

        if isinstance(plan, SortPlan):
            rows = self._execute(plan.source)
            return sorted(rows, key=lambda r: _sort_key(r.get(plan.column)), reverse=not plan.ascending)

        if isinstance(plan, LimitPlan):
            rows = self._execute(plan.source)
            return rows[:plan.count]

        raise TypeError(f"Unsupported logical plan: {type(plan).__name__}")

    def _execute_tool(self, plan: ToolPlan) -> list[dict[str, Any]]:
        rows = self._execute(plan.source)
        if plan.tool == "row_counter":
            total = len(rows)
            return [
                {**row, "row_number": index, "total_rows": total}
                for index, row in enumerate(rows, start=1)
            ]

        if plan.tool == "name_counter":
            column = str(plan.params[0]) if plan.params else "name"
            counts: dict[Any, int] = {}
            for row in rows:
                value = row.get(column, "")
                counts[value] = counts.get(value, 0) + 1
            return [{**row, "name_count": counts.get(row.get(column, ""), 0)} for row in rows]

        if plan.tool == "typo_detector":
            columns = _columns_from_rows(rows)
            if not columns:
                return rows
            column = choose_typo_column(columns, plan.params)
            return annotate_typos(rows, column, _first_int_param(plan.params[1:], default=2))

        raise ValueError(f"Unknown scan tool {plan.tool!r}")

    def _compile_sql(self, plan: LogicalPlan) -> _SQLQuery | None:
        if isinstance(plan, SourcePlan):
            connection = self.connections[plan.connection_name]
            if not isinstance(connection, SQLiteConnection):
                return None
            return _SQLQuery(connection, plan.table_name, plan.selected_columns, (), ())

        if isinstance(plan, ProjectPlan):
            compiled = self._compile_sql(plan.source)
            if compiled is None:
                return None
            return _SQLQuery(
                compiled.connection,
                compiled.table_name,
                plan.columns,
                compiled.conditions,
                compiled.params,
                compiled.order_by,
                compiled.order_desc,
                compiled.limit,
            )

        if isinstance(plan, FilterPlan):
            compiled = self._compile_sql(plan.source)
            if compiled is None:
                return None
            condition_sql, params = _sql_condition(plan.condition)
            return _SQLQuery(
                compiled.connection,
                compiled.table_name,
                compiled.columns,
                compiled.conditions + (condition_sql,),
                compiled.params + params,
                compiled.order_by,
                compiled.order_desc,
                compiled.limit,
            )

        if isinstance(plan, SortPlan):
            compiled = self._compile_sql(plan.source)
            if compiled is None:
                return None
            return _SQLQuery(
                compiled.connection,
                compiled.table_name,
                compiled.columns,
                compiled.conditions,
                compiled.params,
                plan.column,
                not plan.ascending,
                compiled.limit,
            )

        if isinstance(plan, LimitPlan):
            compiled = self._compile_sql(plan.source)
            if compiled is None:
                return None
            return _SQLQuery(
                compiled.connection,
                compiled.table_name,
                compiled.columns,
                compiled.conditions,
                compiled.params,
                compiled.order_by,
                compiled.order_desc,
                plan.count,
            )

        return None

    def _run_sql(self, query: _SQLQuery) -> list[dict[str, Any]]:
        selected_columns = (
            ", ".join(_quote_identifier(column) for column in query.columns) if query.columns else "*"
        )
        sql = f"SELECT {selected_columns} FROM {_quote_identifier(query.table_name)}"
        if query.conditions:
            sql += " WHERE " + " AND ".join(query.conditions)
        if query.order_by:
            direction = "DESC" if query.order_desc else "ASC"
            sql += f" ORDER BY {_quote_identifier(query.order_by)} {direction}"
        if query.limit is not None:
            sql += f" LIMIT {query.limit}"
        return query.connection.execute_query(sql, query.params)


def _matches(row: dict[str, Any], condition: Condition | CompoundCondition) -> bool:
    if isinstance(condition, CompoundCondition):
        left_result = _matches(row, condition.left)
        if condition.operator == "AND":
            return left_result and _matches(row, condition.right)
        if condition.operator == "OR":
            return left_result or _matches(row, condition.right)
        raise ValueError(f"Unknown logical operator {condition.operator!r}")

    if condition.column not in row:
        available = ", ".join(sorted(row.keys()))
        raise ValueError(
            f"Condition references column {condition.column!r} which does not exist. "
            f"Available columns: {available}"
        )
    left = row[condition.column]
    right = _literal_value(condition.value)

    if condition.operator == "starts_with":
        return (str(left) if left is not None else "").startswith(str(right))
    if condition.operator == "ends_with":
        return (str(left) if left is not None else "").endswith(str(right))
    if condition.operator == "contains":
        return str(right) in (str(left) if left is not None else "")
    if condition.operator == "==":
        return _comparable(left) == _comparable(right)
    if condition.operator == "!=":
        return _comparable(left) != _comparable(right)
    try:
        if condition.operator == ">":
            return _comparable(left) > _comparable(right)
        if condition.operator == "<":
            return _comparable(left) < _comparable(right)
        if condition.operator == ">=":
            return _comparable(left) >= _comparable(right)
        if condition.operator == "<=":
            return _comparable(left) <= _comparable(right)
    except TypeError:
        raise ValueError(
            f"Cannot compare column {condition.column!r} (value {left!r}, type {type(left).__name__}) "
            f"with {right!r} ({type(right).__name__}) using {condition.operator!r}"
        )
    raise ValueError(f"Unknown filter operator {condition.operator!r}")


def _sql_condition(condition: Condition | CompoundCondition) -> tuple[str, tuple[Any, ...]]:
    if isinstance(condition, CompoundCondition):
        left_sql, left_params = _sql_condition(condition.left)
        right_sql, right_params = _sql_condition(condition.right)
        return f"({left_sql} {condition.operator} {right_sql})", left_params + right_params

    value = _literal_value(condition.value)
    column = _quote_identifier(condition.column)
    if condition.operator == "starts_with":
        return f"{column} LIKE ?", (f"{value}%",)
    if condition.operator == "ends_with":
        return f"{column} LIKE ?", (f"%{value}",)
    if condition.operator == "contains":
        return f"{column} LIKE ?", (f"%{value}%",)
    if condition.operator == "==":
        return f"{column} = ?", (value,)
    if condition.operator == "!=":
        return f"{column} != ?", (value,)
    if condition.operator in {">", "<", ">=", "<="}:
        return f"{column} {condition.operator} ?", (value,)
    raise ValueError(f"Unsupported SQL condition operator {condition.operator!r}")


def _literal_value(value: Any) -> Any:
    if isinstance(value, Literal):
        return value.value
    return value


def _comparable(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text.casefold()
    return value


def _first_int_param(params: tuple[Any, ...], default: int) -> int:
    for param in params:
        if isinstance(param, bool):
            continue
        if isinstance(param, int):
            return param
        if isinstance(param, float):
            return int(param)
        if isinstance(param, str) and param.isdigit():
            return int(param)
    return default


def _columns_from_rows(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    return tuple(columns)


def _order_row(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: row.get(column, "") for column in columns}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sort_key(value: Any) -> tuple:
    """Return a (type_rank, value) tuple so mixed-type columns sort without TypeError."""
    if value is None or value == "":
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (1, value)
    return (2, str(value).casefold())
