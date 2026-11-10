"""Requirement references, coverage and traceability (docs/06 §4.9, §5.8; docs/02 §10; ADR-024)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from tcms.api.deps import (
    ReadUow,
    Uow,
    project_context,
    project_context_from,
)
from tcms.bugs import queries as bug_queries
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, NotFound, ValidationFailed
from tcms.core.pagination import Page
from tcms.core.uow import UnitOfWork
from tcms.execution import queries as exec_queries
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.planning import queries as plan_queries
from tcms.reporting import coverage
from tcms.reporting.metrics import RequirementCoverage
from tcms.requirements import queries as rq
from tcms.requirements import schemas as s
from tcms.requirements import service
from tcms.testdesign import queries as td_queries
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["requirements"])

RefCtx = Depends(project_context_from("requirement_ref", "ref_id"))
CaseCtx = Depends(project_context_from("test_case", "case_id"))


def _release(uow: UnitOfWork, ctx: AccessContext, release_id: UUID | None) -> UUID | None:
    if release_id is not None:
        rel = workspace_queries.release(uow.session, ctx.principal.organization_id, release_id)
        if rel is None or rel.project_id != ctx.pid:
            raise NotFound("Unknown release")
    return release_id


def _read(v: rq.RefView, status_: s.RefStatus | None = None) -> s.RequirementRefRead:
    return s.RequirementRefRead(
        id=v.id,
        reference=v.reference,
        url=v.url,
        title=v.title,
        archived=v.archived,
        case_count=v.case_count,
        status=status_,
        created_at=v.created_at,
        updated_at=v.updated_at,
        row_version=v.row_version,
    )


def _statuses(
    uow: UnitOfWork, ctx: AccessContext, ids: list[UUID], release_id: UUID | None
) -> dict[UUID, s.RefStatus]:
    out: dict[UUID, s.RefStatus] = {
        r.ref_id: r.status for r in coverage.coverage_rows(uow.session, ctx, release_id, ids)
    }
    return out


def _trace_cases(
    uow: UnitOfWork, ctx: AccessContext, rows: list[coverage.RefCoverage], release_id: UUID | None
) -> tuple[dict[UUID, list[s.TraceCase]], dict[UUID, list[s.BugRef]]]:
    case_ids = sorted({c.case_id for r in rows for c in r.cases})
    runs = exec_queries.run_ids_in_release(uow.session, ctx, release_id) if release_id else None
    bugs = bug_queries.references_for_cases(uow.session, ctx, case_ids, runs)
    found = identity_queries.user_refs(
        uow.session,
        {c.latest.executed_by for r in rows for c in r.cases if c.latest and c.latest.executed_by},
    )
    users = {k: UserRef(**vars(v)) for k, v in found.items()}
    cases: dict[UUID, list[s.TraceCase]] = {}
    row_bugs: dict[UUID, list[s.BugRef]] = {}
    for r in rows:
        items = []
        seen: dict[str, s.BugRef] = {}
        for c in r.cases:
            case_bugs = [s.BugRef(reference=ref, url=url) for ref, url in bugs.get(c.case_id, [])]
            for b in case_bugs:
                seen.setdefault(b.reference.upper(), b)
            latest = (
                s.LatestResult(
                    status=c.latest.status,
                    finished_at=c.latest.finished_at,
                    executed_by=users.get(c.latest.executed_by) if c.latest.executed_by else None,
                    run_id=c.latest.run_id,
                    cycle_key=c.latest.cycle_key,
                )
                if c.latest
                else None
            )
            items.append(s.TraceCase(id=c.case_id, key=c.key, title=c.title, latest=latest, bugs=case_bugs))
        cases[r.ref_id] = items
        row_bugs[r.ref_id] = list(seen.values())
    return cases, row_bugs


def _coverage(c: RequirementCoverage) -> s.CoverageRead:
    return s.CoverageRead(
        total=c.total,
        covered=c.covered,
        not_covered=c.not_covered,
        passed=c.passed,
        failed=c.failed,
        blocked=c.blocked,
        not_run=c.not_run,
        coverage=s.Rate(**vars(c.coverage)),
        verified=s.Rate(**vars(c.verified)),
    )


# -- references ------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/requirements", response_model=Page[s.RequirementRefRead])
def list_requirements(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=100),
    linked: bool | None = Query(default=None, description="true: with linked cases; false: without"),
    plan_id: UUID | None = Query(default=None, description="Only the references a plan lists"),
    release_id: UUID | None = Query(default=None, description="Only references in scope; status in it"),
    include_archived: bool = False,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> Page[s.RequirementRefRead]:
    """R-120: natural order (SPK-2 before SPK-10); each item carries its status (release or all cycles)."""
    ctx.require("project.view")
    _release(uow, ctx, release_id)
    scope: list[UUID] | None = None
    if plan_id is not None:
        if plan_queries.plan_detail(uow.session, ctx, plan_id) is None:
            raise NotFound("Unknown plan")
        scope = plan_queries.plan_requirement_ids(uow.session, ctx, plan_id)
    if release_id is not None:
        in_release = set(coverage.scope_ids(uow.session, ctx, release_id))
        scope = [i for i in scope if i in in_release] if scope is not None else sorted(in_release)
    rows = rq.list_refs(
        uow.session, ctx, q=q, linked=linked, ref_ids=scope, include_archived=include_archived
    )
    start = (page - 1) * page_size
    window = rows[start : start + page_size]
    statuses = _statuses(uow, ctx, [v.id for v in window], release_id)
    return Page[s.RequirementRefRead](
        items=[_read(v, statuses.get(v.id)) for v in window], page=page, page_size=page_size, total=len(rows)
    )


@router.post(
    "/projects/{project_id}/requirements", response_model=s.RefsCreated, status_code=status.HTTP_201_CREATED
)
def add_requirements(
    body: s.RequirementRefsCreate,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Uow,
) -> s.RefsCreated:
    """R-120 / AC-REQ-06: add one or many references; existing ones are returned, not duplicated."""
    out = service.add_refs(uow, ctx, text=body.references, url=body.url, title=body.title)
    uow.session.flush()
    views = {v.id: v for v in rq.refs_by_ids(uow.session, ctx, [r.id for r in out.refs])}
    return s.RefsCreated(created=out.created, references=[_read(views[r.id]) for r in out.refs])


@router.get("/requirements/{ref_id}", response_model=s.RequirementDetail)
def get_requirement(
    ref_id: UUID,
    release_id: UUID | None = None,
    ctx: AccessContext = RefCtx,
    uow: UnitOfWork = ReadUow,
) -> s.RequirementDetail:
    """The reference with its cases (latest result in the release) and the plans that list it."""
    ctx.require("project.view")
    _release(uow, ctx, release_id)
    v = rq.ref_detail(uow.session, ctx, ref_id)
    rows = coverage.coverage_rows(uow.session, ctx, release_id, [ref_id])
    cases, _ = _trace_cases(uow, ctx, rows, release_id)
    plans = plan_queries.plans_with_ref(uow.session, ctx, ref_id)
    base = _read(v, rows[0].status if rows else "not_covered")
    return s.RequirementDetail(
        **base.model_dump(),
        cases=cases.get(ref_id, []),
        plans=[s.PlanRef(id=p.id, key=p.key, name=p.name) for p in plans],
    )


@router.patch("/requirements/{ref_id}", response_model=s.RequirementRefRead)
def patch_requirement(
    ref_id: UUID, body: s.RequirementRefPatch, ctx: AccessContext = RefCtx, uow: UnitOfWork = Uow
) -> s.RequirementRefRead:
    service.update_ref(uow, ctx, ref_id, fields={k: getattr(body, k) for k in body.model_fields_set})
    uow.session.flush()
    return _read(rq.ref_detail(uow.session, ctx, ref_id))


@router.post("/requirements/{ref_id}/archive", response_model=s.RequirementRefRead)
def archive_requirement(
    ref_id: UUID, ctx: AccessContext = RefCtx, uow: UnitOfWork = Uow
) -> s.RequirementRefRead:
    service.set_archived(uow, ctx, ref_id, archived=True)
    uow.session.flush()
    return _read(rq.ref_detail(uow.session, ctx, ref_id))


@router.post("/requirements/{ref_id}/restore", response_model=s.RequirementRefRead)
def restore_requirement(
    ref_id: UUID, ctx: AccessContext = RefCtx, uow: UnitOfWork = Uow
) -> s.RequirementRefRead:
    service.set_archived(uow, ctx, ref_id, archived=False)
    uow.session.flush()
    return _read(rq.ref_detail(uow.session, ctx, ref_id))


# -- links -------------------------------------------------------------------------------------------


@router.post("/requirements/{ref_id}/test-cases", response_model=s.LinkCount)
def link_cases(
    ref_id: UUID, body: s.CaseIdsRequest, ctx: AccessContext = RefCtx, uow: UnitOfWork = Uow
) -> s.LinkCount:
    """R-121 / TCMS-110: link cases to the reference (idempotent); folders and tags expand to their cases."""
    case_ids = list(body.test_case_ids)
    if body.folder_ids:
        case_ids += td_queries.case_ids_in_folders(uow.session, ctx, body.folder_ids, include_subfolders=True)
    if body.tags:
        case_ids += td_queries.case_ids_with_tags(uow.session, ctx, body.tags)
    case_ids = list(dict.fromkeys(case_ids))
    if not case_ids:
        raise ValidationFailed(
            "Choose cases", errors=[FieldError("test_case_ids", "field_required", "Choose one or more cases")]
        )
    return s.LinkCount(count=service.link_cases(uow, ctx, ref_id, case_ids))


@router.delete("/requirements/{ref_id}/test-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_case(ref_id: UUID, case_id: UUID, ctx: AccessContext = RefCtx, uow: UnitOfWork = Uow) -> Response:
    service.unlink(uow, ctx, ref_id, case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/test-cases/{case_id}/requirements", response_model=list[s.RequirementRefRead])
def case_requirements(
    case_id: UUID,
    release_id: UUID | None = None,
    ctx: AccessContext = CaseCtx,
    uow: UnitOfWork = ReadUow,
) -> list[s.RequirementRefRead]:
    """Case page Requirements tab."""
    ctx.require("project.view")
    views = rq.refs_of_case(uow.session, ctx, case_id)
    statuses = _statuses(uow, ctx, [v.id for v in views], _release(uow, ctx, release_id))
    return [_read(v, statuses.get(v.id)) for v in views]


@router.post("/test-cases/{case_id}/requirements", response_model=s.LinkCount)
def link_case_to_requirements(
    case_id: UUID, body: s.ReferencesRequest, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Uow
) -> s.LinkCount:
    """From the case: references by text; unknown ones are registered (D12)."""
    ensured, count = service.link_references(uow, ctx, text=body.references, case_ids=[case_id])
    return s.LinkCount(count=count, created=ensured.created)


@router.post("/projects/{project_id}/requirements/link-cases", response_model=s.LinkCount)
def bulk_link(
    body: s.LinkCasesRequest,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Uow,
) -> s.LinkCount:
    """Repository bulk action "Link selected to requirement…" (TCMS-110)."""
    ensured, count = service.link_references(uow, ctx, text=body.references, case_ids=body.test_case_ids)
    return s.LinkCount(count=count, created=ensured.created)


# -- coverage and traceability ---------------------------------------------------------------------


@router.get("/projects/{project_id}/coverage", response_model=s.CoverageRead)
def get_coverage(
    release_id: UUID | None = None,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> s.CoverageRead:
    """FR-REQ-005 / BR-23: coverage metrics for the release (or across all cycles)."""
    ctx.require("project.view")
    rows = coverage.coverage_rows(uow.session, ctx, _release(uow, ctx, release_id))
    return _coverage(coverage.summary(rows))


@router.get("/projects/{project_id}/traceability", response_model=s.TraceabilityRead)
def traceability(
    release_id: UUID | None = None,
    status_: str | None = Query(default=None, alias="status", description="Comma list of statuses"),
    uncovered: bool = False,
    q: str | None = Query(default=None, max_length=100),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> s.TraceabilityRead:
    """FR-REQ-004 / TCMS-112 (docs/02 §10.4): the summary covers every reference in scope; the rows follow
    the filters."""
    ctx.require("project.view")
    rows = coverage.coverage_rows(uow.session, ctx, _release(uow, ctx, release_id))
    summary = _coverage(coverage.summary(rows))
    wanted = {x.strip() for x in (status_ or "").split(",") if x.strip()}
    if uncovered:
        wanted = {"not_covered"}
    if wanted:
        rows = [r for r in rows if r.status in wanted]
    if q and q.strip():
        needle = q.strip().upper()
        rows = [r for r in rows if needle in r.reference.upper() or needle in (r.title or "").upper()]
    cases, bugs = _trace_cases(uow, ctx, rows, release_id)
    views = {v.id: v for v in rq.refs_by_ids(uow.session, ctx, [r.ref_id for r in rows])}
    return s.TraceabilityRead(
        release_id=release_id,
        summary=summary,
        rows=[
            s.TraceRow(
                requirement=_read(views[r.ref_id], r.status),
                linked_cases=len(r.cases),
                status_in_release=r.status,
                cases=cases.get(r.ref_id, []),
                bugs=bugs.get(r.ref_id, []),
            )
            for r in rows
            if r.ref_id in views
        ],
    )
