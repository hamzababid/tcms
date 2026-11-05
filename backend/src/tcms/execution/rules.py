"""Execution validation and derivations (docs/02 §7.1–7.2; docs/04 §5.1–5.2, §5.7). Pure functions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal
from uuid import UUID

from tcms.core.enums import CycleStatus
from tcms.core.errors import FieldError
from tcms.testdesign.queries import CaseRef

NAME_MIN: Final = 3
NAME_MAX: Final = 150
BUILD_MAX: Final = 100
INLINE_RUN_LIMIT: Final = 500  # > 500 cases → background job (docs/02 §7.1, docs/04 §5.2)

# Reasons a case is skipped when building/adding to a cycle (docs/04 §5.2).
SkipReason = Literal["archived", "deprecated", "no_eligible_version", "already_in_cycle"]


def name_problem(name: str) -> FieldError | None:
    n = name.strip()
    if not (NAME_MIN <= len(n) <= NAME_MAX):
        return FieldError("name", "invalid_length", f"{NAME_MIN}–{NAME_MAX} characters")
    return None


def date_order_problem(start: date | None, due: date | None) -> FieldError | None:
    if start is not None and due is not None and due < start:
        return FieldError("due_date", "invalid_range", "Due date must be on or after the start date")
    return None


@dataclass(frozen=True)
class Eligible:
    version_id: UUID | None
    reason: SkipReason | None  # set when version_id is None (or when the case is ineligible)


def eligible_version(case: CaseRef, *, approval_required: bool, purpose: str) -> Eligible:
    """BR-03 / BR-13 / BR-17 (docs/04 §5.1). `purpose` is "new_cycle" or "existing".

    - archived case → ineligible.
    - deprecated case → ineligible for a new cycle (BR-13); existing references keep working.
    - approval enforced → the approved version; otherwise the latest version.
    - no such version → ineligible (no_eligible_version).
    """
    if case.status == "archived":
        return Eligible(None, "archived")
    if purpose == "new_cycle" and case.status == "deprecated":
        return Eligible(None, "deprecated")
    version_id = case.approved_version_id if approval_required else case.latest_version_id
    if version_id is None:
        return Eligible(None, "no_eligible_version")
    return Eligible(version_id, None)


# -- cycle lifecycle (BR-11, docs/02 §7.1) --------------------------------------------------------

# Allowed status transitions by action.
_TRANSITIONS: Final[dict[str, tuple[CycleStatus, CycleStatus]]] = {
    "start": (CycleStatus.planned, CycleStatus.active),
    "close": (CycleStatus.active, CycleStatus.closed),
    "reopen": (CycleStatus.closed, CycleStatus.active),
}


def can_transition(action: str, current: CycleStatus) -> bool:
    expected = _TRANSITIONS.get(action)
    return expected is not None and expected[0] == current


def next_status(action: str) -> CycleStatus:
    return _TRANSITIONS[action][1]
