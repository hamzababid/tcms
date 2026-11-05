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


# -- attempts: roll-up (BR-09, TCMS-071) ---------------------------------------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402
from itertools import product  # noqa: E402

from tcms.execution.rules import (  # noqa: E402
    FinalStatus,
    IncompleteAttempt,
    OutcomeConflictsWithSteps,
    OutcomeRequired,
    StepRecord,
)

STEP = ("not_run", "passed", "failed", "blocked", "skipped")
EXPLICIT = (None, "passed", "failed", "blocked", "skipped", "not_applicable")


def _oracle(steps: tuple[str, ...], explicit: str | None) -> str:
    """docs/02 §7.3 precedence table, row by row (with reviews K17h/i): the expected status or error code."""
    if explicit in ("passed", "failed"):
        return "outcome_conflicts_with_steps"
    if "failed" in steps:
        return "failed" if explicit is None else "outcome_conflicts_with_steps"
    if "blocked" in steps:
        return "blocked" if explicit in (None, "blocked") else "outcome_conflicts_with_steps"
    if explicit is not None:
        return explicit
    if all(s in ("passed", "skipped") for s in steps) and "passed" in steps:
        return "passed"
    return "incomplete_attempt"


@pytest.mark.br("BR-09")
def test_br_09_tcms_071_roll_up_matrix_is_exhaustive() -> None:
    """TCMS-071 / AC-EXE-01/02/03: every combination of 1–4 step statuses × every explicit outcome."""
    checked = 0
    for n in range(1, 5):
        for steps in product(STEP, repeat=n):
            for explicit in EXPLICIT:
                expected = _oracle(steps, explicit)
                try:
                    got: str = rules.compute_final_status("steps", steps, explicit).status
                except (IncompleteAttempt, OutcomeConflictsWithSteps) as exc:
                    got = exc.code
                assert got == expected, (steps, explicit)
                checked += 1
    assert checked == (5 + 25 + 125 + 625) * 6


@pytest.mark.parametrize(
    ("steps", "explicit", "expected"),
    [
        (("passed", "failed", "not_run"), None, FinalStatus("failed", 0)),  # AC-EXE-01
        (("passed", "skipped", "passed"), None, FinalStatus("passed", 1)),  # AC-EXE-02
        (("passed", "not_run"), "blocked", FinalStatus("blocked", 0)),  # partly passed, env went down
        (("skipped", "skipped"), "not_applicable", FinalStatus("not_applicable", 2)),
    ],
)
def test_ac_exe_01_02_examples(steps: tuple[str, ...], explicit: str | None, expected: FinalStatus) -> None:
    assert rules.compute_final_status("steps", steps, explicit) == expected


def test_ac_exe_03_incomplete_lists_the_unrecorded_steps() -> None:
    with pytest.raises(IncompleteAttempt) as exc:
        rules.compute_final_status("steps", ("passed", "not_run", "not_run"), None)
    assert exc.value.detail.startswith("Steps 2, 3 have no result")
    assert [e.field for e in exc.value.errors] == ["steps[1].status", "steps[2].status"]
    with pytest.raises(IncompleteAttempt) as one:
        rules.compute_final_status("steps", ("passed", "not_run"), None)
    assert one.value.detail.startswith("Step 2 has no result")
    with pytest.raises(IncompleteAttempt, match="Every step is skipped"):
        rules.compute_final_status("steps", ("skipped",), None)


def test_tcms_089_text_format_takes_the_testers_outcome() -> None:
    for outcome in ("passed", "failed", "blocked", "skipped", "not_applicable"):
        assert rules.compute_final_status("text", (), outcome) == FinalStatus(outcome, 0)
    with pytest.raises(OutcomeRequired):
        rules.compute_final_status("text", (), None)
    with pytest.raises(OutcomeConflictsWithSteps):
        rules.compute_final_status("text", (), "in_progress")


@pytest.mark.br("BR-10")
@pytest.mark.parametrize(
    ("fmt", "steps", "status", "reason", "comment", "codes"),
    [
        ("steps", [StepRecord(1, "passed", None)], "passed", None, None, []),
        ("steps", [StepRecord(1, "failed", "  ")], "failed", None, None, ["actual_result_required"]),
        ("steps", [StepRecord(2, "failed", "Took 9 s")], "failed", None, None, []),
        ("steps", [StepRecord(1, "blocked", None)], "blocked", None, None, ["reason_required"]),  # K2
        ("steps", [StepRecord(1, "blocked", None)], "blocked", "Env down", None, []),
        ("steps", [], "skipped", "x" * 1001, None, ["too_long"]),
        ("steps", [], "not_applicable", " ", None, ["reason_required"]),
        ("text", [], "failed", None, None, ["field_required"]),
        ("text", [], "failed", None, "Login button missing", []),
        ("text", [], "passed", None, None, []),
    ],
)
def test_br_10_finalize_problems(
    fmt: str, steps: list[StepRecord], status: str, reason: str | None, comment: str | None, codes: list[str]
) -> None:
    assert [p.code for p in rules.finalize_problems(fmt, steps, status, reason, comment)] == codes


def test_br_10_actual_result_problem_names_the_step() -> None:
    (p,) = rules.finalize_problems("steps", [StepRecord(3, "failed", None)], "failed", None, None)
    assert p.field == "steps[2].actual_result"
    assert "Step 3" in p.message


@pytest.mark.br("BR-08")
@pytest.mark.parametrize(
    ("attempts", "status"),
    [
        ([], "not_run"),
        ([(1, "draft", None)], "in_progress"),
        ([(1, "final", "failed")], "failed"),
        ([(1, "final", "failed"), (2, "final", "passed")], "passed"),  # AC-EXE-07
        ([(2, "final", "blocked"), (1, "final", "passed")], "blocked"),
        ([(1, "final", "failed"), (2, "draft", None)], "in_progress"),
    ],
)
def test_br_08_derive_run_status(attempts: list[tuple[int, str, str | None]], status: str) -> None:
    assert rules.derive_run_status(attempts) == status


@pytest.mark.br("BR-32")
def test_br_32_only_assignee_executes() -> None:
    me, other = uuid4(), uuid4()
    for only, manage, assignee, ok in [
        (False, False, other, True),
        (True, False, me, True),
        (True, False, None, True),
        (True, False, other, False),
        (True, True, other, True),
    ]:
        assert (
            rules.may_execute(assignee_id=assignee, user_id=me, only_assignee=only, has_manage=manage) is ok
        )


def test_duration_uses_the_given_value_or_elapsed_time_within_bounds() -> None:
    t0 = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
    assert rules.duration_seconds(t0, t0 + timedelta(seconds=252), None) == 252
    assert rules.duration_seconds(t0, t0 + timedelta(days=2), None) == 86_400
    assert rules.duration_seconds(t0, t0 - timedelta(seconds=5), None) == 0
    assert rules.duration_seconds(t0, t0, 90) == 90
    assert rules.duration_seconds(t0, t0, 100_000) == 86_400
    assert rules.duration_seconds(t0, t0, -3) == 0
