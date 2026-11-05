"""Pure execution rules (docs/02 §7.1–7.2; docs/04 §5.1–5.2; BR-03/04/05/11/13). Branch coverage gate: ≥ 95%."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from tcms.core.enums import CycleStatus as CS
from tcms.execution import rules
from tcms.testdesign.queries import CaseRef

FOLDER_A, FOLDER_B = uuid4(), uuid4()
LATEST, APPROVED = uuid4(), uuid4()


def _case(
    *,
    status: str = "approved",
    latest: UUID | None = LATEST,
    approved: UUID | None = APPROVED,
    folder: UUID = FOLDER_A,
    key_num: int = 1,
    priority: str = "medium",
) -> CaseRef:
    return CaseRef(
        id=uuid4(),
        key=f"SPARK-TC-{key_num}",
        key_num=key_num,
        title="A case",
        folder_id=folder,
        status=status,
        priority=priority,
        latest_version_id=latest,
        approved_version_id=approved,
    )


@pytest.mark.parametrize(
    ("name", "ok"), [("ab", False), ("  abc  ", True), ("x" * 150, True), ("x" * 151, False)]
)
def test_name_length(name: str, ok: bool) -> None:
    assert (rules.name_problem(name) is None) is ok


@pytest.mark.parametrize(
    ("start", "due", "ok"),
    [
        (None, None, True),
        (date(2026, 11, 3), None, True),
        (None, date(2026, 11, 3), True),
        (date(2026, 11, 3), date(2026, 11, 3), True),
        (date(2026, 11, 4), date(2026, 11, 3), False),
    ],
)
def test_due_date_on_or_after_start(start: date | None, due: date | None, ok: bool) -> None:
    problem = rules.date_order_problem(start, due)
    assert (problem is None) is ok
    if problem:
        assert problem.field == "due_date"


@pytest.mark.br("BR-03")
@pytest.mark.parametrize(
    ("case_kw", "approval", "purpose", "version", "reason"),
    [
        ({"status": "archived"}, False, "new_cycle", None, "archived"),
        ({"status": "archived"}, False, "existing", None, "archived"),
        ({"status": "deprecated"}, False, "new_cycle", None, "deprecated"),
        ({"status": "deprecated"}, False, "existing", LATEST, None),  # existing references keep working
        ({}, False, "new_cycle", LATEST, None),
        ({}, True, "new_cycle", APPROVED, None),
        ({"approved": None}, True, "new_cycle", None, "no_eligible_version"),
        ({"latest": None}, False, "new_cycle", None, "no_eligible_version"),
    ],
)
def test_br_03_br_13_eligible_version(
    case_kw: dict[str, object], approval: bool, purpose: str, version: UUID | None, reason: str | None
) -> None:
    e = rules.eligible_version(_case(**case_kw), approval_required=approval, purpose=purpose)  # type: ignore[arg-type]
    assert (e.version_id, e.reason) == (version, reason)


def test_default_order_is_folder_tree_then_key_unknown_folders_last() -> None:
    order = {FOLDER_A: 0, FOLDER_B: 1}
    unknown = uuid4()
    cases = [
        _case(folder=unknown, key_num=1),
        _case(folder=FOLDER_B, key_num=2),
        _case(folder=FOLDER_A, key_num=9),
        _case(folder=FOLDER_A, key_num=3),
    ]
    assert [c.key_num for c in rules.tree_order(cases, order)] == [3, 9, 2, 1]


def test_priority_order_critical_first_ties_keep_tree_order() -> None:
    order = {FOLDER_A: 0, FOLDER_B: 1}
    cases = [
        _case(folder=FOLDER_A, key_num=1, priority="low"),
        _case(folder=FOLDER_B, key_num=2, priority="critical"),
        _case(folder=FOLDER_A, key_num=3, priority="critical"),
        _case(folder=uuid4(), key_num=4, priority="unknown"),
    ]
    assert [c.key_num for c in rules.priority_order(cases, order)] == [3, 2, 1, 4]


@pytest.mark.parametrize(
    ("statuses", "ok"),
    [
        ([], True),
        (["failed", "blocked", "not_run"], True),
        (["passed"], False),
        (["failed", "skipped"], False),
    ],
)
def test_clone_statuses(statuses: list[str], ok: bool) -> None:
    assert (rules.clone_statuses_problem(statuses) is None) is ok


PINNED, NEWER = uuid4(), uuid4()


@pytest.mark.br("BR-04")
@pytest.mark.parametrize(
    ("eligible", "attempts", "status", "superseded", "expected"),
    [
        (None, False, CS.active, False, None),
        (PINNED, False, CS.active, False, None),
        (NEWER, False, CS.active, False, (True, None)),
        (NEWER, True, CS.active, False, (False, "run_has_results")),  # BR-05: replace instead
        (NEWER, False, CS.closed, False, (False, "cycle_closed")),
        (NEWER, True, CS.active, True, (False, "run_superseded")),
    ],
)
def test_br_04_br_05_newer_version(
    eligible: UUID | None,
    attempts: bool,
    status: CS,
    superseded: bool,
    expected: tuple[bool, str | None] | None,
) -> None:
    n = rules.newer_version(
        pinned_version_id=PINNED,
        eligible_version_id=eligible,
        has_attempts=attempts,
        cycle_status=status,
        superseded=superseded,
    )
    if expected is None:
        assert n is None
    else:
        assert n is not None
        assert (n.version_id, n.eligible, n.can_update, n.reason) == (NEWER, True, *expected)


@pytest.mark.br("BR-11")
def test_br_11_lifecycle_transition_matrix() -> None:
    allowed = {("start", CS.planned), ("close", CS.active), ("reopen", CS.closed)}
    for action in ("start", "close", "reopen", "archive"):
        for status in CS:
            assert rules.can_transition(action, status) is ((action, status) in allowed)
    assert rules.next_status("start") == CS.active
    assert rules.next_status("close") == CS.closed
    assert rules.next_status("reopen") == CS.active
