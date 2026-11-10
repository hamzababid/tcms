"""Test plans (docs/06 §4.5)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from tcms.api.deps import (
    ReadUow,
    Uow,
    project_context,
    project_context_from,
    resolve_row_version,
)
from tcms.api.idempotency import Idempotency, idempotency
from tcms.core.context import AccessContext
from tcms.core.errors import InvalidInclude, NotFound
from tcms.core.pagination import Page, PageParams
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as execution_queries
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.planning import queries as pq
from tcms.planning import schemas as s
from tcms.planning import service
from tcms.planning.service import PlanData
from tcms.reporting.metrics import ExecutionSummary
from tcms.testdesign import queries as testdesign_queries

router = APIRouter(prefix="/api/v1", tags=["test-plans"])

PlanCtx = Depends(project_context_from("test_plan", "plan_id"))
PLAN_INCLUDES = frozenset({"cases", "requirements", "cycles"})


def _etag(response: Response, rv: int) -> None:
    response.headers["ETag"] = f'"{rv}"'


def _users(uow: UnitOfWork, ids_: set[UUID]) -> dict[UUID, UserRef]:
    return {k: UserRef(**vars(v)) for k, v in identity_queries.user_refs(uow.session, ids_).items()}


def _includes(raw: str | None) -> frozenset[str]:
    wanted = frozenset(x.strip() for x in (raw or "").split(",") if x.strip())
    unknown = wanted - PLAN_INCLUDES
    if unknown:
        raise InvalidInclude(f"Unknown include: {', '.join(sorted(unknown))}")
    return wanted


def plan_read(
    uow: UnitOfWork, ctx: AccessContext, plan_id: UUID, includes: frozenset[str] = frozenset()
) -> s.PlanRead:
    se = uow.session
    d = pq.plan_detail(se, ctx, plan_id)
    if d is None:
        raise NotFound()
    cycles = None
    if "cycles" in includes:
        rows = execution_queries.cycles_of_plan(se, ctx, plan_id)
        counts = execution_queries.status_counts(se, ctx, [c.id for c in rows])
        cycles = []
        for c in rows:
            m = ExecutionSummary.from_counts(counts.get(c.id, {}))
            cycles.append(
                s.PlanCycle(
                    id=c.id,
                    key=c.key,
                    name=c.name,
                    status=c.status,
                    total=m.total,
                    executed=m.executed,
                    passed=m.passed,
                )
            )
    return s.PlanRead(
        id=d.id,
        key=d.key,
        project_id=ctx.pid,
        name=d.name,
        type=d.type,
        status=d.status,
        release_id=d.release_id,
        objectives=d.objectives,
        scope_in=d.scope_in,
        scope_out=d.scope_out,
        entry_criteria=d.entry_criteria,
        exit_criteria_notes=d.exit_criteria_notes,
        acceptance_criteria=d.acceptance_criteria,
        exit_rules=d.exit_rules,
        risks=d.risks,
        environment_ids=d.environment_ids,
        member_ids=d.member_ids,
        owner=_users(uow, {d.owner_id}).get(d.owner_id),
        start_date=d.start_date,
        end_date=d.end_date,
        case_count=d.case_count,
        requirement_count=d.requirement_count,
        allowed_transitions=d.allowed_transitions,
        archived=d.archived,
        created_at=d.created_at,
        updated_at=d.updated_at,
        row_version=d.row_version,
        case_ids=pq.plan_case_ids(se, ctx, plan_id) if "cases" in includes else None,
        requirement_ids=pq.plan_requirement_ids(se, ctx, plan_id) if "requirements" in includes else None,
        cycles=cycles,
    )


def _data(body: s.PlanCreate) -> PlanData:
    return PlanData(
        name=body.name,
        type=body.type,
        release_id=body.release_id,
        objectives=body.objectives,
        scope_in=body.scope_in,
        scope_out=body.scope_out,
        entry_criteria=body.entry_criteria,
        exit_criteria_notes=body.exit_criteria_notes,
        acceptance_criteria=body.acceptance_criteria,
        exit_rules=[r.model_dump(exclude_none=True) for r in body.exit_rules],
        risks=[r.model_dump() for r in body.risks],
        environment_ids=body.environment_ids,
        member_ids=body.member_ids,
        start_date=body.start_date,
        end_date=body.end_date,
        owner_id=body.owner_id,
    )


@router.get("/projects/{project_id}/test-plans", response_model=Page[s.PlanListItem])
def list_plans(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    status_: str | None = Query(default=None, alias="status"),
    type_: str | None = Query(default=None, alias="type"),
    release_id: UUID | None = None,
    owner_id: UUID | None = None,
    include_archived: bool = False,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> Page[s.PlanListItem]:
    """US-070 / FR-PLN-001: filters status, type, release_id, owner_id, q."""
    ctx.require("project.view")
    rows, total = pq.list_plans(
        uow.session, ctx, dict(request.query_params), PageParams(page=page, page_size=page_size)
    )
    users = _users(uow, {r.owner_id for r in rows})
    return Page[s.PlanListItem](
        items=[
            s.PlanListItem(
                id=r.id,
                key=r.key,
                name=r.name,
                type=r.type,
                status=r.status,
                release_id=r.release_id,
                owner=users.get(r.owner_id),
                case_count=r.case_count,
                start_date=r.start_date,
                end_date=r.end_date,
                archived=r.archived,
                updated_at=r.updated_at,
                row_version=r.row_version,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/projects/{project_id}/test-plans", response_model=s.PlanRead, status_code=status.HTTP_201_CREATED
)
def create_plan(
    body: s.PlanCreate,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Uow,
    guard: Idempotency = Depends(idempotency("create_plan")),
) -> Any:
    """US-070 / FR-PLN-001/005 (TCMS-050)."""
    if (replay := guard.replay(body)) is not None:
        return replay
    plan = service.create_plan(uow, ctx, _data(body))
    uow.session.flush()
    out = plan_read(uow, ctx, plan.id)
    guard.store(201, out)
    return out


@router.get("/test-plans/{plan_id}", response_model=s.PlanRead)
def get_plan(
    plan_id: UUID,
    response: Response,
    include: str | None = Query(default=None, max_length=100),
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = ReadUow,
) -> s.PlanRead:
    """`?include=cases,requirements,cycles` (docs/06 §4.5)."""
    ctx.require("project.view")
    out = plan_read(uow, ctx, plan_id, _includes(include))
    _etag(response, out.row_version)
    return out


@router.patch("/test-plans/{plan_id}", response_model=s.PlanRead)
def patch_plan(
    plan_id: UUID,
    body: s.PlanPatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Uow,
) -> s.PlanRead:
    fields = {k: getattr(body, k) for k in body.model_fields_set if k != "row_version"}
    if fields.get("exit_rules") is not None:
        fields["exit_rules"] = [r.model_dump(exclude_none=True) for r in body.exit_rules or []]
    if fields.get("risks") is not None:
        fields["risks"] = [r.model_dump() for r in body.risks or []]
    service.update_plan(
        uow, ctx, plan_id, row_version=resolve_row_version(body.row_version, if_match), fields=fields
    )
    uow.session.flush()
    out = plan_read(uow, ctx, plan_id)
    _etag(response, out.row_version)
    return out


@router.post("/test-plans/{plan_id}/cases", response_model=s.AddCasesResponse)
def add_cases(
    plan_id: UUID, body: s.AddCasesRequest, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Uow
) -> s.AddCasesResponse:
    """FR-PLN-002 / BR-13 (TCMS-051): `{added, skipped[]}`."""
    result = service.add_cases(
        uow,
        ctx,
        plan_id,
        case_ids=body.case_ids,
        folder_ids=body.folder_ids,
        include_subfolders=body.include_subfolders,
        tags=body.tags,
        saved_view_id=body.saved_view_id,
    )
    return s.AddCasesResponse(
        added=result.added, skipped=[s.Skipped(key=k, reason=r) for k, r in result.skipped]
    )


@router.delete("/test-plans/{plan_id}/cases", response_model=s.CountResponse)
def remove_cases(
    plan_id: UUID, body: s.CaseIdsRequest, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Uow
) -> s.CountResponse:
    """Removing cases does not change existing cycles (docs/02 §6.2)."""
    return s.CountResponse(count=service.remove_cases(uow, ctx, plan_id, case_ids=body.case_ids))


@router.get("/test-plans/{plan_id}/cases", response_model=Page[s.PlanCaseItem])
def list_plan_cases(
    plan_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = ReadUow,
) -> Page[s.PlanCaseItem]:
    """US-074 / docs/02 §6.2: each case with its status in every cycle created from the plan."""
    ctx.require("project.view")
    se = uow.session
    all_ids = pq.plan_case_ids(se, ctx, plan_id)
    refs = testdesign_queries.case_refs(se, ctx, all_ids)
    ordered = sorted((refs[c] for c in all_ids if c in refs), key=lambda r: r.key_num)
    start = (page - 1) * page_size
    page_refs = ordered[start : start + page_size]
    results = execution_queries.plan_case_results(se, ctx, plan_id, [r.id for r in page_refs])
    items = [
        s.PlanCaseItem(
            case_id=r.id,
            key=r.key,
            title=r.title,
            status=r.status,
            priority=r.priority,
            folder_id=r.folder_id,
            results=[
                s.PlanCaseResult(cycle_id=x.cycle_id, cycle_key=x.cycle_key, status=x.status)
                for x in results[r.id]
            ],
        )
        for r in page_refs
    ]
    return Page[s.PlanCaseItem](items=items, page=page, page_size=page_size, total=len(ordered))


@router.post("/test-plans/{plan_id}/requirements", response_model=s.CountResponse)
def link_requirements(
    plan_id: UUID,
    body: s.RequirementRefsRequest,
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Uow,
) -> s.CountResponse:
    """FR-PLN-003 / R-122 (ADR-024): requirement references the plan must cover; new ones are registered."""
    return s.CountResponse(count=service.link_requirements(uow, ctx, plan_id, references=body.references))


@router.delete("/test-plans/{plan_id}/requirements", response_model=s.CountResponse)
def unlink_requirements(
    plan_id: UUID,
    body: s.RequirementIdsRequest,
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Uow,
) -> s.CountResponse:
    return s.CountResponse(
        count=service.unlink_requirements(uow, ctx, plan_id, requirement_ids=body.requirement_ids)
    )


@router.post("/test-plans/{plan_id}/clone", response_model=s.PlanRead, status_code=status.HTTP_201_CREATED)
def clone_plan(
    plan_id: UUID, body: s.CloneRequest, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Uow
) -> s.PlanRead:
    """US-073 / FR-PLN-006: everything except cycles; draft; "Copy of …"."""
    clone = service.clone_plan(uow, ctx, plan_id, name=body.name)
    uow.session.flush()
    return plan_read(uow, ctx, clone.id)


@router.post("/test-plans/{plan_id}/archive", response_model=s.PlanRead)
def archive_plan(plan_id: UUID, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Uow) -> s.PlanRead:
    service.archive_plan(uow, ctx, plan_id)
    uow.session.flush()
    return plan_read(uow, ctx, plan_id)
