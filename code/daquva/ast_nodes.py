"""AST nodes for the DaQuVa parser.

The parser only builds these structures. Runtime objects such as database
connections and materialized rows live in other modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Literal:
    value: Any


@dataclass(frozen=True)
class VariableReference:
    name: str


ValueNode = Literal | VariableReference


@dataclass(frozen=True)
class ConnectionDecl:
    kind: str
    name: str
    path: str


@dataclass(frozen=True)
class TableReference:
    name: str
    connection: str | None = None
    columns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_external(self) -> bool:
        return self.connection is not None

    def display_name(self) -> str:
        if self.connection:
            base = f"{self.connection}.{self.name}"
        else:
            base = self.name
        if self.columns:
            return f"{base}[{', '.join(self.columns)}]"
        return base


@dataclass(frozen=True)
class Condition:
    column: str
    operator: str
    value: ValueNode


@dataclass(frozen=True)
class Program:
    connections: tuple[ConnectionDecl, ...]
    statements: tuple[Any, ...]


@dataclass(frozen=True)
class Assignment:
    target: str
    expression: Any


@dataclass(frozen=True)
class ScanExpression:
    source: TableReference
    tool: str | None = None
    tool_params: tuple[ValueNode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FilterExpression:
    source: TableReference
    condition: Condition


@dataclass(frozen=True)
class FindDuplicatesExpression:
    source: TableReference
    tool: str
    params: tuple[ValueNode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MergeExpression:
    source_name: str


@dataclass(frozen=True)
class AddRowsExpression:
    source_name: str
    values: tuple[ValueNode, ...]


@dataclass(frozen=True)
class AddColumnsExpression:
    source_name: str
    columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EditRowsExpression:
    source_name: str
    condition: Condition
    assignments: tuple[tuple[str, ValueNode], ...]


@dataclass(frozen=True)
class RenameColumnExpression:
    source_name: str
    old_name: str
    new_name: str


@dataclass(frozen=True)
class DeleteColumnsExpression:
    source_name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class DeleteRowsExpression:
    source_name: str
    condition: Condition


@dataclass(frozen=True)
class OutputDestination:
    kind: str
    target: str | None = None


@dataclass(frozen=True)
class OutputStatement:
    value: ValueNode
    destination: OutputDestination


@dataclass(frozen=True)
class SaveStatement:
    source: TableReference
    table_name: str
    allow_danger: bool = False


@dataclass(frozen=True)
class FunctionDefinition:
    name: str
    params: tuple[str, ...]
    body: tuple[Any, ...]


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: tuple[ValueNode, ...]


@dataclass(frozen=True)
class ReturnStatement:
    value: ValueNode
