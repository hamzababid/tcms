"""Planning validation (docs/02 §6.1–6.3). Pure functions; no I/O."""

from __future__ import annotations

from typing import Any, Final, Literal

from tcms.core.enums import PlanStatus
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


# -- exit criteria as readiness rules (FR-PLN-005, docs/02 §11.4, docs/06 §5.9) -------------------
#
# A rule is `{type, threshold, params?}`. Percentage rules take a fraction 0–1 (docs/06 §5.9 shows
# `"threshold": 1.0` for 100 %); count rules take a whole number ≥ 0. Rules are evaluated in M7.

PERCENT_RULES: Final = frozenset(
    {
        "min_execution_progress",
        "min_pass_rate",
        "min_pass_rate_applicable",
        "min_requirement_coverage",
        "min_requirements_verified",
    }
)
COUNT_RULES: Final = frozenset(
    {"max_failed", "max_blocked"}
)  # max_failed replaced max_open_defects (ADR-023)
FLAG_RULES: Final = frozenset({"tag_fully_executed"})
RULE_TYPES: Final = PERCENT_RULES | COUNT_RULES | FLAG_RULES
MAX_EXIT_RULES: Final = 20


def exit_rules_problem(rules: list[dict[str, Any]]) -> FieldError | None:
    if len(rules) > MAX_EXIT_RULES:
        return FieldError("exit_rules", "too_many", f"At most {MAX_EXIT_RULES} rules")
    for i, r in enumerate(rules):
        where = f"exit_rules[{i}]"
        kind = r.get("type")
        params = r.get("params") or {}
        threshold = r.get("threshold")
        if kind not in RULE_TYPES:
            return FieldError(f"{where}.type", "invalid_value", "Unknown rule type")
        if kind in PERCENT_RULES and not (isinstance(threshold, int | float) and 0 <= threshold <= 1):
            return FieldError(f"{where}.threshold", "invalid_range", "Give a percentage between 0 and 100")
        if kind in COUNT_RULES and not (
            isinstance(threshold, int | float) and threshold >= 0 and float(threshold).is_integer()
        ):
            return FieldError(f"{where}.threshold", "invalid_range", "Give a whole number of 0 or more")
        if kind == "tag_fully_executed" and not str(params.get("tag") or "").strip():
            return FieldError(f"{where}.params.tag", "field_required", "Choose a tag")
    return None


# -- status lifecycle -----------------------------------------------------------------------------
#
# docs/02 §6.1 lists the statuses but not the transitions. Mirroring the release machine
# (docs/02 §4.4): forward draft → active → completed, with a step back allowed while the plan is not
# archived. `archived` is terminal and only reached through the archive endpoint, never a status PATCH.
_PLAN_TRANSITIONS: Final[dict[PlanStatus, frozenset[PlanStatus]]] = {
    PlanStatus.draft: frozenset({PlanStatus.active}),
    PlanStatus.active: frozenset({PlanStatus.draft, PlanStatus.completed}),
    PlanStatus.completed: frozenset({PlanStatus.active}),
    PlanStatus.archived: frozenset(),
}


def plan_transition_allowed(current: PlanStatus, target: PlanStatus) -> bool:
    if current == target:
        return True  # no-op patch is not an error
    return target in _PLAN_TRANSITIONS[current]


def allowed_plan_targets(current: PlanStatus) -> frozenset[PlanStatus]:
    return _PLAN_TRANSITIONS[current]
