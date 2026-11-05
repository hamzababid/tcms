"""Execution data access (private to the module). Every query is organization- and project-scoped."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.enums import ResultState
from tcms.execution.models import TestCycle, TestResult, TestRun

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
    s: Session, ctx: AccessContext, cycle_id: UUID, *, include_superseded: bool = False
) -> list[TestRun]:
    stmt = _scope(select(TestRun), TestRun, ctx).where(TestRun.cycle_id == cycle_id)
    if not include_superseded:
        stmt = stmt.where(_ACTIVE)
    return list(s.execute(stmt.order_by(TestRun.position, TestRun.id)).scalars())


def runs_by_ids(
    s: Session, ctx: AccessContext, run_ids: Sequence[UUID], *, for_update: bool = False
) -> list[TestRun]:
    if not run_ids:
        return []
    stmt = _scope(select(TestRun), TestRun, ctx).where(TestRun.id.in_(run_ids))
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
        status="not_run",
        created_at=now,
        created_by=actor,
        updated_at=now,
        updated_by=actor,
    )
    s.add(r)
    return r


def run_has_any_attempt(s: Session, run_id: UUID) -> bool:
    return s.execute(select(TestResult.id).where(TestResult.run_id == run_id).limit(1)).first() is not None


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


def draft_runs(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[TestRun]:
    """Active runs in the cycle that carry a draft attempt (for the close dialog, docs/02 §7.1)."""
    draft_run_ids = select(TestResult.run_id).where(TestResult.state == ResultState.draft).scalar_subquery()
    stmt = (
        _scope(select(TestRun), TestRun, ctx)
        .where(TestRun.cycle_id == cycle_id, _ACTIVE, TestRun.id.in_(draft_run_ids))
        .order_by(TestRun.position)
    )
    return list(s.execute(stmt).scalars())


def status_counts(s: Session, ctx: AccessContext, cycle_id: UUID) -> dict[str, int]:
    """Counts by run status over non-superseded runs (docs/05 §5)."""
    rows = s.execute(
        _scope(select(TestRun.status, func.count()), TestRun, ctx)
        .where(TestRun.cycle_id == cycle_id, _ACTIVE)
        .group_by(TestRun.status)
    ).all()
    return {status.value: int(n) for status, n in rows}


def assignee_counts(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[tuple[UUID | None, str, int]]:
    rows = s.execute(
        _scope(select(TestRun.assignee_id, TestRun.status, func.count()), TestRun, ctx)
        .where(TestRun.cycle_id == cycle_id, _ACTIVE)
        .group_by(TestRun.assignee_id, TestRun.status)
    ).all()
    return [(a, st.value, int(n)) for a, st, n in rows]
