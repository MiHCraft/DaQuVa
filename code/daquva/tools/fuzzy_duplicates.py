"""Simple fuzzy duplicate detection and duplicate-aware merge helpers."""

from __future__ import annotations

from typing import Any


DUPLICATE_METADATA_COLUMNS = (
    "duplicate_group_id",
    "similarity_score",
    "canonical_candidate",
    "matched_with",
)


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (left_char != right_char)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def annotate_duplicates(
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    max_distance: int = 2,
) -> list[dict[str, Any]]:
    annotated = [dict(row) for row in rows]
    if not annotated:
        return annotated

    keys = [_row_key(row, columns) for row in annotated]
    parent = list(range(len(annotated)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for i, left_key in enumerate(keys):
        for j in range(i + 1, len(keys)):
            if _is_duplicate_key(left_key, keys[j], max_distance):
                union(i, j)

    grouped: dict[int, list[int]] = {}
    for index in range(len(annotated)):
        grouped.setdefault(find(index), []).append(index)

    duplicate_group_number = 1
    for indices in grouped.values():
        if len(indices) == 1:
            row = annotated[indices[0]]
            row["duplicate_group_id"] = ""
            row["similarity_score"] = 1.0
            row["canonical_candidate"] = True
            row["matched_with"] = ""
            continue

        canonical_index = _choose_canonical_row(annotated, indices, columns)
        canonical_key = keys[canonical_index]
        group_id = f"dup-{duplicate_group_number}"
        duplicate_group_number += 1

        for index in indices:
            row = annotated[index]
            row["duplicate_group_id"] = group_id
            row["similarity_score"] = round(_similarity(keys[index], canonical_key), 3)
            row["canonical_candidate"] = index == canonical_index
            row["matched_with"] = "" if index == canonical_index else canonical_key

    return annotated


def merge_duplicate_rows(
    rows: list[dict[str, Any]],
    ordered_columns: tuple[str, ...],
    duplicate_metadata_columns: tuple[str, ...] = DUPLICATE_METADATA_COLUMNS,
) -> list[dict[str, Any]]:
    merged_rows: list[dict[str, Any]] = []
    consumed_groups: set[str] = set()

    data_columns = tuple(column for column in ordered_columns if column not in duplicate_metadata_columns)

    for row in rows:
        group_id = str(row.get("duplicate_group_id") or "")
        if not group_id:
            merged_rows.append(_without_duplicate_metadata(row, data_columns, 1))
            continue

        if group_id in consumed_groups:
            continue
        group = [candidate for candidate in rows if candidate.get("duplicate_group_id") == group_id]
        canonical = next((candidate for candidate in group if candidate.get("canonical_candidate") is True), group[0])
        merged = _without_duplicate_metadata(canonical, data_columns, len(group))

        for candidate in group:
            for column in data_columns:
                if column.startswith("typo_"):
                    continue
                if _is_empty(merged.get(column)) and not _is_empty(candidate.get(column)):
                    merged[column] = candidate.get(column)

        merged_rows.append(merged)
        consumed_groups.add(group_id)

    return merged_rows


def _row_key(row: dict[str, Any], columns: tuple[str, ...]) -> str:
    return " | ".join(normalize(row.get(column, "")) for column in columns)


def normalize(value: Any) -> str:
    return " ".join(str(value).casefold().strip().split())


def _is_duplicate_key(left: str, right: str, max_distance: int) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    distance = levenshtein(left, right)
    if distance <= max_distance:
        return True
    shorter, longer = sorted((left, right), key=len)
    return longer.startswith(shorter) and len(longer) - len(shorter) <= max_distance


def _similarity(left: str, right: str) -> float:
    max_length = max(len(left), len(right), 1)
    return 1.0 - (levenshtein(left, right) / max_length)


def _choose_canonical_row(
    rows: list[dict[str, Any]], indices: list[int], columns: tuple[str, ...]
) -> int:
    return max(
        indices,
        key=lambda index: (
            not bool(rows[index].get("typo_suspect")),
            _non_empty_count(rows[index]),
            len(_row_key(rows[index], columns)),
            -index,
        ),
    )


def _non_empty_count(row: dict[str, Any]) -> int:
    ignored_prefixes = ("duplicate_", "similarity_", "canonical_", "matched_", "typo_")
    return sum(
        not _is_empty(value)
        for column, value in row.items()
        if not column.startswith(ignored_prefixes)
    )


def _without_duplicate_metadata(
    row: dict[str, Any], data_columns: tuple[str, ...], merged_from_count: int
) -> dict[str, Any]:
    result = {column: row.get(column, "") for column in data_columns}
    result["merged_from_count"] = merged_from_count
    return result


def _is_empty(value: Any) -> bool:
    return value is None or value == ""
