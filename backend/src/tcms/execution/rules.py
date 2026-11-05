"""Execution validation and derivations (docs/02 §7.1–7.2; docs/04 §5.1–5.2, §5.7). Pure functions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal
from uuid import UUID

from tcms.core.enums import CycleStatus
from tcms.core.errors import FieldError
from tcms.testdesign.queries import PRIORITY_RANK, CaseRef

NAME_MIN: Final = 3
NAME_MAX: Final = 150
BUILD_MAX: Final = 100
INLINE_RUN_LIMIT: Final = 500  # > 500 cases → background job (docs/02 §7.1, docs/04 §5.2)
CLONE_STATUSES: Final = frozenset({"failed", "blocked", "not_run"})  # docs/06 §4.6

# Reasons a case is skipped when building/adding to a cycle (docs/04 §5.2).
SkipReason = Literal["archived", "deprecated", "no_eligible_version", "already_in_cycle", "not_found"]


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
    reason: SkipReason | None  # set when version_id is None


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


def tree_order(cases: list[CaseRef], folder_order: Mapping[UUID, int]) -> list[CaseRef]:
    """Default run order: folder tree order, then case key (docs/02 §7.1)."""
    last = len(folder_order)
    return sorted(cases, key=lambda c: (folder_order.get(c.folder_id, last), c.key_num))


def priority_order(cases: list[CaseRef], folder_order: Mapping[UUID, int]) -> list[CaseRef]:
    """ "Sort by priority": critical first; ties keep tree order."""
    last = len(folder_order)
    return sorted(
        cases,
        key=lambda c: (PRIORITY_RANK.get(c.priority, 9), folder_order.get(c.folder_id, last), c.key_num),
    )


def clone_statuses_problem(statuses: list[str]) -> FieldError | None:
    bad = sorted(set(statuses) - CLONE_STATUSES)
    if bad:
        return FieldError("only_statuses", "invalid_value", "Choose from failed, blocked, not_run")
    return None


@dataclass(frozen=True)
class NewerVersion:
    """docs/06 §5.4 `newer_version` (the "v5 available (you are on v3)" banner)."""

    version_id: UUID
    eligible: bool
    can_update: bool
    reason: str | None  # why the run cannot be updated in place: run_has_results, cycle_closed, superseded


def newer_version(
    *,
    pinned_version_id: UUID,
    eligible_version_id: UUID | None,
    has_attempts: bool,
    cycle_status: CycleStatus,
    superseded: bool,
) -> NewerVersion | None:
    if eligible_version_id is None or eligible_version_id == pinned_version_id:
        return None
    reason = (
        "run_superseded"
        if superseded
        else "cycle_closed"
        if cycle_status == CycleStatus.closed
        else "run_has_results"
        if has_attempts
        else None
    )
    return NewerVersion(eligible_version_id, True, reason is None, reason)


# -- cycle lifecycle (BR-11, docs/02 §7.1) --------------------------------------------------------

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
