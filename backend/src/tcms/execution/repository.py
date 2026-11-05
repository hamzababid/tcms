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
