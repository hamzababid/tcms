"""Planning validation (docs/02 §6.1–6.3). Pure functions; no I/O."""

from __future__ import annotations

from typing import Any, Final, Literal

from tcms.core.errors import FieldError

NAME_MIN: Final = 3
NAME_MAX: Final = 150
MD_MAX: Final = 20_000
MAX_RISKS: Final = 50
RISK_IMPACTS: Final = ("low", "medium", "high")

# Reason codes reported when a case cannot be added to a plan (docs/02 §6.2) or a cycle (BR-13).
SkipReason = Literal["archived", "deprecated", "unapproved", "already_in_plan"]


def name_problem(name: str) -> FieldError | None:
    n = name.strip()
    if not (NAME_MIN <= len(n) <= NAME_MAX):
        return FieldError("name", "invalid_length", f"{NAME_MIN}–{NAME_MAX} characters")
    return None


def normalize_md(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.replace("\r\n", "\n").strip()
    return v or None


def date_order_problem(start: Any, end: Any) -> FieldError | None:
    """end ≥ start (docs/02 §6.1)."""
    if start is not None and end is not None and end < start:
        return FieldError("end_date", "invalid_range", "End date must be on or after the start date")
    return None


def risks_problem(risks: list[dict[str, Any]]) -> FieldError | None:
    if len(risks) > MAX_RISKS:
        return FieldError("risks", "too_many", f"At most {MAX_RISKS} risks")
    for r in risks:
        if r.get("impact") not in RISK_IMPACTS:
            return FieldError("risks", "invalid_impact", "impact must be low, medium or high")
        desc = (r.get("description") or "").strip()
        if not desc:
            return FieldError("risks", "field_required", "Each risk needs a description")
    return None
