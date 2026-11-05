"""Public read functions of the planning module (routers and modules above planning)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.enums import PlanStatus, PlanType
from tcms.core.pagination import FilterField, PageParams, paginate, parse_filters, parse_sort
from tcms.planning import repository as repo
from tcms.planning import rules
from tcms.planning.models import TestPlan, TestPlanCase

PLAN_FILTERS: Mapping[str, FilterField] = {
    "status": FilterField(TestPlan.status, kind="enum", choices=frozenset(s.value for s in PlanStatus)),
    "type": FilterField(TestPlan.type, kind="enum", choices=frozenset(t.value for t in PlanType)),
    "release_id": FilterField(TestPlan.release_id, kind="uuid"),
    "owner_id": FilterField(TestPlan.owner_id, kind="uuid"),
}
PLAN_SORTS: Mapping[str, ColumnElement[Any]] = {
    "key": TestPlan.key_num,  # type: ignore[dict-item]
    "name": func.lower(TestPlan.name),
    "status": TestPlan.status,  # type: ignore[dict-item]
    "updated_at": TestPlan.updated_at,  # type: ignore[dict-item]
    "created_at": TestPlan.created_at,  # type: ignore[dict-item]
}


@dataclass(frozen=True)
class PlanSummary:
    id: UUID
    key: str
    name: str
    type: str
    status: str
    release_id: UUID | None
    owner_id: UUID
    objectives: str | None
    scope_in: str | None
    scope_out: str | None
    entry_criteria: str | None
    exit_criteria_notes: str | None
    acceptance_criteria: str | None
    exit_rules: list[Any]
    risks: list[Any]
    environment_ids: list[UUID]
    member_ids: list[UUID]
    start_date: date | None
    end_date: date | None
    case_count: int
    requirement_count: int
    allowed_transitions: list[str]
    archived: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


def _summary(s: Session, p: TestPlan) -> PlanSummary:
    return PlanSummary(
        id=p.id,
        key=p.key,
        name=p.name,
        type=p.type.value,
        status=p.status.value,
        release_id=p.release_id,
        owner_id=p.owner_id,
        objectives=p.objectives,
        scope_in=p.scope_in,
        scope_out=p.scope_out,
        entry_criteria=p.entry_criteria,
        exit_criteria_notes=p.exit_criteria_notes,
        acceptance_criteria=p.acceptance_criteria,
        exit_rules=list(p.exit_rules),
        risks=list(p.risks),
        environment_ids=repo.environment_ids(s, p.id),
        member_ids=list(p.member_ids),
        start_date=p.start_date,
        end_date=p.end_date,
        case_count=_count_cases(s, p.id),
        requirement_count=len(repo.requirement_ids(s, p.id)),
        allowed_transitions=sorted(t.value for t in rules.allowed_plan_targets(p.status)),
        archived=p.archived_at is not None,
        created_at=p.created_at,
        updated_at=p.updated_at,
        row_version=p.row_version,
    )


def _count_cases(s: Session, plan_id: UUID) -> int:
    return int(
        s.execute(
            select(func.count()).select_from(TestPlanCase).where(TestPlanCase.plan_id == plan_id)
        ).scalar_one()
    )


def plan_detail(s: Session, ctx: AccessContext, plan_id: UUID) -> PlanSummary | None:
    p = repo.plan(s, ctx, plan_id)
    return _summary(s, p) if p else None


def list_plans(
    s: Session, ctx: AccessContext, params: Mapping[str, str], page: PageParams
) -> tuple[list[PlanSummary], int]:
    stmt: Select[Any] = repo.plan_list_stmt(ctx)
    conditions = parse_filters(params, PLAN_FILTERS)
    if conditions:
        stmt = stmt.where(*conditions)
    if "status" not in params:
        stmt = stmt.where(TestPlan.status != PlanStatus.archived)
    q = (params.get("q") or "").strip()
    if q:
        stmt = stmt.where(or_(TestPlan.name.icontains(q, autoescape=True), TestPlan.key.icontains(q)))
    stmt = stmt.order_by(*parse_sort(params.get("sort"), PLAN_SORTS, default="key"))
    rows, total = paginate(s, stmt, page)
    return [_summary(s, r[0]) for r in rows], total


def plan_case_ids(s: Session, ctx: AccessContext, plan_id: UUID) -> list[UUID]:
    return repo.case_ids(s, ctx, plan_id)


def plan_requirement_ids(s: Session, ctx: AccessContext, plan_id: UUID) -> list[UUID]:
    return repo.requirement_ids(s, plan_id)


def owning_project_of_plan(s: Session, plan_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(TestPlan.organization_id, TestPlan.project_id).where(TestPlan.id == plan_id)
    ).first()
    return (row[0], row[1]) if row else None
