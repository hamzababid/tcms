"""Planning data access (private to the module). Every query is organization- and project-scoped."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.planning.models import PlanRequirementRef, TestPlan, TestPlanCase, TestPlanEnvironment


def _scope(stmt: Any, model: Any, ctx: AccessContext) -> Any:
    return stmt.where(model.organization_id == ctx.principal.organization_id, model.project_id == ctx.pid)


# -- plans ----------------------------------------------------------------------------------------


def plan(s: Session, ctx: AccessContext, plan_id: UUID, *, for_update: bool = False) -> TestPlan | None:
    stmt = _scope(select(TestPlan), TestPlan, ctx).where(TestPlan.id == plan_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def plan_list_stmt(ctx: AccessContext) -> Select[Any]:
    stmt: Select[Any] = _scope(select(TestPlan), TestPlan, ctx)
    return stmt


def name_taken(s: Session, ctx: AccessContext, name: str, *, exclude: UUID | None = None) -> bool:
    from sqlalchemy import func

    stmt = _scope(select(TestPlan.id), TestPlan, ctx).where(func.lower(TestPlan.name) == name.lower())
    if exclude is not None:
        stmt = stmt.where(TestPlan.id != exclude)
    return s.execute(stmt.limit(1)).first() is not None


# -- plan cases -----------------------------------------------------------------------------------


def case_ids(s: Session, ctx: AccessContext, plan_id: UUID) -> list[UUID]:
    return list(s.execute(select(TestPlanCase.test_case_id).where(TestPlanCase.plan_id == plan_id)).scalars())


def add_case(
    s: Session, ctx: AccessContext, plan_id: UUID, case_id: UUID, actor: UUID | None, now: Any
) -> None:
    s.add(
        TestPlanCase(
            plan_id=plan_id,
            test_case_id=case_id,
            organization_id=ctx.principal.organization_id,
            project_id=ctx.pid,
            added_at=now,
            added_by=actor,
        )
    )


def remove_cases(s: Session, plan_id: UUID, case_ids: Sequence[UUID]) -> int:
    if not case_ids:
        return 0
    present = set(
        s.execute(
            select(TestPlanCase.test_case_id).where(
                TestPlanCase.plan_id == plan_id, TestPlanCase.test_case_id.in_(case_ids)
            )
        ).scalars()
    )
    if present:
        s.execute(
            delete(TestPlanCase).where(
                TestPlanCase.plan_id == plan_id, TestPlanCase.test_case_id.in_(present)
            )
        )
    return len(present)


# -- plan requirements ----------------------------------------------------------------------------


def requirement_ids(s: Session, plan_id: UUID) -> list[UUID]:
    """Requirement references of the plan (ADR-024)."""
    return list(
        s.execute(select(PlanRequirementRef.ref_id).where(PlanRequirementRef.plan_id == plan_id)).scalars()
    )


def add_requirement(
    s: Session, ctx: AccessContext, plan_id: UUID, requirement_id: UUID, actor: UUID | None, now: Any
) -> None:
    s.add(
        PlanRequirementRef(
            plan_id=plan_id,
            ref_id=requirement_id,
            organization_id=ctx.principal.organization_id,
            project_id=ctx.pid,
            created_at=now,
            created_by=actor,
        )
    )


def remove_requirements(s: Session, plan_id: UUID, requirement_ids: Sequence[UUID]) -> int:
    if not requirement_ids:
        return 0
    res = s.execute(
        delete(PlanRequirementRef).where(
            PlanRequirementRef.plan_id == plan_id, PlanRequirementRef.ref_id.in_(list(requirement_ids))
        )
    )
    return int(getattr(res, "rowcount", 0) or 0)


def plan_ids_with_ref(s: Session, ctx: AccessContext, ref_id: UUID) -> list[UUID]:
    return list(
        s.execute(
            select(PlanRequirementRef.plan_id).where(
                PlanRequirementRef.project_id == ctx.pid, PlanRequirementRef.ref_id == ref_id
            )
        ).scalars()
    )


# -- plan environments ----------------------------------------------------------------------------


def environment_ids(s: Session, plan_id: UUID) -> list[UUID]:
    return list(
        s.execute(
            select(TestPlanEnvironment.environment_id).where(TestPlanEnvironment.plan_id == plan_id)
        ).scalars()
    )


def set_environments(s: Session, plan_id: UUID, environment_ids: Iterable[UUID]) -> None:
    s.execute(delete(TestPlanEnvironment).where(TestPlanEnvironment.plan_id == plan_id))
    for eid in environment_ids:
        s.add(TestPlanEnvironment(plan_id=plan_id, environment_id=eid))
