"""Execution validation and derivations (docs/02 §7.1–7.2; docs/04 §5.1–5.2, §5.7). Pure functions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

from tcms.core.enums import CycleStatus
from tcms.core.errors import FieldError, RuleViolation
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


# -- attempts (BR-06…10, BR-32; docs/02 §7.3; docs/04 §5.3–5.6) ----------------------------------

EXPLICIT_OUTCOMES: Final = frozenset({"blocked", "skipped", "not_applicable"})
TEXT_OUTCOMES: Final = frozenset({"passed", "failed", "blocked", "skipped", "not_applicable"})
REASON_STATUSES: Final = EXPLICIT_OUTCOMES  # BR-10 / review K2: every final one needs a reason
REASON_MAX: Final = 1000
MAX_DURATION: Final = 86_400


class IncompleteAttempt(RuleViolation):
    code, title = "incomplete_attempt", "Attempt cannot be finalized"


class OutcomeRequired(RuleViolation):
    code, title = "outcome_required", "Choose the result of this run"


class OutcomeConflictsWithSteps(RuleViolation):
    code, title = "outcome_conflicts_with_steps", "The chosen result contradicts the step results"


@dataclass(frozen=True)
class FinalStatus:
    status: str
    skipped_steps: int


def compute_final_status(fmt: str, steps: Sequence[str], explicit: str | None) -> FinalStatus:
    """BR-09 roll-up with the docs/02 §7.3 precedence table (reviews K17h/i).

    `steps` are the step statuses of a `steps` attempt (ignored for `text`); `explicit` is the run-level
    outcome the tester sent, if any."""
    skipped = sum(1 for s in steps if s == "skipped")
    if fmt == "text":
        if explicit is None:
            raise OutcomeRequired("Choose Passed, Failed, Blocked, Skipped or Not applicable")
        if explicit not in TEXT_OUTCOMES:
            raise OutcomeConflictsWithSteps(f"Unknown result {explicit}")
        return FinalStatus(explicit, 0)
    if explicit is not None and explicit not in EXPLICIT_OUTCOMES:
        # Passed and Failed come from the steps, never from the tester (K17i).
        raise OutcomeConflictsWithSteps("Passed and Failed are worked out from the step results")
    if "failed" in steps:
        if explicit is not None:
            raise OutcomeConflictsWithSteps("A step failed, so the run is Failed")  # K17h
        return FinalStatus("failed", skipped)
    if "blocked" in steps:
        if explicit not in (None, "blocked"):
            raise OutcomeConflictsWithSteps("A step is blocked, so the run is Blocked")
        return FinalStatus("blocked", skipped)
    if explicit is not None:
        return FinalStatus(explicit, skipped)
    if steps and all(s in ("passed", "skipped") for s in steps) and "passed" in steps:
        return FinalStatus("passed", skipped)
    not_recorded = [i + 1 for i, s in enumerate(steps) if s == "not_run"]
    if not_recorded:
        listed = ", ".join(str(n) for n in not_recorded)
        detail = (
            f"Step {listed} has no result" if len(not_recorded) == 1 else f"Steps {listed} have no result"
        ) + ". Record them or choose Blocked, Skipped or Not applicable with a reason."
        raise IncompleteAttempt(
            detail,
            errors=[
                FieldError(f"steps[{n - 1}].status", "not_recorded", f"Step {n} has no result")
                for n in not_recorded
            ],
        )
    raise IncompleteAttempt("Every step is skipped. Choose Skipped or Not applicable with a reason.")


@dataclass(frozen=True)
class StepRecord:
    position: int
    status: str
    actual_result: str | None


def finalize_problems(
    fmt: str, steps: Sequence[StepRecord], status: str, reason: str | None, comment: str | None
) -> list[FieldError]:
    """BR-10: actual result on failed steps, reason on blocked/skipped/N/A (K2), comment on a failed
    text attempt (docs/02 §7.3). The service raises the first family of problems found."""
    problems: list[FieldError] = []
    if fmt == "steps":
        for st in steps:
            if st.status == "failed" and not (st.actual_result or "").strip():
                problems.append(
                    FieldError(
                        f"steps[{st.position - 1}].actual_result",
                        "actual_result_required",
                        f"Step {st.position} failed: describe the actual result",
                    )
                )
    if status in REASON_STATUSES and not (reason or "").strip():
        problems.append(FieldError("reason", "reason_required", "Give a reason"))
    if reason is not None and len(reason) > REASON_MAX:
        problems.append(FieldError("reason", "too_long", f"At most {REASON_MAX} characters"))
    if fmt == "text" and status == "failed" and not (comment or "").strip():
        problems.append(FieldError("comment", "field_required", "Describe what failed"))
    return problems


def derive_run_status(attempts: Sequence[tuple[int, str, str | None]]) -> str:
    """BR-08 from `(attempt_no, state, status)` rows: a draft → in_progress; else the latest final
    attempt's status; no attempt → not_run. Used by the consistency check (docs/04 §5.6)."""
    if any(state == "draft" for _, state, _ in attempts):
        return "in_progress"
    finals = sorted((n, st) for n, state, st in attempts if state == "final" and st is not None)
    return finals[-1][1] if finals else "not_run"


def may_execute(*, assignee_id: UUID | None, user_id: UUID, only_assignee: bool, has_manage: bool) -> bool:
    """BR-32: with "only assignee executes" others need cycle.manage; unassigned runs are open to all."""
    if not only_assignee or has_manage:
        return True
    return assignee_id is None or assignee_id == user_id


def duration_seconds(started: datetime, finished: datetime, given: int | None) -> int:
    """docs/02 §7.3: the tester's value, else the elapsed time; within 0–86,400 (SQL CHECK)."""
    if given is not None:
        return max(0, min(given, MAX_DURATION))
    return max(0, min(int((finished - started).total_seconds()), MAX_DURATION))
