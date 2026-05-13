"""Lazy logical table plans.

The Table class never stores data rows. It stores an immutable relational plan,
schema information, and metadata-column declarations produced by tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from daquva.ast_nodes import Condition


DUPLICATE_METADATA_COLUMNS = (
    "duplicate_group_id",
    "similarity_score",
    "canonical_candidate",
    "matched_with",
)


TYPO_METADATA_COLUMNS = ("typo_suspect", "typo_suggestion", "typo_distance")


@dataclass(frozen=True)
class SourcePlan:
    connection_name: str
    table_name: str
    selected_columns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectPlan:
    source: "LogicalPlan"
    columns: tuple[str, ...]


@dataclass(frozen=True)
class FilterPlan:
    source: "LogicalPlan"
    condition: Condition


@dataclass(frozen=True)
class ToolPlan:
    source: "LogicalPlan"
    tool: str
    params: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DuplicateDetectionPlan:
    source: "LogicalPlan"
    columns: tuple[str, ...]
    tool: str
    params: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MergePlan:
    source: "LogicalPlan"
    duplicate_metadata_columns: tuple[str, ...] = DUPLICATE_METADATA_COLUMNS


@dataclass(frozen=True)
class AddRowsPlan:
    source: "LogicalPlan"
    columns: tuple[str, ...]
    values: tuple[Any, ...]


@dataclass(frozen=True)
class AddColumnsPlan:
    source: "LogicalPlan"
    columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EditRowsPlan:
    source: "LogicalPlan"
    condition: Condition
    assignments: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class RenameColumnPlan:
    source: "LogicalPlan"
    old_name: str
    new_name: str


@dataclass(frozen=True)
class DeleteColumnsPlan:
    source: "LogicalPlan"
    columns: tuple[str, ...]


@dataclass(frozen=True)
class DeleteRowsPlan:
    source: "LogicalPlan"
    condition: Condition


LogicalPlan = (
    SourcePlan
    | ProjectPlan
    | FilterPlan
    | ToolPlan
    | DuplicateDetectionPlan
    | MergePlan
    | AddRowsPlan
    | AddColumnsPlan
    | EditRowsPlan
    | RenameColumnPlan
    | DeleteColumnsPlan
    | DeleteRowsPlan
)


@dataclass(frozen=True)
class Table:
    plan: LogicalPlan
    schema: tuple[str, ...]
    metadata_columns: tuple[str, ...] = field(default_factory=tuple)
    kind: str = "table"
    analysis: dict[str, Any] = field(default_factory=dict)

    @property
    def columns(self) -> tuple[str, ...]:
        return _unique(self.schema + self.metadata_columns)

    def project(self, columns: tuple[str, ...]) -> "Table":
        self._require_columns(columns)
        return Table(ProjectPlan(self.plan, columns), columns, (), self.kind, dict(self.analysis))

    def filter(self, condition: Condition) -> "Table":
        return replace(self, plan=FilterPlan(self.plan, condition))

    def with_tool(self, tool: str, params: tuple[Any, ...]) -> "Table":
        new_metadata = self.metadata_columns + _metadata_for_tool(tool)
        return Table(
            ToolPlan(self.plan, tool, params),
            self.schema,
            _unique(new_metadata),
            self.kind,
            dict(self.analysis),
        )

    def find_duplicates(
        self, columns: tuple[str, ...], tool: str, params: tuple[Any, ...]
    ) -> "Table":
        self._require_columns(columns)
        metadata = _unique(self.metadata_columns + DUPLICATE_METADATA_COLUMNS)
        analysis = dict(self.analysis)
        analysis["duplicate_columns"] = columns
        analysis["duplicate_tool"] = tool
        analysis["duplicate_metadata_columns"] = DUPLICATE_METADATA_COLUMNS
        return Table(
            DuplicateDetectionPlan(self.plan, columns, tool, params),
            self.schema,
            metadata,
            "duplicate_analysis",
            analysis,
        )

    def merge_duplicates(self) -> "Table":
        if self.kind != "duplicate_analysis":
            raise ValueError("merge is only valid for tables produced by find_duplicates")
        duplicate_metadata = tuple(self.analysis.get("duplicate_metadata_columns", DUPLICATE_METADATA_COLUMNS))
        preserved_metadata = tuple(c for c in self.metadata_columns if c not in duplicate_metadata)
        schema = _unique(self.schema + preserved_metadata + ("merged_from_count",))
        return Table(
            MergePlan(self.plan, duplicate_metadata),
            schema,
            (),
            "table",
            {"merged_from": self.analysis},
        )

    def add_rows(self, values: tuple[Any, ...]) -> "Table":
        if len(values) != len(self.schema):
            raise ValueError(
                f"add_rows expected {len(self.schema)} values for columns {self.schema}, got {len(values)}"
            )
        return replace(self, plan=AddRowsPlan(self.plan, self.schema, values))

    def add_columns(self, columns: tuple[tuple[str, str], ...]) -> "Table":
        names = tuple(name for name, _ in columns)
        return Table(
            AddColumnsPlan(self.plan, columns),
            _unique(self.schema + names),
            self.metadata_columns,
            self.kind,
            dict(self.analysis),
        )

    def edit_rows(self, condition: Condition, assignments: tuple[tuple[str, Any], ...]) -> "Table":
        assignment_columns = tuple(column for column, _ in assignments)
        self._require_columns(assignment_columns)
        return replace(self, plan=EditRowsPlan(self.plan, condition, assignments))

    def rename_column(self, old_name: str, new_name: str) -> "Table":
        self._require_columns((old_name,))
        schema = tuple(new_name if column == old_name else column for column in self.schema)
        metadata = tuple(new_name if column == old_name else column for column in self.metadata_columns)
        return Table(RenameColumnPlan(self.plan, old_name, new_name), schema, metadata, self.kind, dict(self.analysis))

    def delete_columns(self, columns: tuple[str, ...]) -> "Table":
        self._require_columns(columns)
        schema = tuple(column for column in self.schema if column not in columns)
        metadata = tuple(column for column in self.metadata_columns if column not in columns)
        return Table(DeleteColumnsPlan(self.plan, columns), schema, metadata, self.kind, dict(self.analysis))

    def delete_rows(self, condition: Condition) -> "Table":
        return replace(self, plan=DeleteRowsPlan(self.plan, condition))

    def _require_columns(self, columns: tuple[str, ...]) -> None:
        missing = [column for column in columns if column not in self.columns]
        if missing:
            raise ValueError(f"Unknown column(s): {', '.join(missing)}")


def _metadata_for_tool(tool: str) -> tuple[str, ...]:
    if tool == "row_counter":
        return ("row_number", "total_rows")
    if tool == "name_counter":
        return ("name_count",)
    if tool == "typo_detector":
        return TYPO_METADATA_COLUMNS
    return ()


def _unique(columns: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for column in columns:
        if column not in seen:
            seen.add(column)
            result.append(column)
    return tuple(result)
