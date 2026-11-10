"""Bug links (docs/06 §4.8; docs/02 §8; ADR-023)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from tcms.api.deps import (
    ReadUow,
    Uow,
    project_context,
    project_context_from,
    settings_dep,
)
from tcms.bugs import queries as bq
from tcms.bugs import schemas as s
from tcms.bugs import service
from tcms.core.config import Settings
from tcms.core.context import AccessContext
from tcms.core.pagination import Page
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["bugs"])

ResultCtx = Depends(project_context_from("test_result", "result_id"))
CaseCtx = Depends(project_context_from("test_case", "case_id"))
RunCtx = Depends(project_context_from("test_run", "run_id"))
CycleCtx = Depends(project_context_from("test_cycle", "cycle_id"))
LinkCtx = Depends(project_context_from("bug_link", "link_id"))


def _reads(uow: UnitOfWork, ctx: AccessContext, views: list[bq.LinkView]) -> list[s.BugLinkRead]:
    found = identity_queries.user_refs(uow.session, {v.created_by for v in views if v.created_by})
    users = {k: UserRef(**vars(v)) for k, v in found.items()}
    may_edit_any = ctx.has("defect.edit")
    return [
        s.BugLinkRead(
            id=v.id,
            reference=v.reference,
            url=v.url,
            title=v.title,
            test_case=s.LinkedCase(id=v.test_case_id, key=v.case_key, title=v.case_title),
            run_id=v.run_id,
            result_id=v.result_id,
            step_id=v.step_id,
            step_position=v.step_position,
            cycle=s.LinkedCycle(id=v.cycle_id, key=v.cycle_key) if v.cycle_id and v.cycle_key else None,
            run_status=v.run_status,
            attempt_no=v.attempt_no,
            attempt_status=v.attempt_status,
            created_by=users.get(v.created_by) if v.created_by else None,
            created_at=v.created_at,
            can_edit=may_edit_any or (v.created_by is not None and v.created_by == ctx.principal.user_id),
            row_version=v.row_version,
        )
        for v in views
    ]


def _one(uow: UnitOfWork, ctx: AccessContext, link_id: UUID) -> s.BugLinkRead:
    uow.session.flush()
    return _reads(uow, ctx, [bq.link_detail(uow.session, ctx, link_id)])[0]


@router.post(
    "/results/{result_id}/bug-links", response_model=s.BugLinkRead, status_code=status.HTTP_201_CREATED
)
def link_to_result(
    result_id: UUID, body: s.BugLinkCreate, ctx: AccessContext = ResultCtx, uow: UnitOfWork = Uow
) -> s.BugLinkRead:
    """BR-20 / AC-BUG-01, 02, 06: link a bug to an attempt (and step); draft or final."""
    row = service.link_to_result(
        uow, ctx, result_id, reference=body.reference, url=body.url, title=body.title, step_id=body.step_id
    )
    return _one(uow, ctx, row.id)


@router.post(
    "/test-cases/{case_id}/bug-links", response_model=s.BugLinkRead, status_code=status.HTTP_201_CREATED
)
def link_to_case(
    case_id: UUID, body: s.CaseBugLinkCreate, ctx: AccessContext = CaseCtx, uow: UnitOfWork = Uow
) -> s.BugLinkRead:
    """docs/02 §8.2 (TCMS-102): a bug found outside execution, linked to the case."""
    row = service.link_to_case(uow, ctx, case_id, reference=body.reference, url=body.url, title=body.title)
    return _one(uow, ctx, row.id)


@router.get("/test-cases/{case_id}/bug-links", response_model=list[s.BugLinkRead])
def case_links(case_id: UUID, ctx: AccessContext = CaseCtx, uow: UnitOfWork = ReadUow) -> list[s.BugLinkRead]:
    """Case Bugs tab: direct links and links through its runs."""
    ctx.require("project.view")
    return _reads(uow, ctx, bq.links_of_case(uow.session, ctx, case_id))


@router.get("/runs/{run_id}/bug-links", response_model=list[s.BugLinkRead])
def run_links(run_id: UUID, ctx: AccessContext = RunCtx, uow: UnitOfWork = ReadUow) -> list[s.BugLinkRead]:
    ctx.require("project.view")
    return _reads(uow, ctx, bq.links_of_run(uow.session, ctx, run_id))


@router.get("/cycles/{cycle_id}/bug-links", response_model=list[s.BugLinkRead])
def cycle_links(
    cycle_id: UUID,
    recent: bool = Query(default=False, description="Only the most recent distinct references (suggestions)"),
    ctx: AccessContext = CycleCtx,
    uow: UnitOfWork = ReadUow,
) -> list[s.BugLinkRead]:
    """Cycle detail Bugs column (docs/07 §5.8) or link-popover suggestions (`recent=true`)."""
    ctx.require("project.view")
    views = (bq.recent_references if recent else bq.links_of_cycle)(uow.session, ctx, cycle_id)
    return _reads(uow, ctx, views)


@router.patch("/bug-links/{link_id}", response_model=s.BugLinkRead)
def patch_link(
    link_id: UUID, body: s.BugLinkPatch, ctx: AccessContext = LinkCtx, uow: UnitOfWork = Uow
) -> s.BugLinkRead:
    """Correct URL or title: the person who linked it, or `defect.edit` (TCMS-107)."""
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    service.update_link(uow, ctx, link_id, fields=fields)
    return _one(uow, ctx, link_id)


@router.delete("/bug-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(link_id: UUID, ctx: AccessContext = LinkCtx, uow: UnitOfWork = Uow) -> Response:
    service.remove_link(uow, ctx, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/bugs", response_model=Page[s.BugSummaryRead])
def list_bugs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=100),
    cycle_id: UUID | None = None,
    failing: bool = Query(default=False, description="Only bugs linked to runs that are failed now"),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> Page[s.BugSummaryRead]:
    """docs/02 §8.4 (TCMS-105): one row per reference."""
    ctx.require("project.view")
    rows = bq.bug_list(uow.session, ctx, q=q, cycle_id=cycle_id, failing=failing)
    start = (page - 1) * page_size
    items = [s.BugSummaryRead(**vars(b)) for b in rows[start : start + page_size]]
    return Page[s.BugSummaryRead](items=items, page=page, page_size=page_size, total=len(rows))


@router.get("/projects/{project_id}/bugs/links", response_model=list[s.BugLinkRead])
def reference_links(
    reference: str = Query(min_length=1, max_length=100),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = ReadUow,
) -> list[s.BugLinkRead]:
    """Every link of one reference (Bugs list detail). The reference is a query parameter because tracker
    keys may contain `#` or `/`."""
    ctx.require("project.view")
    return _reads(uow, ctx, bq.links_of_reference(uow.session, ctx, reference))


@router.post("/projects/{project_id}/bugs/retest", response_model=s.RetestResponse)
def request_retest(
    body: s.RetestRequest, ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Uow
) -> s.RetestResponse:
    """BR-21 / AC-BUG-03 (TCMS-103): flag the eligible linked runs; `dry_run` previews the count."""
    out = service.request_retest(uow, ctx, body.reference, dry_run=body.dry_run)
    return s.RetestResponse(
        reference=out.reference,
        linked_runs=out.linked_runs,
        flagged=len(out.flagged_run_ids),
        dry_run=body.dry_run,
    )


@router.get("/results/{result_id}/bug-report", response_model=s.BugReportRead)
def bug_report(
    result_id: UUID,
    step_id: UUID | None = None,
    ctx: AccessContext = ResultCtx,
    uow: UnitOfWork = ReadUow,
    settings: Settings = Depends(settings_dep),
) -> s.BugReportRead:
    """ "Copy bug details" (docs/02 §8.2): Markdown for the team's tracker, with a link back to the run."""
    ctx.require("project.view")
    from tcms.execution import queries as eq

    view = eq.result_detail(uow.session, ctx, result_id)
    cycle_id = eq.runs_brief(uow.session, ctx, [view.run_id])[view.run_id].cycle_id
    project = workspace_queries.project_ref(uow.session, ctx.principal.organization_id, ctx.pid)
    cyc = eq.cycle(uow.session, ctx, cycle_id)
    base = settings.tcms_base_url.rstrip("/")
    run_url = f"{base}/p/{project.key if project else ''}/cycles/{cyc.key if cyc else ''}/run/{view.run_id}"
    return s.BugReportRead(text=bq.bug_report(uow.session, ctx, result_id, step_id, run_url))
