"""Cycles and runs (docs/06 §4.6)."""

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
from tcms.execution import queries as eq
from tcms.execution import schemas as s
from tcms.execution import service
from tcms.execution.service import CycleData, Selection
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef

router = APIRouter(prefix="/api/v1", tags=["cycles"])

CycleCtx = Depends(project_context_from("test_cycle", "cycle_id"))
RunCtx = Depends(project_context_from("test_run", "run_id"))


def _etag(response: Response, rv: int) -> None:
    response.headers["ETag"] = f'"{rv}"'


def _ref(uow: UnitOfWork, user_id: UUID | None) -> UserRef | None:
    if user_id is None:
        return None
    found = identity_queries.user_refs(uow.session, {user_id})
    v = found.get(user_id)
    return UserRef(**vars(v)) if v else None


def _summary(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> s.CycleSummary:
    data = eq.cycle_summary(uow.session, ctx, cycle_id)
    return s.CycleSummary(total=data.total, by_status=data.by_status)


def _cycle_read(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> s.CycleRead:
    c = eq.cycle(uow.session, ctx, cycle_id)
    if c is None:
        raise NotFound()
    progress = eq.cycle_progress_by_assignee(uow.session, ctx, cycle_id)
    refs = identity_queries.user_refs(
        uow.session, {p.assignee_id for p in progress if p.assignee_id} | {c.owner_id}
    )
    return s.CycleRead(
        id=c.id,
        key=c.key,
        project_id=ctx.pid,
        name=c.name,
        description=c.description,
        release_id=c.release_id,
        plan_id=c.plan_id,
        environment_id=c.environment_id,
        build=c.build,
        status=c.status,
        start_date=c.start_date,
        due_date=c.due_date,
        owner=UserRef(**vars(refs[c.owner_id])) if c.owner_id in refs else None,
        runs_pending=c.runs_pending,
        summary=_summary(uow, ctx, cycle_id),
        progress_by_assignee=[
            s.AssigneeProgress(
                assignee=UserRef(**vars(refs[p.assignee_id])) if p.assignee_id in refs else None,
                by_status=p.by_status,
                total=p.total,
            )
            for p in progress
        ],
        archived=c.archived_at is not None,
        created_at=c.created_at,
        updated_at=c.updated_at,
        row_version=c.row_version,
    )


def _selection(body: s.SelectionIn) -> Selection:
    return Selection(
        from_plan=body.from_plan,
        case_ids=body.case_ids,
        folder_ids=body.folder_ids,
        tags=body.tags,
        priorities=body.priorities,
    )


def _skipped(pairs: list[tuple[str, str]]) -> list[s.Skipped]:
    return [s.Skipped(key=k, reason=r) for k, r in pairs]


# -- cycles ---------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/cycles", response_model=Page[s.CycleListItem])
def list_cycles(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    status_: str | None = Query(default=None, alias="status"),
    release_id: UUID | None = None,
    plan_id: UUID | None = None,
    environment_id: UUID | None = None,
    owner_id: UUID | None = None,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[s.CycleListItem]:
    """US-080 / FR-EXE-001."""
    ctx.require("project.view")
    rows, total = eq.list_cycles(
        uow.session, ctx, dict(request.query_params), PageParams(page=page, page_size=page_size)
    )
    return Page[s.CycleListItem](
        items=[
            s.CycleListItem(
                id=c.id,
                key=c.key,
                name=c.name,
                status=c.status,
                release_id=c.release_id,
                plan_id=c.plan_id,
                environment_id=c.environment_id,
                due_date=c.due_date,
                summary=_summary(uow, ctx, c.id),
                updated_at=c.updated_at,
                row_version=c.row_version,
            )
            for c in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/projects/{project_id}/cycles", response_model=s.CycleCreateResponse)
def create_cycle(
    body: s.CycleCreate,
    response: Response,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_uow),
    guard: Idempotency = Depends(idempotency("create_cycle")),
) -> Any:
    """US-080 / FR-EXE-001/002, BR-03 (AC-PLN-01, TCMS-052/054)."""
    if (replay := guard.replay(body)) is not None:
        return replay
    result = service.create_cycle(
        uow,
        ctx,
        CycleData(
            name=body.name,
            environment_id=body.environment_id,
            release_id=body.release_id,
            plan_id=body.plan_id,
            build=body.build,
            start_date=body.start_date,
            due_date=body.due_date,
            description=body.description,
            selection=_selection(body.selection),
            default_assignee_id=body.default_assignee_id,
        ),
    )
    uow.session.flush()
    out = s.CycleCreateResponse(
        cycle_id=result.cycle.id,
        key=result.cycle.key,
        added=result.added,
        skipped=_skipped(result.skipped),
        runs_pending=result.runs_pending,
    )
    code = 202 if result.runs_pending else 201
    guard.store(code, out)
    response.status_code = code
    return out


@router.get("/cycles/{cycle_id}", response_model=s.CycleRead)
def get_cycle(
    cycle_id: UUID, response: Response, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> s.CycleRead:
    """US-083 / FR-EXE-013: cycle with summary and progress by assignee."""
    ctx.require("project.view")
    out = _cycle_read(uow, ctx, cycle_id)
    _etag(response, out.row_version)
    return out


@router.patch("/cycles/{cycle_id}", response_model=s.CycleRead)
def patch_cycle(
    cycle_id: UUID,
    body: s.CyclePatch,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = CycleCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> s.CycleRead:
    fields = {k: getattr(body, k) for k in body.model_fields_set if k != "row_version"}
    service.update_cycle(
        uow, ctx, cycle_id, row_version=resolve_row_version(body.row_version, if_match), fields=fields
    )
    uow.session.flush()
    return _cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/start", response_model=s.CycleRead)
def start_cycle(
    cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CycleRead:
    service.start_cycle(uow, ctx, cycle_id)
    uow.session.flush()
    return _cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/close", response_model=s.CycleRead)
def close_cycle(
    cycle_id: UUID, body: s.CloseRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CycleRead:
    """US-084 (TCMS-058): 409 draft_exists lists drafts unless discard_drafts."""
    service.close_cycle(uow, ctx, cycle_id, discard_drafts=body.discard_drafts)
    uow.session.flush()
    return _cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/reopen", response_model=s.CycleRead)
def reopen_cycle(
    cycle_id: UUID, body: s.ReopenRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CycleRead:
    """US-084 / BR-11 (TCMS-059)."""
    service.reopen_cycle(uow, ctx, cycle_id, reason=body.reason)
    uow.session.flush()
    return _cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/archive", response_model=s.CycleRead)
def archive_cycle(
    cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CycleRead:
    service.archive_cycle(uow, ctx, cycle_id)
    uow.session.flush()
    return _cycle_read(uow, ctx, cycle_id)


@router.post(
    "/cycles/{cycle_id}/clone", response_model=s.CycleCreateResponse, status_code=status.HTTP_201_CREATED
)
def clone_cycle(
    cycle_id: UUID, body: s.CloneRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CycleCreateResponse:
    """US-084 (TCMS-060)."""
    result = service.clone_cycle(
        uow,
        ctx,
        cycle_id,
        name=body.name,
        only_statuses=[st.value for st in body.only_statuses] if body.only_statuses else None,
    )
    uow.session.flush()
    return s.CycleCreateResponse(
        cycle_id=result.cycle.id,
        key=result.cycle.key,
        added=result.added,
        skipped=_skipped(result.skipped),
        runs_pending=result.runs_pending,
    )


@router.post("/cycles/{cycle_id}/sync-from-plan", response_model=s.AddRunsResponse)
def sync_from_plan(
    cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.AddRunsResponse:
    """US-085 / BR-31 (AC-PLN-02, TCMS-053)."""
    result = service.sync_from_plan(uow, ctx, cycle_id)
    uow.session.flush()
    return s.AddRunsResponse(added=result.added, skipped=_skipped(result.skipped))


# -- runs -----------------------------------------------------------------------------------------


@router.get("/cycles/{cycle_id}/runs", response_model=Page[s.RunRead])
def list_runs(
    cycle_id: UUID,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    assignee_id: str | None = None,
    needs_retest: bool | None = None,
    include_superseded: bool = False,
    ctx: AccessContext = CycleCtx,
    uow: UnitOfWork = Depends(get_read_uow),
) -> Page[s.RunRead]:
    """US-083 / FR-EXE-013: filters per docs/06 §4.6."""
    ctx.require("project.view")
    rows, total = eq.list_runs(
        uow.session, ctx, cycle_id, dict(request.query_params), PageParams(page=page, page_size=page_size)
    )
    refs = identity_queries.user_refs(uow.session, {r.run.assignee_id for r in rows if r.run.assignee_id})
    return Page[s.RunRead](
        items=[
            s.RunRead(
                id=r.run.id,
                cycle_id=r.run.cycle_id,
                test_case_id=r.run.test_case_id,
                case_key=r.case_key,
                title=r.title,
                version_no=r.version_no,
                latest_version_no=r.latest_version_no,
                position=r.run.position,
                assignee=UserRef(**vars(refs[r.run.assignee_id])) if r.run.assignee_id in refs else None,
                status=r.run.status,
                needs_retest=r.run.needs_retest,
                superseded=r.run.superseded_by_run_id is not None,
                row_version=r.run.row_version,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/cycles/{cycle_id}/runs", response_model=s.AddRunsResponse)
def add_runs(
    cycle_id: UUID, body: s.AddCasesRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.AddRunsResponse:
    """US-081 / FR-EXE-003 (TCMS-057)."""
    result = service.add_cases(
        uow, ctx, cycle_id, Selection(case_ids=body.case_ids, folder_ids=body.folder_ids, tags=body.tags)
    )
    uow.session.flush()
    return s.AddRunsResponse(added=result.added, skipped=_skipped(result.skipped))


@router.delete("/cycles/{cycle_id}/runs", response_model=s.CountResponse)
def remove_runs(
    cycle_id: UUID, body: s.RunIdsRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CountResponse:
    """US-081: only not_run runs without attempts (409 run_has_results)."""
    removed = service.remove_runs(uow, ctx, cycle_id, run_ids=body.run_ids)
    uow.session.flush()
    return s.CountResponse(count=removed)


@router.post("/cycles/{cycle_id}/runs/assign", response_model=s.CountResponse)
def assign_runs(
    cycle_id: UUID, body: s.AssignRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CountResponse:
    """US-082 / FR-EXE-004 (TCMS-055)."""
    changed = service.assign_runs(uow, ctx, cycle_id, run_ids=body.run_ids, assignee_id=body.assignee_id)
    uow.session.flush()
    return s.CountResponse(count=changed)


@router.post("/cycles/{cycle_id}/runs/reorder", response_model=s.CountResponse)
def reorder_runs(
    cycle_id: UUID, body: s.ReorderRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CountResponse:
    """US-087 / docs/02 §7.1."""
    n = service.reorder_runs(uow, ctx, cycle_id, ordered_run_ids=body.ordered_run_ids, sort_by=body.sort_by)
    uow.session.flush()
    return s.CountResponse(count=n)


@router.post("/cycles/{cycle_id}/runs/update-versions", response_model=s.CountResponse)
def update_not_run_versions(
    cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.CountResponse:
    """US-086 bulk: update all not-run runs to the latest eligible version (BR-04)."""
    n = service.update_not_run_versions(uow, ctx, cycle_id)
    uow.session.flush()
    return s.CountResponse(count=n)


@router.post("/runs/{run_id}/claim", response_model=s.RunRead)
def claim_run(run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = Depends(get_uow)) -> s.RunRead:
    """US-082 / FR-EXE-004 (TCMS-056)."""
    service.claim_run(uow, ctx, run_id)
    uow.session.flush()
    return _run_read(uow, ctx, run_id)


@router.post("/runs/{run_id}/update-version", response_model=s.RunRead)
def update_run_version(
    run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = Depends(get_uow)
) -> s.RunRead:
    """US-086 / BR-04."""
    service.update_run_version(uow, ctx, run_id)
    uow.session.flush()
    return _run_read(uow, ctx, run_id)


@router.post("/runs/{run_id}/replace", response_model=s.RunRead, status_code=status.HTTP_201_CREATED)
def replace_run(run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = Depends(get_uow)) -> s.RunRead:
    """US-086 / BR-05."""
    new = service.replace_run(uow, ctx, run_id)
    uow.session.flush()
    return _run_read(uow, ctx, new.id)


def _run_read(uow: UnitOfWork, ctx: AccessContext, run_id: UUID) -> s.RunRead:
    r = eq.run_row(uow.session, ctx, run_id)
    if r is None:
        raise NotFound()
    return s.RunRead(
        id=r.run.id,
        cycle_id=r.run.cycle_id,
        test_case_id=r.run.test_case_id,
        case_key=r.case_key,
        title=r.title,
        version_no=r.version_no,
        latest_version_no=r.latest_version_no,
        position=r.run.position,
        assignee=_ref(uow, r.run.assignee_id),
        status=r.run.status,
        needs_retest=r.run.needs_retest,
        superseded=r.run.superseded_by_run_id is not None,
        row_version=r.run.row_version,
    )
