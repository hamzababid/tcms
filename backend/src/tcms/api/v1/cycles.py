"""Cycles and runs (docs/06 §4.6, §5.3, §5.4)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from tcms.api.deps import (
    ReadUow,
    Uow,
    project_context,
    project_context_from,
    resolve_row_version,
)
from tcms.api.idempotency import Idempotency, idempotency
from tcms.api.v1.records import attachment_read
from tcms.api.v1.test_cases import version_read
from tcms.core.context import AccessContext
from tcms.core.errors import InvalidInclude, NotFound
from tcms.core.pagination import Page, PageParams
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as eq
from tcms.execution import schemas as s
from tcms.execution import service
from tcms.execution.queries import TestCycle
from tcms.execution.service import CycleData, Selection
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.planning import queries as planning_queries
from tcms.platform import attachments
from tcms.reporting.metrics import ExecutionSummary
from tcms.testdesign import queries as tq
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["cycles"])

CycleCtx = Depends(project_context_from("test_cycle", "cycle_id"))
RunCtx = Depends(project_context_from("test_run", "run_id"))
RUN_INCLUDES = frozenset({"version", "draft", "history", "queue"})


def _etag(response: Response, rv: int) -> None:
    response.headers["ETag"] = f'"{rv}"'


def _users(uow: UnitOfWork, ids_: set[UUID | None]) -> dict[UUID, UserRef]:
    found = identity_queries.user_refs(uow.session, {i for i in ids_ if i is not None})
    return {k: UserRef(**vars(v)) for k, v in found.items()}


def summary_read(counts: dict[str, int], needs_retest: int = 0) -> s.ExecutionSummaryRead:
    """The only way cycle numbers are produced: reporting/metrics.py (CLAUDE.md rule 5)."""
    m = ExecutionSummary.from_counts(counts, needs_retest=needs_retest)
    return s.ExecutionSummaryRead.model_validate(m, from_attributes=True)


class _Refs:
    """Release / plan / environment names for a set of cycles (one query each)."""

    def __init__(self, uow: UnitOfWork, ctx: AccessContext, cycles: list[TestCycle]) -> None:
        org = ctx.principal.organization_id
        self.releases = {r.id: r.name for r in workspace_queries.releases(uow.session, org, ctx.pid)}
        self.envs = {
            e.id: e.name
            for e in workspace_queries.environments(uow.session, org, ctx.pid, include_archived=True)
        }
        self.plans: dict[UUID, s.KeyRef] = {}
        for pid in {c.plan_id for c in cycles if c.plan_id}:
            p = planning_queries.plan_detail(uow.session, ctx, pid)
            if p:
                self.plans[pid] = s.KeyRef(id=p.id, key=p.key, title=p.name)
        people: set[UUID | None] = {c.owner_id for c in cycles}
        people |= {c.closed_by for c in cycles}
        self.users = _users(uow, people)

    def release(self, c: TestCycle) -> s.Ref | None:
        return s.Ref(id=c.release_id, name=self.releases.get(c.release_id, "—")) if c.release_id else None

    def env(self, c: TestCycle) -> s.Ref:
        return s.Ref(id=c.environment_id, name=self.envs.get(c.environment_id, "—"))

    def plan(self, c: TestCycle) -> s.KeyRef | None:
        return self.plans.get(c.plan_id) if c.plan_id else None


def cycle_read(uow: UnitOfWork, ctx: AccessContext, cycle_id: UUID) -> s.CycleRead:
    se = uow.session
    c = eq.cycle(se, ctx, cycle_id)
    if c is None:
        raise NotFound()
    refs = _Refs(uow, ctx, [c])
    counts = eq.status_counts(se, ctx, [c.id])[c.id]
    retest = eq.needs_retest_counts(se, ctx, [c.id]).get(c.id, 0)
    return s.CycleRead(
        id=c.id,
        key=c.key,
        project_id=ctx.pid,
        name=c.name,
        description=c.description,
        status=c.status,
        release=refs.release(c),
        plan=refs.plan(c),
        environment=refs.env(c),
        build=c.build,
        start_date=c.start_date,
        due_date=c.due_date,
        owner=refs.users.get(c.owner_id),
        runs_pending=c.runs_pending,
        summary=summary_read(counts, retest),
        superseded_runs=eq.superseded_count(se, ctx, c.id),
        progress_by_assignee=[
            s.GroupProgress(id=g.id, name=g.name, summary=summary_read(g.counts))
            for g in eq.progress_by_assignee(se, ctx, c.id)
        ],
        progress_by_folder=[
            s.GroupProgress(id=g.id, name=g.name, summary=summary_read(g.counts))
            for g in eq.progress_by_folder(se, ctx, c.id)
        ],
        started_at=c.started_at,
        closed_at=c.closed_at,
        closed_by=refs.users.get(c.closed_by) if c.closed_by else None,
        archived=c.archived_at is not None,
        created_at=c.created_at,
        updated_at=c.updated_at,
        row_version=c.row_version,
    )


def cycle_list_items(uow: UnitOfWork, ctx: AccessContext, cycles: list[TestCycle]) -> list[s.CycleListItem]:
    ids_ = [c.id for c in cycles]
    counts = eq.status_counts(uow.session, ctx, ids_)
    retest = eq.needs_retest_counts(uow.session, ctx, ids_)
    refs = _Refs(uow, ctx, cycles)
    return [
        s.CycleListItem(
            id=c.id,
            key=c.key,
            name=c.name,
            status=c.status,
            release=refs.release(c),
            plan=refs.plan(c),
            environment=refs.env(c),
            build=c.build,
            start_date=c.start_date,
            due_date=c.due_date,
            owner=refs.users.get(c.owner_id),
            runs_pending=c.runs_pending,
            summary=summary_read(counts.get(c.id, {}), retest.get(c.id, 0)),
            archived=c.archived_at is not None,
            updated_at=c.updated_at,
            row_version=c.row_version,
        )
        for c in cycles
    ]


def _selection(body: s.SelectionIn) -> Selection:
    return Selection(
        from_plan=body.from_plan,
        case_ids=body.case_ids,
        folder_ids=body.folder_ids,
        tags=body.tags,
        priorities=list(body.priorities),
    )


def _skipped(pairs: list[tuple[str, str]]) -> list[s.Skipped]:
    return [s.Skipped(key=k, reason=r) for k, r in pairs]


def _create_response(
    uow: UnitOfWork, ctx: AccessContext, result: service.CreateCycleResult
) -> s.CycleCreateResponse:
    uow.session.flush()
    return s.CycleCreateResponse(
        cycle=cycle_read(uow, ctx, result.cycle.id),
        added=result.added,
        skipped=_skipped(result.skipped),
        runs_pending=result.runs_pending,
    )


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
    include_archived: bool = False,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> Page[s.CycleListItem]:
    """US-080 / FR-EXE-001: each item has its ExecutionSummary."""
    ctx.require("project.view")
    rows, total = eq.list_cycles(
        uow.session, ctx, dict(request.query_params), PageParams(page=page, page_size=page_size)
    )
    return Page[s.CycleListItem](
        items=cycle_list_items(uow, ctx, rows), page=page, page_size=page_size, total=total
    )


@router.post(
    "/projects/{project_id}/cycles",
    response_model=s.CycleCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": s.CycleCreateResponse, "description": "Runs are created in the background"}},
)
def create_cycle(
    body: s.CycleCreate,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Uow,
    guard: Idempotency = Depends(idempotency("create_cycle")),
) -> Any:
    """US-080 / FR-EXE-001/002, BR-03 (AC-PLN-01, TCMS-052/054, TCMS-025b)."""
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
    out = _create_response(uow, ctx, result)
    code = 202 if result.runs_pending else 201
    guard.store(code, out)
    return JSONResponse(out.model_dump(mode="json"), status_code=code)


@router.get("/cycles/{cycle_id}", response_model=s.CycleRead)
def get_cycle(
    cycle_id: UUID, response: Response, ctx: AccessContext = CycleCtx, uow: UnitOfWork = ReadUow
) -> s.CycleRead:
    """US-083 / FR-EXE-013: cycle, ExecutionSummary and progress by assignee and folder."""
    ctx.require("project.view")
    out = cycle_read(uow, ctx, cycle_id)
    _etag(response, out.row_version)
    return out


@router.patch("/cycles/{cycle_id}", response_model=s.CycleRead)
def patch_cycle(
    cycle_id: UUID,
    body: s.CyclePatch,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    ctx: AccessContext = CycleCtx,
    uow: UnitOfWork = Uow,
) -> s.CycleRead:
    fields = {k: getattr(body, k) for k in body.model_fields_set if k != "row_version"}
    service.update_cycle(
        uow, ctx, cycle_id, row_version=resolve_row_version(body.row_version, if_match), fields=fields
    )
    uow.session.flush()
    out = cycle_read(uow, ctx, cycle_id)
    _etag(response, out.row_version)
    return out


@router.post("/cycles/{cycle_id}/start", response_model=s.CycleRead)
def start_cycle(cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow) -> s.CycleRead:
    service.start_cycle(uow, ctx, cycle_id)
    uow.session.flush()
    return cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/close", response_model=s.CycleRead)
def close_cycle(
    cycle_id: UUID, body: s.CloseRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.CycleRead:
    """US-084 (TCMS-058): `409 draft_exists` lists the drafts unless `discard_drafts`."""
    service.close_cycle(uow, ctx, cycle_id, discard_drafts=body.discard_drafts)
    uow.session.flush()
    return cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/reopen", response_model=s.CycleRead)
def reopen_cycle(
    cycle_id: UUID, body: s.ReopenRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.CycleRead:
    """US-084 / BR-11 (TCMS-059)."""
    service.reopen_cycle(uow, ctx, cycle_id, reason=body.reason)
    uow.session.flush()
    return cycle_read(uow, ctx, cycle_id)


@router.post("/cycles/{cycle_id}/archive", response_model=s.CycleRead)
def archive_cycle(cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow) -> s.CycleRead:
    service.archive_cycle(uow, ctx, cycle_id)
    uow.session.flush()
    return cycle_read(uow, ctx, cycle_id)


@router.post(
    "/cycles/{cycle_id}/clone",
    response_model=s.CycleCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": s.CycleCreateResponse, "description": "Runs are created in the background"}},
)
def clone_cycle(
    cycle_id: UUID, body: s.CloneRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> Any:
    """US-084 (TCMS-060)."""
    result = service.clone_cycle(
        uow,
        ctx,
        cycle_id,
        name=body.name,
        only_statuses=list(body.only_statuses) if body.only_statuses else None,
    )
    out = _create_response(uow, ctx, result)
    return JSONResponse(out.model_dump(mode="json"), status_code=202 if result.runs_pending else 201)


@router.post("/cycles/{cycle_id}/sync-from-plan", response_model=s.AddRunsResponse)
def sync_from_plan(cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow) -> s.AddRunsResponse:
    """US-085 / BR-31 (AC-PLN-02, TCMS-053)."""
    result = service.sync_from_plan(uow, ctx, cycle_id)
    return s.AddRunsResponse(added=result.added, skipped=_skipped(result.skipped))


# -- runs -----------------------------------------------------------------------------------------


def _run_item(r: eq.RunRow, users: dict[UUID, UserRef]) -> s.RunListItem:
    return s.RunListItem(
        id=r.run.id,
        cycle_id=r.run.cycle_id,
        position=r.run.position,
        test_case=s.RunCase(
            id=r.run.test_case_id,
            key=r.case_key,
            title=r.title,
            priority=r.priority,
            folder_id=r.folder_id,
            folder_name=r.folder_name,
        ),
        pinned_version_no=r.pinned_version_no,
        newer_version_no=r.eligible_version_no,
        assignee=users.get(r.run.assignee_id) if r.run.assignee_id else None,
        status=r.run.status,
        needs_retest=r.run.needs_retest,
        superseded=r.run.superseded_by_run_id is not None,
        updated_at=r.run.updated_at,
        row_version=r.run.row_version,
    )


@router.get("/cycles/{cycle_id}/runs", response_model=Page[s.RunListItem])
def list_runs(
    cycle_id: UUID,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    status_: str | None = Query(default=None, alias="status"),
    assignee_id: str | None = None,
    folder_id: UUID | None = None,
    priority: str | None = None,
    tag: str | None = None,
    needs_retest: bool | None = None,
    include_superseded: bool = False,
    ctx: AccessContext = CycleCtx,
    uow: UnitOfWork = ReadUow,
) -> Page[s.RunListItem]:
    """US-083 / FR-EXE-013: filters and sorts of docs/06 §4.6."""
    ctx.require("project.view")
    rows, total = eq.list_runs(
        uow.session, ctx, cycle_id, dict(request.query_params), PageParams(page=page, page_size=page_size)
    )
    users = _users(uow, {r.run.assignee_id for r in rows})
    return Page[s.RunListItem](
        items=[_run_item(r, users) for r in rows], page=page, page_size=page_size, total=total
    )


@router.post("/cycles/{cycle_id}/runs", response_model=s.AddRunsResponse)
def add_runs(
    cycle_id: UUID, body: s.AddCasesRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.AddRunsResponse:
    """US-081 / FR-EXE-003."""
    result = service.add_cases(
        uow, ctx, cycle_id, Selection(case_ids=body.case_ids, folder_ids=body.folder_ids, tags=body.tags)
    )
    return s.AddRunsResponse(added=result.added, skipped=_skipped(result.skipped))


@router.delete("/cycles/{cycle_id}/runs", response_model=s.CountResponse)
def remove_runs(
    cycle_id: UUID, body: s.RunIdsRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.CountResponse:
    """US-081 (TCMS-057): only not-run runs without attempts (409 run_has_results)."""
    return s.CountResponse(count=service.remove_runs(uow, ctx, cycle_id, run_ids=body.run_ids))


@router.post("/cycles/{cycle_id}/runs/assign", response_model=s.CountResponse)
def assign_runs(
    cycle_id: UUID, body: s.AssignRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.CountResponse:
    """US-082 / FR-EXE-004 (TCMS-055): selected runs or every run matching `filter`."""
    n = service.assign_runs(
        uow, ctx, cycle_id, run_ids=body.run_ids, filter_=body.filter, assignee_id=body.assignee_id
    )
    return s.CountResponse(count=n)


@router.post("/cycles/{cycle_id}/runs/reorder", response_model=s.CountResponse)
def reorder_runs(
    cycle_id: UUID, body: s.ReorderRequest, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.CountResponse:
    """US-087 / docs/02 §7.1."""
    n = service.reorder_runs(uow, ctx, cycle_id, run_ids_in_order=body.run_ids_in_order, sort_by=body.sort_by)
    return s.CountResponse(count=n)


@router.post("/cycles/{cycle_id}/runs/update-versions", response_model=s.CountResponse)
def update_not_run_versions(
    cycle_id: UUID, ctx: AccessContext = CycleCtx, uow: UnitOfWork = Uow
) -> s.CountResponse:
    """US-086 bulk: every not-run run moves to its eligible version (BR-04)."""
    return s.CountResponse(count=service.update_not_run_versions(uow, ctx, cycle_id))


def result_read(uow: UnitOfWork, ctx: AccessContext, v: eq.ResultView) -> s.ResultRead:
    """docs/06 §5.5: an attempt with its step rows and their evidence."""
    org = ctx.principal.organization_id
    envs = {
        e.id: e.name for e in workspace_queries.environments(uow.session, org, ctx.pid, include_archived=True)
    }
    evidence = attachments.list_for(uow, org, "test_step_result", [x.id for x in v.steps])
    people = {v.executed_by, *(a.uploaded_by for lst in evidence.values() for a in lst)}
    users = _users(uow, set(people))
    return s.ResultRead(
        id=v.id,
        run_id=v.run_id,
        attempt_no=v.attempt_no,
        state=v.state,
        status=v.status,
        source=v.source,
        executed_by=users.get(v.executed_by) if v.executed_by else None,
        started_at=v.started_at,
        finished_at=v.finished_at,
        duration_seconds=v.duration_seconds,
        build=v.build,
        environment=s.Ref(id=v.environment_id, name=envs.get(v.environment_id, "—")),
        comment=v.comment,
        reason=v.reason,
        skipped_steps=v.skipped_steps,
        corrects_result_id=v.corrects_result_id,
        steps=[
            s.StepResultRead(
                id=x.id,
                step_id=x.step_id,
                position=x.position,
                status=x.status,
                actual_result=x.actual_result,
                comment=x.comment,
                attachments=[attachment_read(a, users) for a in evidence.get(x.id, [])],
                updated_at=x.updated_at,
            )
            for x in v.steps
        ],
    )


def run_read(
    uow: UnitOfWork,
    ctx: AccessContext,
    run_id: UUID,
    includes: frozenset[str],
    queue_filter: str | None = None,
) -> s.RunRead:
    d = eq.run_detail(uow.session, ctx, run_id)
    r = d.row
    attempts = [*d.history, *([d.draft] if d.draft else [])]
    users = _users(uow, {r.run.assignee_id, *(a.executed_by for a in attempts)})
    corrected_by = {a.corrects_result_id: a.id for a in d.history if a.corrects_result_id}

    def attempt(a: eq.AttemptView) -> s.AttemptRead:
        return s.AttemptRead(
            id=a.id,
            attempt_no=a.attempt_no,
            state=a.state,
            status=a.status,
            executed_by=users.get(a.executed_by) if a.executed_by else None,
            started_at=a.started_at,
            finished_at=a.finished_at,
            duration_seconds=a.duration_seconds,
            reason=a.reason,
            comment=a.comment,
            skipped_steps=a.skipped_steps,
            corrects_result_id=a.corrects_result_id,
            corrected_by_result_id=corrected_by.get(a.id),
        )

    version = None
    if "version" in includes:
        v = tq.version_view_by_id(uow.session, ctx, r.run.test_case_version_id)
        if v is not None:
            refs = _users(uow, {v.created_by, v.approved_by, v.submitted_by})
            version = version_read(uow, ctx, v, refs)
    newer = None
    if d.newer is not None:
        number = tq.version_numbers(uow.session, [d.newer.version_id]).get(d.newer.version_id, 0)
        newer = s.NewerVersionRead(
            version_no=number, eligible=d.newer.eligible, can_update=d.newer.can_update, reason=d.newer.reason
        )
    draft = None
    if "draft" in includes:
        dv = eq.draft_detail(uow.session, r.run.id)
        draft = result_read(uow, ctx, dv) if dv else None
    queue = None
    if "queue" in includes:
        q = eq.queue(uow.session, ctx, r.run.id, queue_filter)
        queue = s.QueueRead(
            filter=q.filter,
            position=q.position,
            total=q.total,
            previous_run_id=q.previous_run_id,
            next_run_id=q.next_run_id,
        )
    return s.RunRead(
        id=r.run.id,
        cycle=s.RunCycleRef(id=d.cycle.id, key=d.cycle.key, name=d.cycle.name, status=d.cycle.status),
        position=r.run.position,
        test_case=s.RunCaseDetail(
            id=r.run.test_case_id,
            key=r.case_key,
            title=r.title,
            priority=r.priority,
            folder_id=r.folder_id,
            folder_name=r.folder_name,
            folder_path=d.folder_path,
        ),
        pinned_version_no=r.pinned_version_no,
        newer_version=newer,
        assignee=users.get(r.run.assignee_id) if r.run.assignee_id else None,
        status=r.run.status,
        needs_retest=r.run.needs_retest,
        superseded_by_run_id=r.run.superseded_by_run_id,
        has_attempts=d.has_attempts,
        version=version,
        draft=draft,
        history=[attempt(a) for a in d.history] if "history" in includes else None,
        queue=queue,
        row_version=r.run.row_version,
    )


def _includes(raw: str | None) -> frozenset[str]:
    wanted = frozenset(x.strip() for x in (raw or "").split(",") if x.strip())
    unknown = wanted - RUN_INCLUDES
    if unknown:
        raise InvalidInclude(f"Unknown include: {', '.join(sorted(unknown))}")
    return wanted


@router.get("/runs/{run_id}", response_model=s.RunRead)
def get_run(
    run_id: UUID,
    response: Response,
    include: str | None = Query(default=None, max_length=100),
    queue_filter: str | None = Query(
        default=None, description="Runner queue (include=queue): mine_open (default), mine, open, all"
    ),
    ctx: AccessContext = RunCtx,
    uow: UnitOfWork = ReadUow,
) -> s.RunRead:
    """docs/06 §4.6 / §5.4: run, case summary, pinned version, newer version, draft, attempts, queue."""
    ctx.require("project.view")
    out = run_read(uow, ctx, run_id, _includes(include), queue_filter)
    _etag(response, out.row_version)
    return out


@router.post("/runs/{run_id}/claim", response_model=s.RunRead)
def claim_run(run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = Uow) -> s.RunRead:
    """US-082 / FR-EXE-004 (TCMS-056)."""
    service.claim_run(uow, ctx, run_id)
    uow.session.flush()
    return run_read(uow, ctx, run_id, frozenset())


@router.post("/runs/{run_id}/update-version", response_model=s.RunRead)
def update_run_version(run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = Uow) -> s.RunRead:
    """US-086 / BR-04."""
    service.update_run_version(uow, ctx, run_id)
    uow.session.flush()
    return run_read(uow, ctx, run_id, frozenset())


@router.post("/runs/{run_id}/replace", response_model=s.RunRead, status_code=status.HTTP_201_CREATED)
def replace_run(run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = Uow) -> s.RunRead:
    """US-086 / BR-05: returns the new run."""
    new = service.replace_run(uow, ctx, run_id)
    uow.session.flush()
    return run_read(uow, ctx, new.id, frozenset())
