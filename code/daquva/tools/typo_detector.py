"""Small deterministic typo detector.

This intentionally uses transparent heuristics instead of ML:
- case normalization
- Levenshtein distance
- common email domain corrections
"""

from __future__ import annotations

from typing import Any

from daquva.tools.fuzzy_duplicates import levenshtein, normalize


COMMON_EMAIL_DOMAINS = (
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "example.com",
)


def annotate_typos(
    rows: list[dict[str, Any]],
    column: str,
    max_distance: int = 2,
) -> list[dict[str, Any]]:
    values = [str(row.get(column, "")) for row in rows]
    normalized_values = [normalize(value) for value in values]
    counts: dict[str, int] = {}
    for value in normalized_values:
        if value:
            counts[value] = counts.get(value, 0) + 1

    annotated: list[dict[str, Any]] = []
    for row, value, normalized in zip(rows, values, normalized_values, strict=True):
        suggestion, distance = _suggest(value, normalized, counts, max_distance)
        updated = dict(row)
        updated["typo_suspect"] = suggestion != ""
        updated["typo_suggestion"] = suggestion
        updated["typo_distance"] = distance if suggestion else ""
        annotated.append(updated)

    return annotated


def choose_typo_column(columns: tuple[str, ...], params: tuple[Any, ...]) -> str:
    if params:
        requested = str(params[0])
        if requested in columns:
            return requested
    for preferred in ("email", "name"):
        if preferred in columns:
            return preferred
    return columns[0]


def _suggest(
    value: str,
    normalized: str,
    counts: dict[str, int],
    max_distance: int,
) -> tuple[str, int]:
    if not normalized:
        return "", 0

    email_suggestion = _suggest_email_domain(value, max_distance)
    if email_suggestion:
        domain_distance = levenshtein(value.split("@")[-1].casefold(), email_suggestion.split("@")[-1])
        return email_suggestion, domain_distance

    best_value = ""
    best_distance = max_distance + 1
    current_count = counts.get(normalized, 0)
    for candidate, count in counts.items():
        if candidate == normalized or count <= current_count:
            continue
        distance = levenshtein(normalized, candidate)
        if 0 < distance < best_distance and distance <= max_distance:
            best_value = candidate
            best_distance = distance

    if best_value:
        return best_value, best_distance
    return "", 0


def _suggest_email_domain(value: str, max_distance: int) -> str:
    if "@" not in value:
        return ""
    local, domain = value.rsplit("@", 1)
    normalized_domain = domain.casefold()
    for common_domain in COMMON_EMAIL_DOMAINS:
        distance = levenshtein(normalized_domain, common_domain)
        if 0 < distance <= max_distance:
            return f"{local}@{common_domain}"
    return ""
