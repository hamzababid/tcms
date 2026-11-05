"""Test plans (docs/06 §4.5)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from tcms.api.deps import (
    get_read_uow,
    get_uow,
    project_context,
    project_context_from,
    resolve_row_version,
)
from tcms.api.idempotency import Idempotency, idempotency
from tcms.core.context import AccessContext
from tcms.core.errors import NotFound
from tcms.core.pagination import Page, PageParams
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as execution_queries
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.planning import queries as pq
from tcms.planning import schemas as s
from tcms.planning import service
from tcms.planning.service import PlanData
from tcms.testdesign import queries as testdesign_queries

router = APIRouter(prefix="/api/v1", tags=["test-plans"])

PlanCtx = Depends(project_context_from("test_plan", "plan_id"))


def _etag(response: Response, rv: int) -> None:
    response.headers["ETag"] = f'"{rv}"'


def _user_ref(uow: UnitOfWork, user_id: UUID | None) -> UserRef | None:
    if user_id is None:
        return None
    found = identity_queries.user_refs(uow.session, {user_id})
    v = found.get(user_id)
    return UserRef(**vars(v)) if v else None


def _plan_read(uow: UnitOfWork, ctx: AccessContext, plan_id: UUID) -> s.PlanRead:
    d = pq.plan_detail(uow.session, ctx, plan_id)
    if d is None:
        raise NotFound()
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
        owner=_user_ref(uow, d.owner_id),
        start_date=d.start_date,
        end_date=d.end_date,
        case_count=d.case_count,
        requirement_count=d.requirement_count,
        allowed_transitions=d.allowed_transitions,
        archived=d.archived,
        created_at=d.created_at,
        updated_at=d.updated_at,
        row_version=d.row_version,
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
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[s.PlanListItem]:
    """US-070 / FR-PLN-001."""
    ctx.require("project.view")
    rows, total = pq.list_plans(
        uow.session, ctx, dict(request.query_params), PageParams(page=page, page_size=page_size)
    )
    refs = identity_queries.user_refs(uow.session, {r.owner_id for r in rows})
    return Page[s.PlanListItem](
        items=[
            s.PlanListItem(
                id=r.id,
                key=r.key,
                name=r.name,
                type=r.type,
                status=r.status,
                release_id=r.release_id,
                owner=UserRef(**vars(refs[r.owner_id])) if r.owner_id in refs else None,
                case_count=r.case_count,
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
    uow: UnitOfWork = Depends(get_uow),
    guard: Idempotency = Depends(idempotency("create_plan")),
) -> Any:
    """US-070 / FR-PLN-001 (TCMS-050)."""
    if (replay := guard.replay(body)) is not None:
        return replay
    plan = service.create_plan(
        uow,
        ctx,
        PlanData(
            name=body.name,
            type=body.type,
            release_id=body.release_id,
            objectives=body.objectives,
            scope_in=body.scope_in,
            scope_out=body.scope_out,
            entry_criteria=body.entry_criteria,
            exit_criteria_notes=body.exit_criteria_notes,
            acceptance_criteria=body.acceptance_criteria,
            exit_rules=[r.model_dump() for r in body.exit_rules],
            risks=[r.model_dump() for r in body.risks],
            environment_ids=body.environment_ids,
            member_ids=body.member_ids,
            start_date=body.start_date,
            end_date=body.end_date,
            owner_id=body.owner_id,
        ),
    )
    uow.session.flush()
    out = _plan_read(uow, ctx, plan.id)
    guard.store(201, out)
    return out


@router.get("/test-plans/{plan_id}", response_model=s.PlanRead)
def get_plan(
    plan_id: UUID, response: Response, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> s.PlanRead:
    ctx.require("project.view")
    out = _plan_read(uow, ctx, plan_id)
    _etag(response, out.row_version)
    return out


@router.patch("/test-plans/{plan_id}", response_model=s.PlanRead)
def patch_plan(
    plan_id: UUID,
    body: s.PlanPatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.PlanRead:
    fields = {k: getattr(body, k) for k in body.model_fields_set if k != "row_version"}
    if "exit_rules" in fields and fields["exit_rules"] is not None:
        fields["exit_rules"] = [r.model_dump() for r in body.exit_rules or []]
    if "risks" in fields and fields["risks"] is not None:
        fields["risks"] = [r.model_dump() for r in body.risks or []]
    service.update_plan(
        uow, ctx, plan_id, row_version=resolve_row_version(body.row_version, if_match), fields=fields
    )
    uow.session.flush()
    out = _plan_read(uow, ctx, plan_id)
    _etag(response, out.row_version)
    return out


@router.post("/test-plans/{plan_id}/cases", response_model=s.AddCasesResponse)
def add_cases(
    plan_id: UUID, body: s.AddCasesRequest, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.AddCasesResponse:
    """FR-PLN-002 / BR-13 (TCMS-051)."""
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
    uow.session.flush()
    return s.AddCasesResponse(
        added=result.added, skipped=[s.Skipped(key=k, reason=r) for k, r in result.skipped]
    )


@router.delete("/test-plans/{plan_id}/cases", response_model=s.AddCasesResponse)
def remove_cases(
    plan_id: UUID, body: s.CaseIdsRequest, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.AddCasesResponse:
    removed = service.remove_cases(uow, ctx, plan_id, case_ids=body.case_ids)
    uow.session.flush()
    return s.AddCasesResponse(added=-removed, skipped=[])


@router.get("/test-plans/{plan_id}/cases", response_model=Page[s.PlanCaseItem])
def list_plan_cases(
    plan_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[s.PlanCaseItem]:
    """US-074 / docs/02 §6.2: each case with its latest result in every linked cycle."""
    ctx.require("project.view")
    all_ids = pq.plan_case_ids(uow.session, ctx, plan_id)
    total = len(all_ids)
    start = (page - 1) * page_size
    page_ids = all_ids[start : start + page_size]
    refs = testdesign_queries.case_refs(uow.session, ctx, page_ids)
    items: list[s.PlanCaseItem] = []
    for cid in page_ids:
        ref = refs.get(cid)
        if ref is None:
            continue
        results = execution_queries.case_executions(uow.session, ctx, cid)
        items.append(
            s.PlanCaseItem(
                case_id=cid,
                key=ref.key,
                title=ref.title,
                status=ref.status,
                results=[
                    s.PlanCaseResult(cycle_id=r.cycle_id, cycle_key=r.cycle_key, status=r.status)
                    for r in results
                    if not r.superseded
                ],
            )
        )
    return Page[s.PlanCaseItem](items=items, page=page, page_size=page_size, total=total)


@router.post("/test-plans/{plan_id}/requirements", response_model=s.AddCasesResponse)
def link_requirements(
    plan_id: UUID,
    body: s.RequirementIdsRequest,
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.AddCasesResponse:
    """FR-PLN-003."""
    added = service.link_requirements(uow, ctx, plan_id, requirement_ids=body.requirement_ids)
    uow.session.flush()
    return s.AddCasesResponse(added=added, skipped=[])


@router.delete("/test-plans/{plan_id}/requirements", response_model=s.AddCasesResponse)
def unlink_requirements(
    plan_id: UUID,
    body: s.RequirementIdsRequest,
    ctx: AccessContext = PlanCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.AddCasesResponse:
    removed = service.unlink_requirements(uow, ctx, plan_id, requirement_ids=body.requirement_ids)
    uow.session.flush()
    return s.AddCasesResponse(added=-removed, skipped=[])


@router.post("/test-plans/{plan_id}/clone", response_model=s.PlanRead, status_code=status.HTTP_201_CREATED)
def clone_plan(
    plan_id: UUID, body: s.CloneRequest, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.PlanRead:
    """US-073 / FR-PLN-006."""
    clone = service.clone_plan(uow, ctx, plan_id, name=body.name)
    uow.session.flush()
    return _plan_read(uow, ctx, clone.id)


@router.post("/test-plans/{plan_id}/archive", response_model=s.PlanRead)
def archive_plan(
    plan_id: UUID, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.PlanRead:
    service.archive_plan(uow, ctx, plan_id)
    uow.session.flush()
    return _plan_read(uow, ctx, plan_id)
