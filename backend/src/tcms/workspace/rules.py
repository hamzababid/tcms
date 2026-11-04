"""Pure workspace rules (docs/02 §4, BR-16, BR-27)."""

from __future__ import annotations

import re
from typing import Any, Final

from tcms.core.enums import ReleaseStatus
from tcms.core.errors import FieldError
from tcms.core.policy import DEFAULT_ORG_SETTINGS, OrgPolicy

PROJECT_KEY_RE: Final = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
SLUG_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
DEFAULT_ENVIRONMENTS: Final = ("QA", "Staging")
KEY_ENTITIES: Final = ("test_case", "test_plan", "test_cycle", "defect", "requirement")
KEY_PREFIX: Final = {
    "test_case": "TC",
    "test_plan": "PL",
    "test_cycle": "CY",
    "defect": "D",
    "requirement": "R",
}
PLATFORM_ATTACHMENT_CAP_MB: Final = 100

DEFAULT_PROJECT_SETTINGS: Final[dict[str, Any]] = {
    "approval_required": False,
    "allow_self_approval": False,
    "only_assignee_executes": False,
    "report_module_depth": 1,
    "attachment_max_mb": 25,
    "require_defect_for_failure": False,
}


def normalize_project_key(raw: str) -> str:
    """Keys are upper-cased before validation and comparison (AC-WS-01)."""
    return raw.strip().upper()


def project_key_problem(key: str) -> FieldError | None:
    if not PROJECT_KEY_RE.match(key):
        return FieldError(
            "key", "invalid_format", "2–10 characters: uppercase letters and digits, starting with a letter"
        )
    return None


def human_key(project_key: str, entity: str, number: int) -> str:
    """BR-16: `<PROJECT>-<PREFIX>-<n>`."""
    return f"{project_key}-{KEY_PREFIX[entity]}-{number}"


# -- organization settings (docs/02 §4.1) ---------------------------------------------------------

_ORG_RANGES: Final[dict[str, tuple[int, int]]] = {
    "session_idle_minutes": (15, 480),
    "session_absolute_hours": (1, 24),
    "default_attachment_max_mb": (1, PLATFORM_ATTACHMENT_CAP_MB),
    "audit_retention_years": (1, 10),
}
_ORG_BOOLS: Final = ("mfa_required_for_all", "qa_managers_can_create_projects")


def org_settings_problems(patch: dict[str, Any]) -> list[FieldError]:
    problems = []
    for key, value in patch.items():
        field = f"settings.{key}"
        if key in _ORG_RANGES:
            lo, hi = _ORG_RANGES[key]
            if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                problems.append(
                    FieldError(field, "out_of_range", f"Must be a whole number from {lo} to {hi}")
                )
        elif key in _ORG_BOOLS:
            if not isinstance(value, bool):
                problems.append(FieldError(field, "invalid_type", "Must be true or false"))
        else:
            problems.append(FieldError(field, "unknown_setting", "Unknown setting"))
    return problems


def merged_org_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_ORG_SETTINGS, **current, **patch}


# -- project settings (docs/02 §4.2) --------------------------------------------------------------

_PROJECT_BOOLS: Final = (
    "approval_required",
    "allow_self_approval",
    "only_assignee_executes",
    "require_defect_for_failure",
)


def project_settings_problems(patch: dict[str, Any], policy: OrgPolicy) -> list[FieldError]:
    """Attachment limit: 1…org `default_attachment_max_mb`, which is also the org cap (review K9)."""
    problems = []
    for key, value in patch.items():
        field = f"settings.{key}"
        if key in _PROJECT_BOOLS:
            if not isinstance(value, bool):
                problems.append(FieldError(field, "invalid_type", "Must be true or false"))
        elif key == "report_module_depth":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                problems.append(FieldError(field, "out_of_range", "Must be a whole number from 1 to 5"))
        elif key == "attachment_max_mb":
            cap = policy.default_attachment_max_mb
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= cap:
                problems.append(FieldError(field, "out_of_range", f"Must be a whole number from 1 to {cap}"))
        else:
            problems.append(FieldError(field, "unknown_setting", "Unknown setting"))
    return problems


def default_project_settings(policy: OrgPolicy) -> dict[str, Any]:
    return {**DEFAULT_PROJECT_SETTINGS, "attachment_max_mb": policy.default_attachment_max_mb}


def merged_project_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_PROJECT_SETTINGS, **current, **patch}


# -- releases (docs/02 §4.4) ----------------------------------------------------------------------

_RELEASE_TRANSITIONS: Final[dict[ReleaseStatus, frozenset[ReleaseStatus]]] = {
    ReleaseStatus.planned: frozenset({ReleaseStatus.active, ReleaseStatus.archived}),
    ReleaseStatus.active: frozenset({ReleaseStatus.released, ReleaseStatus.archived}),
    ReleaseStatus.released: frozenset(
        {ReleaseStatus.active, ReleaseStatus.archived}
    ),  # hotfix: back to active
    ReleaseStatus.archived: frozenset(),
}


def release_transition_allowed(current: ReleaseStatus, target: ReleaseStatus) -> bool:
    return target in _RELEASE_TRANSITIONS[current]


def allowed_release_targets(current: ReleaseStatus) -> frozenset[ReleaseStatus]:
    return _RELEASE_TRANSITIONS[current]
