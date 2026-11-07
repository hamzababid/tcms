"""Dashboards, readiness, decisions, reports and exports (docs/06 §4.3, §4.10, §4.13, §5.9; M7)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from tcms.api.deps import (
    Auth,
    get_read_uow,
    get_uow,
    org_context,
    project_context,
    project_context_allow_archived,
    project_context_from,
)
from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, InvalidFilter, NotFound, PermissionDenied, ValidationFailed
from tcms.core.uow import UnitOfWork
from tcms.execution.schemas import ExecutionSummaryRead, KeyRef, RateRead, Ref
from tcms.identity import queries as identity_queries
from tcms.identity.schemas import UserRef
from tcms.identity.service import Authenticated
from tcms.platform import transfers
from tcms.platform.attachments import content_disposition
from tcms.reporting import coverage, exports, queries, readiness, reports, snapshots
from tcms.reporting import schemas as rs
from tcms.reporting.metrics import ExecutionSummary, Rate, RequirementCoverage
from tcms.reporting.queries import Scope
from tcms.requirements.schemas import CoverageRead
from tcms.requirements.schemas import Rate as CoverageRate
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace

router = APIRouter(prefix="/api/v1", tags=["reporting"])

ReleaseCtx = Depends(project_context_from("release", "release_id"))
PlanCtx = Depends(project_context_from("test_plan", "plan_id"))
TransferCtx = Depends(project_context_from("data_transfer", "transfer_id"))


# -- conversions -----------------------------------------------------------------------------------


def summary_read(m: ExecutionSummary) -> ExecutionSummaryRead:
    return ExecutionSummaryRead.model_validate(m, from_attributes=True)


def rate_read(r: Rate) -> RateRead:
    return RateRead(numerator=r.numerator, denominator=r.denominator, value=r.value)


def coverage_read(c: RequirementCoverage) -> CoverageRead:
    return CoverageRead(
        total=c.total,
        covered=c.covered,
        not_covered=c.not_covered,
        passed=c.passed,
        failed=c.failed,
        blocked=c.blocked,
        not_run=c.not_run,
        coverage=CoverageRate(**vars(c.coverage)),
        verified=CoverageRate(**vars(c.verified)),
    )


def _users(uow: UnitOfWork, ids_: set[UUID | None]) -> dict[UUID, UserRef]:
    found = identity_queries.user_refs(uow.session, {i for i in ids_ if i})
    return {k: UserRef(**vars(v)) for k, v in found.items()}


def _release(uow: UnitOfWork, ctx: AccessContext, release_id: UUID | None) -> Any:
    if release_id is None:
        return None
    rel = workspace_queries.release(uow.session, ctx.principal.organization_id, release_id)
    if rel is None or rel.project_id != ctx.pid:
        raise NotFound("Unknown release")
    return rel


def _decision_read(uow: UnitOfWork, d: Any, users: dict[UUID, UserRef] | None = None) -> rs.DecisionDetail:
    users = users if users is not None else _users(uow, {d.decided_by})
    return rs.DecisionDetail(
        id=d.id,
        decision=d.decision.value,
        comment=d.comment,
        risks=d.risks,
        decided_by=users.get(d.decided_by),
        decided_at=d.decided_at,
        ready=bool(d.snapshot.get("ready")),
        snapshot=d.snapshot,
    )


def _brief(d: rs.DecisionDetail | None) -> rs.DecisionRead | None:
    return rs.DecisionRead(**d.model_dump(exclude={"snapshot"})) if d else None


def _readiness_read(
    uow: UnitOfWork, r: readiness.Readiness, *, release: Any = None, plan: Any = None
) -> rs.ReadinessRead:
    latest = None
    if release is not None:
        found = workspace_queries.latest_decisions(uow.session, release.organization_id, [release.id])
        if release.id in found:
            latest = _brief(_decision_read(uow, found[release.id]))
    return rs.ReadinessRead(
        release=Ref(id=release.id, name=release.name) if release is not None else None,
        plan=KeyRef(id=plan.id, key=plan.key, title=plan.name) if plan is not None else None,
        ready=r.ready,
        uses_defaults=r.uses_defaults,
        rules=[
            rs.RuleRead(
                type=x.type,
                threshold=x.threshold,
                params=x.params,
                actual=rate_read(x.actual) if x.actual else None,
                count=x.count,
                met=x.met,
                note=x.note,
                plan=rs.PlanBrief(id=x.plan.id, key=x.plan.key, name=x.plan.name) if x.plan else None,
            )
            for x in r.rules
        ],
        plans=[
            rs.PlanReadiness(plan=rs.PlanBrief(id=p.id, key=p.key, name=p.name), ready=ok)
            for p, ok in r.plans
        ],
        summary=summary_read(r.summary),
        coverage=coverage_read(r.coverage),
        latest_decision=latest,
        evaluated_at=r.evaluated_at,
    )


# -- releases, readiness, decisions ----------------------------------------------------------------


@router.get("/projects/{project_id}/release-summaries", response_model=list[rs.ReleaseListItem])
def release_summaries(
    include_archived: bool = False,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> list[rs.ReleaseListItem]:
    """Releases page (docs/07 §5.15): each release with its execution summary, readiness and latest"
    " decision."""
    ctx.require("project.view")
    org = ctx.principal.organization_id
    rels = [
        r
        for r in workspace_queries.releases(uow.session, org, ctx.pid)
        if include_archived or r.status.value != "archived"
    ]
    latest = workspace_queries.latest_decisions(uow.session, org, [r.id for r in rels])
    users = _users(uow, {d.decided_by for d in latest.values()})
    out = []
    for r in rels:
        # Readiness is evaluated for open releases; released and archived ones show their last decision.
        evaluated = r.status.value in ("planned", "active")
        ready = readiness.release_readiness(uow.session, ctx, r.id) if evaluated else None
        summ = ready.summary if ready else queries.summary(uow.session, ctx, Scope(release_id=r.id))
        counts = queries.release_counts(uow.session, ctx, r.id)
        out.append(
            rs.ReleaseListItem(
                id=r.id,
                name=r.name,
                status=r.status.value,
                start_date=r.start_date,
                target_date=r.target_date,
                released_at=r.released_at,
                summary=summary_read(summ),
                ready=ready.ready if ready else None,
                latest_decision=_brief(_decision_read(uow, latest[r.id], users)) if r.id in latest else None,
                plan_count=counts[0],
                cycle_count=counts[1],
            )
        )
    return out


@router.get("/releases/{release_id}/readiness", response_model=rs.ReadinessRead)
def release_readiness(
    release_id: UUID, ctx: AccessContext = ReleaseCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> rs.ReadinessRead:
    """FR-RPT-006 / docs/02 §11.4 (D1: per plan over its own cycles; defaults when no plan has rules)."""
    ctx.require("project.view")
    rel = _release(uow, ctx, release_id)
    return _readiness_read(uow, readiness.release_readiness(uow.session, ctx, release_id), release=rel)


@router.get("/test-plans/{plan_id}/readiness", response_model=rs.ReadinessRead)
def plan_readiness(
    plan_id: UUID, ctx: AccessContext = PlanCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> rs.ReadinessRead:
    """L25: the plan Overview shows its exit rules as met / not met."""
    ctx.require("project.view")
    r = readiness.plan_readiness(uow.session, ctx, plan_id)
    if r is None:
        raise NotFound()
    plan = r.plans[0][0]
    from tcms.planning import queries as plan_queries

    p = plan_queries.plan_detail(uow.session, ctx, plan_id)
    rel = _release(uow, ctx, p.release_id) if p and p.release_id else None
    return _readiness_read(uow, r, release=rel, plan=plan)


@router.get("/releases/{release_id}/decisions", response_model=list[rs.DecisionDetail])
def list_decisions(
    release_id: UUID, ctx: AccessContext = ReleaseCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> list[rs.DecisionDetail]:
    """Decision timeline, newest first, each with its frozen snapshot."""
    ctx.require("project.view")
    _release(uow, ctx, release_id)
    rows = workspace_queries.decisions(uow.session, ctx.principal.organization_id, release_id)
    users = _users(uow, {d.decided_by for d in rows})
    return [_decision_read(uow, d, users) for d in rows]


@router.post(
    "/releases/{release_id}/decisions", response_model=rs.DecisionDetail, status_code=status.HTTP_201_CREATED
)
def record_decision(
    release_id: UUID,
    body: rs.DecisionCreate,
    ctx: AccessContext = ReleaseCtx,
    uow: UnitOfWork = Depends(get_uow),
) -> rs.DecisionDetail:
    """TCMS-116 / AC-REL-03: go, go with risks (risks required) or no-go; the readiness snapshot is computed
    here and stored with the decision (append-only)."""
    ctx.require("release.manage")
    rel = _release(uow, ctx, release_id)
    snapshot = readiness.as_json(readiness.release_readiness(uow.session, ctx, release_id))
    snapshot["release"] = {"id": str(rel.id), "name": rel.name, "status": rel.status.value}
    row = workspace.record_decision(
        uow,
        ctx,
        release_id,
        decision=body.decision,
        comment=body.comment,
        risks=body.risks,
        snapshot=snapshot,
    )
    return _decision_read(uow, row)


# -- dashboards ------------------------------------------------------------------------------------


def _scope(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    release_id: UUID | None,
    cycle_ids: str | None,
    environment_id: UUID | None,
    module_folder_id: UUID | None,
    tester_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> Scope:
    _release(uow, ctx, release_id)
    ids_: tuple[UUID, ...] | None = None
    if cycle_ids:
        try:
            ids_ = tuple(UUID(x.strip()) for x in cycle_ids.split(",") if x.strip())
        except ValueError as exc:
            raise InvalidFilter("cycle_ids must be IDs separated by commas") from exc
    if date_from and date_to and date_to < date_from:
        raise ValidationFailed(errors=[FieldError("date_to", "before_start", "The end is before the start")])
    return Scope(
        release_id=release_id,
        cycle_ids=ids_,
        environment_id=environment_id,
        module_folder_id=module_folder_id,
        tester_id=tester_id,
        date_from=date_from,
        date_to=date_to,
    )


class _Filters:
    def __init__(
        self,
        release_id: UUID | None = None,
        cycle_ids: str | None = Query(default=None, description="Comma-separated cycle IDs"),
        environment_id: UUID | None = None,
        module_folder_id: UUID | None = None,
        tester_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> None:
        self.kw: dict[str, Any] = {
            "release_id": release_id,
            "cycle_ids": cycle_ids,
            "environment_id": environment_id,
            "module_folder_id": module_folder_id,
            "tester_id": tester_id,
            "date_from": date_from,
            "date_to": date_to,
        }


@router.get("/projects/{project_id}/execution-summary", response_model=ExecutionSummaryRead)
def execution_summary(
    f: _Filters = Depends(),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> ExecutionSummaryRead:
    """docs/06 §5.7 for any filter of docs/02 §11.1 (BR-24)."""
    ctx.require("project.view")
    return summary_read(queries.summary(uow.session, ctx, _scope(uow, ctx, **f.kw)))


@router.get("/projects/{project_id}/dashboards/manager", response_model=rs.ManagerDashboard)
def manager_dashboard(
    f: _Filters = Depends(),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> rs.ManagerDashboard:
    """FR-RPT-001 / docs/02 §11.3: every widget of the project Overview in one response (TCMS-115)."""
    ctx.require("project.view")
    se = uow.session
    scope = _scope(uow, ctx, **f.kw)
    rel = _release(uow, ctx, scope.release_id)
    org = ctx.principal.organization_id
    brief = None
    if rel is not None:
        r = readiness.release_readiness(se, ctx, rel.id)
        brief = rs.ReadinessBrief(
            release=Ref(id=rel.id, name=rel.name),
            ready=r.ready,
            met=sum(1 for x in r.rules if x.met),
            total=len(r.rules),
            uses_defaults=r.uses_defaults,
        )
    cyc_rows = queries.cycles(se, ctx, scope)
    by_cycle = queries.counts_by_cycle(se, ctx, scope)
    releases = {x.id: x.name for x in workspace_queries.releases(se, org, ctx.pid)}
    envs = {e.id: e.name for e in workspace_queries.environments(se, org, ctx.pid, include_archived=True)}
    today = clock.now().date()
    cycles = [
        rs.CycleWidget(
            id=c.id,
            key=c.key,
            name=c.name,
            status=c.status,
            release=Ref(id=c.release_id, name=releases.get(c.release_id, "—")) if c.release_id else None,
            environment=Ref(id=c.environment_id, name=envs.get(c.environment_id, "—")),
            start_date=c.start_date,
            due_date=c.due_date,
            overdue=bool(c.due_date and c.due_date < today and c.status != "closed"),
            summary=summary_read(
                ExecutionSummary.from_counts(
                    by_cycle.get(c.id, ({}, 0))[0], needs_retest=by_cycle.get(c.id, ({}, 0))[1]
                )
            ),
        )
        for c in cyc_rows
    ]
    cov_rows = coverage.coverage_rows(se, ctx, scope.release_id)
    uncovered = [r for r in cov_rows if r.status == "not_covered"][:10]
    team = queries.team(se, ctx, scope)
    users = _users(uow, {t.user_id for t in team})
    return rs.ManagerDashboard(
        release=Ref(id=rel.id, name=rel.name) if rel is not None else None,
        readiness=brief,
        summary=summary_read(queries.summary(se, ctx, scope)),
        retest_count=queries.retest_count(se, ctx, scope),
        bugs=rs.BugMetricsRead(**vars(queries.bug_metrics(se, ctx, scope))),
        top_bugs=[rs.BugRowRead(**vars(b)) for b in queries.bugs_on_failing_runs(se, ctx, scope)],
        cycles=cycles,
        coverage=coverage_read(coverage.summary(cov_rows)),
        top_uncovered=[
            rs.UncoveredRef(id=r.ref_id, reference=r.reference, title=r.title, url=r.url) for r in uncovered
        ],
        regression=summary_read(queries.summary(se, ctx, Scope(**{**vars(scope), "tag": "regression"}))),
        team=[
            rs.TesterRead(
                user=users.get(t.user_id) if t.user_id else None,
                assigned=t.assigned,
                executed=t.executed,
                remaining=t.remaining,
                failed=t.failed,
                blocked=t.blocked,
            )
            for t in team
        ],
        repository=_repository_read(queries.repository(se, ctx, scope.module_folder_id)),
    )


def _repository_read(m: Any) -> rs.RepositoryRead:
    return rs.RepositoryRead(
        total_cases=m.total_cases,
        by_status=m.by_status,
        by_type=m.by_type,
        by_automation=m.by_automation,
        approved=rate_read(m.approved),
        automation_coverage=rate_read(m.automation_coverage),
        folders=m.folders,
        plans_by_status=m.plans_by_status,
    )


@router.get("/projects/{project_id}/dashboards/quality", response_model=rs.QualityDashboard)
def quality_dashboard(
    release_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> rs.QualityDashboard:
    """FR-RPT-003 / docs/02 §11.3: trends from daily snapshots plus today live (D5)."""
    ctx.require("project.view")
    se = uow.session
    rel = _release(uow, ctx, release_id)
    hi = date_to or clock.now().date()
    lo = date_from or hi - timedelta(days=29)
    if hi < lo or (hi - lo).days > 366:
        raise ValidationFailed(errors=[FieldError("date_from", "invalid_range", "Choose up to one year")])
    days = []
    today = clock.now().date()
    for d, c in snapshots.trend(se, ctx, release_id=release_id, lo=lo, hi=hi):
        executed = c["passed_on_day"] + c["failed_on_day"] + c["blocked_on_day"]
        days.append(
            rs.TrendDay(
                day=d,
                executed=executed,
                passed=c["passed_on_day"],
                failed=c["failed_on_day"],
                blocked=c["blocked_on_day"],
                pass_rate=rate_read(Rate.of(c["passed_on_day"], executed)),
                bug_links_added=c["bug_links_added"],
                failed_runs=c["failed"],
                req_total=c["req_total"],
                req_covered=c["req_covered"],
                req_passed=c["req_passed"],
                live=d == today,
            )
        )
    depth = int(
        workspace_queries.project_settings_of(se, ctx.principal.organization_id, ctx.pid).get(
            "report_module_depth", 1
        )
    )
    scope = Scope(release_id=release_id)
    modules = [
        rs.ModuleBugs(folder_id=i, name=n, references=c)
        for i, n, c in queries.bugs_by_module(se, ctx, scope, depth)
    ]
    quality = []
    org = ctx.principal.organization_id
    recent = [r for r in workspace_queries.releases(se, org, ctx.pid) if r.status.value != "archived"]
    recent.sort(key=lambda r: r.released_at or r.created_at, reverse=True)
    for r in recent[:6]:
        rscope = Scope(release_id=r.id)
        summ = queries.summary(se, ctx, rscope)
        snap = snapshots.at_or_before(se, ctx, r.id, r.released_at.date()) if r.released_at else None
        cov = coverage.summary(coverage.coverage_rows(se, ctx, r.id))
        quality.append(
            rs.ReleaseQuality(
                release=Ref(id=r.id, name=r.name),
                status=r.status.value,
                released_at=r.released_at,
                pass_rate_applicable=rate_read(summ.pass_rate_applicable),
                failed_at_release=snap["failed"] if snap else None,
                bug_references=queries.bug_metrics(se, ctx, rscope).linked,
                coverage=rate_read(cov.coverage),
                regression=summary_read(queries.summary(se, ctx, Scope(release_id=r.id, tag="regression"))),
            )
        )
    return rs.QualityDashboard(
        release=Ref(id=rel.id, name=rel.name) if rel is not None else None,
        date_from=lo,
        date_to=hi,
        days=days,
        bugs_by_module=modules,
        automation=_repository_read(queries.repository(se, ctx)),
        releases=quality,
        last_snapshot_day=queries.last_snapshot_day(se, ctx),
    )


@router.post(
    "/projects/{project_id}/metrics/refresh",
    response_model=rs.RefreshRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def refresh_metrics(
    ctx: AccessContext = Depends(project_context), uow: UnitOfWork = Depends(get_uow)
) -> rs.RefreshRead:
    """docs/06 §4.10: enqueue today's snapshot; one per project per 10 minutes (dedupe key)."""
    ctx.require("project.view")
    now = clock.now()
    bucket = int(now.timestamp() // 600)
    uow.enqueue_job(
        "metrics.snapshot",
        {"project_id": str(ctx.pid), "day": now.date().isoformat()},
        organization_id=ctx.principal.organization_id,
        dedupe_key=f"metrics.refresh:{ctx.pid}:{bucket}",
    )
    return rs.RefreshRead(job_id=None, queued=True)


@router.get("/organization/dashboard", response_model=rs.OrgDashboard)
def organization_dashboard(
    auth: Authenticated = Auth,
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> rs.OrgDashboard:
    """FR-WS-008 / US-146: Org Admins (org.reports.view) see every active project; others their own."""
    from tcms.core.context import AccessContext as Ctx
    from tcms.core.enums import ProjectStatus

    se = uow.session
    visible = None if ctx.has("org.reports.view") else identity_queries.member_project_ids(se, auth)
    projects = workspace_queries.projects(se, auth.organization_id, ids=visible, status=ProjectStatus.active)
    activity = queries.last_activity(se, auth.organization_id, [p.id for p in projects])
    rows = []
    for p in projects:
        pctx = Ctx.for_principal(auth.principal, ctx.meta, project_id=p.id)
        active = Scope(open_cycles_only=True)
        m = queries.summary(se, pctx, active)
        rows.append(
            rs.OrgProjectRow(
                project=KeyRef(id=p.id, key=p.key, title=p.name),
                active_cycles=len(queries.cycles(se, pctx, active)),
                summary=summary_read(m),
                failed=m.failed,
                bugs_on_failing_runs=queries.bug_metrics(se, pctx, active).on_failing_runs,
                last_activity=activity.get(p.id),
            )
        )
    return rs.OrgDashboard(projects=rows)


# -- reports and exports ---------------------------------------------------------------------------

_UUID_FILTERS = ("release_id", "environment_id", "module_folder_id", "tester_id", "assignee_id")
_LIST_FILTERS = ("status", "case_status", "case_type", "priority")
_PAGING = frozenset({"page", "page_size"})


def _report(name: str) -> reports.Report:
    r = reports.REPORTS.get(name)
    if r is None:
        raise NotFound("Unknown report")
    return r


def _report_filters(
    uow: UnitOfWork, ctx: AccessContext, report: reports.Report, raw: dict[str, str]
) -> reports.Filters:
    unknown = set(raw) - report.filters - _PAGING
    if unknown:
        raise InvalidFilter(f"Unknown filter for this report: {', '.join(sorted(unknown))}")
    vals: dict[str, Any] = {}
    for k in _UUID_FILTERS:
        if raw.get(k):
            try:
                vals[k] = UUID(raw[k])
            except ValueError as exc:
                raise InvalidFilter(f"{k} must be an ID") from exc
    dates: dict[str, date | None] = {}
    for k in ("date_from", "date_to"):
        try:
            dates[k] = date.fromisoformat(raw[k]) if raw.get(k) else None
        except ValueError as exc:
            raise InvalidFilter(f"{k} must be a date (YYYY-MM-DD)") from exc
    scope = _scope(
        uow,
        ctx,
        release_id=vals.get("release_id"),
        cycle_ids=raw.get("cycle_ids"),
        environment_id=vals.get("environment_id"),
        module_folder_id=vals.get("module_folder_id"),
        tester_id=vals.get("tester_id"),
        date_from=dates["date_from"],
        date_to=dates["date_to"],
    )
    if raw.get("tag"):
        scope = Scope(**{**vars(scope), "tag": raw["tag"].strip().lower()})
    lists = {k: tuple(x.strip() for x in raw.get(k, "").split(",") if x.strip()) for k in _LIST_FILTERS}
    return reports.Filters(
        scope=scope,
        status=lists["status"],
        assignee_id=vals.get("assignee_id"),
        case_status=lists["case_status"],
        case_type=lists["case_type"],
        priority=lists["priority"],
    )


def _report_meta(report: reports.Report) -> dict[str, Any]:
    return {
        "report": report.name,
        "title": report.title,
        "columns": [rs.ReportColumn(key=c.key, label=c.label, kind=c.kind) for c in report.columns],
        "filters": sorted(report.filters),
    }


@router.get("/projects/{project_id}/reports/{report}", response_model=rs.ReportRead)
def run_report(
    report: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Depends(get_read_uow),
) -> rs.ReportRead:
    """FR-RPT-004: `cycle-execution`, `results-history`, `bug-links`, `traceability`, `tester-activity`,
    `case-inventory`; filters per report (D9), unknown filters → 400."""
    ctx.require("project.view")
    rep = _report(report)
    f = _report_filters(uow, ctx, rep, dict(request.query_params))
    rows, total = rep.rows(uow.session, ctx, f, page_size, (page - 1) * page_size)
    return rs.ReportRead(
        **_report_meta(rep),
        items=[{k: reports.cell(v) for k, v in row.items()} for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/projects/{project_id}/reports/{report}/export",
    responses={
        200: {
            "content": {"text/csv": {}, exports.MEDIA["xlsx"]: {}},
            "description": "The file (≤ 10,000 rows)",
        },
        202: {"model": rs.ExportAccepted, "description": "Generated in the background; notified when ready"},
    },
)
def export_report(
    report: str,
    body: rs.ExportRequest,
    ctx: AccessContext = Depends(project_context_allow_archived),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """FR-RPT-005 / AC-RPT-04/05 / TCMS-117: CSV or XLSX with formula-injection protection."""
    ctx.require("data.export")
    rep = _report(report)
    f = _report_filters(uow, ctx, rep, body.filters)
    _, total = rep.rows(uow.session, ctx, f, 1, 0)
    project = workspace_queries.project_ref(uow.session, ctx.principal.organization_id, ctx.pid)
    assert project is not None
    if total > exports.ASYNC_MAX:
        raise ValidationFailed(
            f"{total:,} rows; narrow the filters to {exports.ASYNC_MAX:,} rows or fewer",
            errors=[FieldError("filters", "too_many_rows", "Too many rows for one export")],
        )
    if total <= exports.SYNC_MAX:
        data = exports.render(rep, reports.iterate(uow.session, ctx, rep, f), body.format)
        transfers.audit_export(
            uow, ctx, entity=f"report:{rep.name}", rows=total, format=body.format, transfer_id=None
        )
        name = exports.file_name(rep, body.format, project.key)
        return Response(
            content=data,
            media_type=exports.MEDIA[body.format],
            headers={
                "Content-Disposition": content_disposition("attachment", name),
                "X-Content-Type-Options": "nosniff",
            },
        )
    options = {"report": rep.name, "filters": exports.filters_to_json(f)}
    t = transfers.create_export(uow, ctx, entity=f"report:{rep.name}", format=body.format, options=options)
    p = ctx.principal
    uow.enqueue_job(
        "export.generate",
        {
            "actor": {
                "user_id": str(p.user_id),
                "org_id": str(p.organization_id),
                "is_admin": p.is_org_admin,
                "name": p.display_name,
                "permissions": sorted(ctx.permissions),
            },
            "request_id": ctx.request_id,
            "project_id": str(ctx.pid),
            "project_key": project.key,
            "transfer_id": str(t.id),
            "report": rep.name,
            "format": body.format,
            "filters": options["filters"],
        },
        organization_id=p.organization_id,
        dedupe_key=f"export:{t.id}",
    )
    return JSONResponse(
        rs.ExportAccepted(transfer_id=t.id, rows=total).model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
    )


def _transfer(
    uow: UnitOfWork, ctx: AccessContext, transfer_id: UUID, *, initiator_only: bool
) -> transfers.TransferView:
    t = transfers.get(uow.session, ctx.principal.organization_id, transfer_id)
    if t is None or t.project_id != ctx.pid:
        raise NotFound()
    mine = t.created_by == ctx.principal.user_id
    if not mine and (initiator_only or not ctx.has("project.configure")):
        raise PermissionDenied("project.configure", "Only the person who started the export can open it")
    return t


@router.get("/data-transfers/{transfer_id}", response_model=rs.TransferRead)
def get_transfer(
    transfer_id: UUID, ctx: AccessContext = TransferCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> rs.TransferRead:
    """docs/06 §4.13: initiator or project.configure."""
    t = _transfer(uow, ctx, transfer_id, initiator_only=False)
    return rs.TransferRead(
        id=t.id,
        kind=t.kind,
        entity=t.entity,
        status=t.status,
        format=t.format,
        summary=t.summary,
        errors=t.errors,
        created_at=t.created_at,
        finished_at=t.finished_at,
        expires_at=t.expires_at,
        download_url=f"/api/v1/data-transfers/{t.id}/download"
        if t.status in ("ready", "committed") and t.result_object_key
        else None,
    )


@router.get(
    "/data-transfers/{transfer_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "The export file"}},
)
def download_transfer(
    transfer_id: UUID, ctx: AccessContext = TransferCtx, uow: UnitOfWork = Depends(get_read_uow)
) -> StreamingResponse:
    """docs/06 §4.13: the initiator downloads a ready export or an import report within 7 days."""
    t = _transfer(uow, ctx, transfer_id, initiator_only=True)
    if t.status not in ("ready", "committed") or not t.result_object_key:
        raise NotFound("The file is not ready or has expired")
    st = transfers.store()
    obj = st.client.get_object(Bucket=st.bucket, Key=t.result_object_key)
    name = str(t.summary.get("file_name") or f"export.{t.format}")
    return StreamingResponse(
        obj["Body"].iter_chunks(),
        media_type=exports.MEDIA.get(t.format, "application/octet-stream"),
        headers={
            "Content-Disposition": content_disposition("attachment", name),
            "X-Content-Type-Options": "nosniff",
        },
    )
