"""Execution data access (private to the module). Every query is organization- and project-scoped."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.enums import CycleStatus, ResultState, RunStatus
from tcms.execution.models import TestCycle, TestResult, TestRun, TestStepResult

_ACTIVE = TestRun.superseded_by_run_id.is_(None)


def _scope(stmt: Any, model: Any, ctx: AccessContext) -> Any:
    return stmt.where(model.organization_id == ctx.principal.organization_id, model.project_id == ctx.pid)


# -- cycles ---------------------------------------------------------------------------------------


def cycle(s: Session, ctx: AccessContext, cycle_id: UUID, *, for_update: bool = False) -> TestCycle | None:
    stmt = _scope(select(TestCycle), TestCycle, ctx).where(TestCycle.id == cycle_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def cycle_list_stmt(ctx: AccessContext) -> Select[Any]:
    stmt: Select[Any] = _scope(select(TestCycle), TestCycle, ctx)
    return stmt


def cycle_name_taken(s: Session, ctx: AccessContext, name: str, *, exclude: UUID | None = None) -> bool:
    stmt = _scope(select(TestCycle.id), TestCycle, ctx).where(func.lower(TestCycle.name) == name.lower())
    if exclude is not None:
        stmt = stmt.where(TestCycle.id != exclude)
    return s.execute(stmt.limit(1)).first() is not None


def cycles_of_plan(s: Session, ctx: AccessContext, plan_id: UUID) -> list[TestCycle]:
    stmt = _scope(select(TestCycle), TestCycle, ctx).where(TestCycle.plan_id == plan_id)
    return list(s.execute(stmt.order_by(TestCycle.key_num)).scalars())


def open_cycles(s: Session, ctx: AccessContext) -> list[TestCycle]:
    """Planned or active cycles of the project (project archive needs them closed, docs/02 §4.2)."""
    stmt = _scope(select(TestCycle), TestCycle, ctx).where(
        TestCycle.status.in_([CycleStatus.planned, CycleStatus.active])
    )
    return list(s.execute(stmt.order_by(TestCycle.key_num)).scalars())


# -- runs -----------------------------------------------------------------------------------------


def run(s: Session, ctx: AccessContext, run_id: UUID, *, for_update: bool = False) -> TestRun | None:
    stmt = _scope(select(TestRun), TestRun, ctx).where(TestRun.id == run_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def run_list_stmt(ctx: AccessContext, cycle_id: UUID, *, include_superseded: bool) -> Select[Any]:
    stmt: Select[Any] = _scope(select(TestRun), TestRun, ctx).where(TestRun.cycle_id == cycle_id)
    if not include_superseded:
        stmt = stmt.where(_ACTIVE)
    return stmt


def runs_in_cycle(
    s: Session,
    ctx: AccessContext,
    cycle_id: UUID,
    *,
    include_superseded: bool = False,
    for_update: bool = False,
) -> list[TestRun]:
    stmt = run_list_stmt(ctx, cycle_id, include_superseded=include_superseded).order_by(
        TestRun.position, TestRun.id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return list(s.execute(stmt).scalars())


def runs_by_ids(
    s: Session, ctx: AccessContext, run_ids: Sequence[UUID], *, for_update: bool = False
) -> list[TestRun]:
    if not run_ids:
        return []
    stmt = _scope(select(TestRun), TestRun, ctx).where(TestRun.id.in_(run_ids)).order_by(TestRun.position)
    if for_update:
        stmt = stmt.with_for_update()
    return list(s.execute(stmt).scalars())


def active_case_ids(s: Session, ctx: AccessContext, cycle_id: UUID) -> set[UUID]:
    """Case ids that already have a non-superseded run in the cycle (BR-12)."""
    stmt = _scope(select(TestRun.test_case_id), TestRun, ctx).where(TestRun.cycle_id == cycle_id, _ACTIVE)
    return set(s.execute(stmt).scalars())


def max_position(s: Session, ctx: AccessContext, cycle_id: UUID) -> int:
    stmt = _scope(select(func.coalesce(func.max(TestRun.position), 0)), TestRun, ctx).where(
        TestRun.cycle_id == cycle_id
    )
    return int(s.execute(stmt).scalar_one())


def insert_run(
    s: Session,
    ctx: AccessContext,
    *,
    run_id: UUID,
    cycle_id: UUID,
    test_case_id: UUID,
    version_id: UUID,
    position: int,
    assignee_id: UUID | None,
    now: Any,
    actor: UUID | None,
) -> TestRun:
    r = TestRun(
        id=run_id,
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        cycle_id=cycle_id,
        test_case_id=test_case_id,
        test_case_version_id=version_id,
        position=position,
        assignee_id=assignee_id,
        status=RunStatus.not_run,
        needs_retest=False,
        row_version=1,
        created_at=now,
        created_by=actor,
        updated_at=now,
        updated_by=actor,
    )
    s.add(r)
    return r


# -- attempts -------------------------------------------------------------------------------------


def run_has_any_attempt(s: Session, run_id: UUID) -> bool:
    return s.execute(select(TestResult.id).where(TestResult.run_id == run_id).limit(1)).first() is not None


def run_ids_with_attempts(s: Session, run_ids: Sequence[UUID]) -> set[UUID]:
    if not run_ids:
        return set()
    return set(
        s.execute(select(TestResult.run_id).where(TestResult.run_id.in_(run_ids)).distinct()).scalars()
    )


def run_any_attempt_in_cycle(s: Session, ctx: AccessContext, cycle_id: UUID) -> bool:
    """True if any run in the cycle has a result attempt (gates environment change, docs/06 §4.6)."""
    run_ids = _scope(select(TestRun.id), TestRun, ctx).where(TestRun.cycle_id == cycle_id).scalar_subquery()
    return s.execute(select(TestResult.id).where(TestResult.run_id.in_(run_ids)).limit(1)).first() is not None


def run_has_final_attempt(s: Session, run_id: UUID) -> bool:
    return (
        s.execute(
            select(TestResult.id)
            .where(TestResult.run_id == run_id, TestResult.state == ResultState.final)
            .limit(1)
        ).first()
        is not None
    )


def attempts(s: Session, run_id: UUID) -> list[TestResult]:
    return list(
        s.execute(
            select(TestResult).where(TestResult.run_id == run_id).order_by(TestResult.attempt_no)
        ).scalars()
    )


def drafts_in_cycle(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[tuple[TestResult, TestRun]]:
    """Draft attempts on the cycle's active runs (close dialog, docs/02 §7.1)."""
    rows = s.execute(
        _scope(select(TestResult, TestRun), TestRun, ctx)
        .join(TestResult, TestResult.run_id == TestRun.id)
        .where(TestRun.cycle_id == cycle_id, _ACTIVE, TestResult.state == ResultState.draft)
        .order_by(TestRun.position)
    ).all()
    return [(res, run_) for res, run_ in rows]


def delete_draft(s: Session, result: TestResult) -> None:
    """Hard delete of a draft attempt and its step rows (docs/02 §2.5). Finals are protected by the
    database trigger (BR-06)."""
    s.execute(delete(TestStepResult).where(TestStepResult.result_id == result.id))
    s.execute(delete(TestResult).where(TestResult.id == result.id, TestResult.state == ResultState.draft))


def latest_final_status(s: Session, run_: TestRun) -> RunStatus:
    """A run's status from its latest final attempt (BR-08); not_run when there is none."""
    if run_.latest_result_id is None:
        return RunStatus.not_run
    status = s.execute(
        select(TestResult.status).where(TestResult.id == run_.latest_result_id)
    ).scalar_one_or_none()
    return RunStatus(status.value) if status is not None else RunStatus.not_run


# -- aggregates -----------------------------------------------------------------------------------


def status_counts(s: Session, ctx: AccessContext, cycle_ids: Sequence[UUID]) -> dict[UUID, dict[str, int]]:
    """Counts by run status over non-superseded runs, per cycle (docs/05 §5, docs/04 §8)."""
    out: dict[UUID, dict[str, int]] = {c: {} for c in cycle_ids}
    if not cycle_ids:
        return out
    rows = s.execute(
        _scope(select(TestRun.cycle_id, TestRun.status, func.count()), TestRun, ctx)
        .where(TestRun.cycle_id.in_(cycle_ids), _ACTIVE)
        .group_by(TestRun.cycle_id, TestRun.status)
    ).all()
    for cid, status, n in rows:
        out[cid][status.value] = int(n)
    return out


def needs_retest_counts(s: Session, ctx: AccessContext, cycle_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not cycle_ids:
        return {}
    rows = s.execute(
        _scope(select(TestRun.cycle_id, func.count()), TestRun, ctx)
        .where(TestRun.cycle_id.in_(cycle_ids), _ACTIVE, TestRun.needs_retest.is_(True))
        .group_by(TestRun.cycle_id)
    ).all()
    return {c: int(n) for c, n in rows}


def superseded_count(s: Session, ctx: AccessContext, cycle_id: UUID) -> int:
    return int(
        s.execute(
            _scope(select(func.count()).select_from(TestRun), TestRun, ctx).where(
                TestRun.cycle_id == cycle_id, TestRun.superseded_by_run_id.is_not(None)
            )
        ).scalar_one()
    )


def assignee_counts(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[tuple[UUID | None, str, int]]:
    rows = s.execute(
        _scope(select(TestRun.assignee_id, TestRun.status, func.count()), TestRun, ctx)
        .where(TestRun.cycle_id == cycle_id, _ACTIVE)
        .group_by(TestRun.assignee_id, TestRun.status)
    ).all()
    return [(a, st.value, int(n)) for a, st, n in rows]


def folder_counts(
    s: Session, ctx: AccessContext, cycle_id: UUID, case_cols: Any
) -> list[tuple[UUID, str, int]]:
    """Counts by (case folder, run status); `case_cols` is testdesign's public case subquery."""
    rows = s.execute(
        _scope(select(case_cols.c.folder_id, TestRun.status, func.count()), TestRun, ctx)
        .join(case_cols, case_cols.c.id == TestRun.test_case_id)
        .where(TestRun.cycle_id == cycle_id, _ACTIVE)
        .group_by(case_cols.c.folder_id, TestRun.status)
    ).all()
    return [(f, st.value, int(n)) for f, st, n in rows]


# -- attempt writes and reads (M4, docs/04 §5.3–5.5) ----------------------------------------------


def result(s: Session, ctx: AccessContext, result_id: UUID, *, for_update: bool = False) -> TestResult | None:
    stmt = _scope(select(TestResult), TestResult, ctx).where(TestResult.id == result_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def draft_of(s: Session, run_id: UUID) -> TestResult | None:
    return s.execute(
        select(TestResult).where(TestResult.run_id == run_id, TestResult.state == ResultState.draft)
    ).scalar_one_or_none()


def latest_final(s: Session, run_id: UUID) -> TestResult | None:
    return s.execute(
        select(TestResult)
        .where(TestResult.run_id == run_id, TestResult.state == ResultState.final)
        .order_by(TestResult.attempt_no.desc())
        .limit(1)
    ).scalar_one_or_none()


def next_attempt_no(s: Session, run_id: UUID) -> int:
    n = s.execute(
        select(func.coalesce(func.max(TestResult.attempt_no), 0)).where(TestResult.run_id == run_id)
    ).scalar_one()
    return int(n) + 1


def add_result(s: Session, row: TestResult, steps: Sequence[TestStepResult]) -> None:
    s.add(row)
    s.flush()  # the step trigger reads the parent row
    s.add_all(steps)
    s.flush()


def step_results(s: Session, result_id: UUID) -> list[TestStepResult]:
    return list(
        s.execute(
            select(TestStepResult)
            .where(TestStepResult.result_id == result_id)
            .order_by(TestStepResult.position)
        ).scalars()
    )


def step_results_of(s: Session, result_ids: Sequence[UUID]) -> dict[UUID, list[TestStepResult]]:
    out: dict[UUID, list[TestStepResult]] = {r: [] for r in result_ids}
    if not result_ids:
        return out
    rows = s.execute(
        select(TestStepResult)
        .where(TestStepResult.result_id.in_(result_ids))
        .order_by(TestStepResult.result_id, TestStepResult.position)
    ).scalars()
    for row in rows:
        out[row.result_id].append(row)
    return out


def step_result(s: Session, result_id: UUID, step_id: UUID) -> TestStepResult | None:
    return s.execute(
        select(TestStepResult).where(TestStepResult.result_id == result_id, TestStepResult.step_id == step_id)
    ).scalar_one_or_none()


def step_result_by_id(s: Session, ctx: AccessContext, step_result_id: UUID) -> TestStepResult | None:
    return s.execute(
        _scope(select(TestStepResult), TestStepResult, ctx).where(TestStepResult.id == step_result_id)
    ).scalar_one_or_none()


def queue_runs(
    s: Session, ctx: AccessContext, cycle_id: UUID, *, assignee_id: UUID | None, open_only: bool
) -> list[UUID]:
    """Active runs of a cycle in position order, optionally mine and/or not finalized (docs/02 §7.4)."""
    stmt = _scope(select(TestRun.id), TestRun, ctx).where(TestRun.cycle_id == cycle_id, _ACTIVE)
    if assignee_id is not None:
        stmt = stmt.where(TestRun.assignee_id == assignee_id)
    if open_only:
        stmt = stmt.where(TestRun.status.in_([RunStatus.not_run, RunStatus.in_progress]))
    return list(s.execute(stmt.order_by(TestRun.position, TestRun.id)).scalars())


# -- My Work (org-level, across the caller's projects; docs/02 §7.5) -------------------------------


def my_run_counts(
    s: Session, org_id: UUID, project_ids: Sequence[UUID], user_id: UUID
) -> list[tuple[TestCycle, str, int, int]]:
    """(cycle, run status, count, needs-retest count) of my active runs in planned/active cycles."""
    if not project_ids:
        return []
    rows = s.execute(
        select(
            TestCycle,
            TestRun.status,
            func.count(),
            func.count().filter(TestRun.needs_retest.is_(True)),
        )
        .join(TestCycle, TestCycle.id == TestRun.cycle_id)
        .where(
            TestRun.organization_id == org_id,
            TestRun.project_id.in_(project_ids),
            TestRun.assignee_id == user_id,
            _ACTIVE,
            TestCycle.status.in_([CycleStatus.planned, CycleStatus.active]),
            TestCycle.archived_at.is_(None),
        )
        .group_by(TestCycle.id, TestRun.status)
    ).all()
    return [(c, st.value, int(n), int(rt)) for c, st, n, rt in rows]


def my_next_runs(s: Session, org_id: UUID, cycle_ids: Sequence[UUID], user_id: UUID) -> dict[UUID, UUID]:
    """First open run (by position) of mine per cycle: where "Continue / Start" goes."""
    if not cycle_ids:
        return {}
    rows = s.execute(
        select(TestRun.cycle_id, TestRun.id)
        .where(
            TestRun.organization_id == org_id,
            TestRun.cycle_id.in_(cycle_ids),
            TestRun.assignee_id == user_id,
            _ACTIVE,
            TestRun.status.in_([RunStatus.not_run, RunStatus.in_progress]),
        )
        .order_by(TestRun.cycle_id, TestRun.position, TestRun.id)
    ).all()
    out: dict[UUID, UUID] = {}
    for c, r in rows:
        out.setdefault(c, r)
    return out


def my_finished_counts(
    s: Session, org_id: UUID, project_ids: Sequence[UUID], user_id: UUID, since: Any
) -> dict[str, int]:
    """Final attempts I recorded since `since`, by status ("My week")."""
    if not project_ids:
        return {}
    rows = s.execute(
        select(TestResult.status, func.count())
        .where(
            TestResult.organization_id == org_id,
            TestResult.project_id.in_(project_ids),
            TestResult.executed_by == user_id,
            TestResult.state == ResultState.final,
            TestResult.finished_at >= since,
        )
        .group_by(TestResult.status)
    ).all()
    return {st.value: int(n) for st, n in rows if st is not None}


def all_runs_with_attempts(s: Session, ctx: AccessContext) -> list[tuple[TestRun, list[TestResult]]]:
    """Every run of the project with its attempts (consistency check, docs/04 §5.6)."""
    runs = list(s.execute(_scope(select(TestRun), TestRun, ctx)).scalars())
    by_run: dict[UUID, list[TestResult]] = {r.id: [] for r in runs}
    for res in s.execute(_scope(select(TestResult), TestResult, ctx)).scalars():
        by_run.setdefault(res.run_id, []).append(res)
    return [(r, by_run[r.id]) for r in runs]


def projects_with_runs(s: Session) -> list[tuple[UUID, UUID]]:
    """System job helper (no user context): each tenant is then read through its own scoped context."""
    rows = s.execute(select(TestRun.organization_id, TestRun.project_id).distinct()).all()
    return [(o, p) for o, p in rows]


# -- retest requests from bug links (BR-21, M5) ----------------------------------------------------


def retest_eligible_runs(s: Session, ctx: AccessContext, run_ids: Sequence[UUID]) -> list[TestRun]:
    """Runs of the project that are not superseded and whose cycle is not closed or archived."""
    if not run_ids:
        return []
    stmt = (
        _scope(select(TestRun), TestRun, ctx)
        .join(TestCycle, TestCycle.id == TestRun.cycle_id)
        .where(
            TestRun.id.in_(list(run_ids)),
            _ACTIVE,
            TestCycle.status.in_([CycleStatus.planned, CycleStatus.active]),
            TestCycle.archived_at.is_(None),
        )
        .order_by(TestRun.id)
        .with_for_update(of=TestRun)
    )
    return list(s.execute(stmt).scalars())
