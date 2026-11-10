"""Administration (docs/06 §4.2, §4.12; US-162…165; M8b): audit log, access review, system status and
jobs."""

from __future__ import annotations

from datetime import date
from typing import Any, Final, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from tcms.api.deps import (
    ReadUow,
    Uow,
    app_state,
    org_context,
    project_context,
)
from tcms.api.v1.health import run_checks
from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.enums import JobStatus
from tcms.core.errors import FieldError, ValidationFailed
from tcms.core.pagination import Page, PageParams
from tcms.core.uow import UnitOfWork
from tcms.core.version import API_VERSION
from tcms.platform import attachments, spreadsheets, transfers
from tcms.platform.attachments import content_disposition
from tcms.platform.audit import queries as audit_queries
from tcms.platform.jobs import admin as jobs_admin
from tcms.workspace import access_review
from tcms.workspace import admin_schemas as s
from tcms.workspace import queries as workspace_queries

router = APIRouter(prefix="/api/v1", tags=["administration"])

AUDIT_EXPORT_MAX: Final = 100_000
AUDIT_HEADER: Final = [
    "When",
    "Project",
    "Actor",
    "Actor type",
    "Action",
    "Record type",
    "Record",
    "Summary",
    "Changes",
    "IP",
    "Request",
]
AUDIT_KINDS: Final = ["datetime"] + ["text"] * (len(AUDIT_HEADER) - 1)


# -- audit log ---------------------------------------------------------------------------------------


def _filters(
    entity_type: str | None = Query(default=None, max_length=50),
    actor_id: UUID | None = None,
    action: str | None = Query(default=None, max_length=100),
    occurred_at__gte: date | None = None,
    occurred_at__lte: date | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> audit_queries.AuditFilter:
    # An inverted range matches nothing (as the activity feed): an empty page, not an error.
    return audit_queries.AuditFilter(
        entity_type=entity_type,
        actor_id=actor_id,
        action=action,
        occurred_from=occurred_at__gte,
        occurred_to=occurred_at__lte,
        q=q,
    )


def _project_keys(uow: UnitOfWork, org_id: UUID, rows: list[audit_queries.EventRow]) -> dict[UUID, str]:
    ids = {r.project_id for r in rows if r.project_id}
    if not ids:
        return {}
    return {p.id: p.key for p in workspace_queries.projects(uow.session, org_id, ids=ids, status=None)}


def _read(r: audit_queries.EventRow, keys: dict[UUID, str]) -> s.AuditEventRead:
    return s.AuditEventRead(
        **{k: v for k, v in vars(r).items() if k != "context"},
        project_key=keys.get(r.project_id) if r.project_id else None,
        context=r.context,
    )


def _changes_text(changes: dict[str, Any] | None) -> str:
    if not changes:
        return ""
    parts = []
    for field, value in changes.items():
        if isinstance(value, list) and len(value) == 2:
            parts.append(f"{field}: {value[0]!r} → {value[1]!r}")
        else:
            parts.append(f"{field}: {value!r}")
    return "; ".join(parts)


def _audit_csv(
    uow: UnitOfWork,
    ctx: AccessContext,
    rows: list[audit_queries.EventRow],
    *,
    file_stem: str,
) -> Response:
    if len(rows) > AUDIT_EXPORT_MAX:
        raise ValidationFailed(
            errors=[
                FieldError(
                    "format",
                    "too_many_rows",
                    f"More than {AUDIT_EXPORT_MAX:,} events match; narrow the dates or filters",
                )
            ]
        )
    keys = _project_keys(uow, ctx.principal.organization_id, rows)
    cells = [
        [
            r.occurred_at,
            keys.get(r.project_id, "") if r.project_id else "",
            r.actor_display or "System",
            r.actor_type,
            r.action,
            r.entity_type,
            r.entity_key or "",
            r.summary or "",
            _changes_text(r.changes),
            r.context.get("ip", ""),
            r.context.get("request_id", ""),
        ]
        for r in rows
    ]
    data = spreadsheets.write_csv(AUDIT_HEADER, cells, AUDIT_KINDS)
    transfers.audit_export(uow, ctx, entity="audit_events", rows=len(rows), format="csv", transfer_id=None)
    return _file(data, "csv", f"{file_stem}-{clock.now():%Y%m%d-%H%M}.csv")


def _file(data: bytes, fmt: str, name: str) -> Response:
    return Response(
        data,
        media_type=spreadsheets.MEDIA[fmt],
        headers={
            "Content-Disposition": content_disposition("attachment", name),
            "X-Content-Type-Options": "nosniff",
        },
    )


_CSV_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    200: {"content": {"text/csv": {}}, "description": "JSON page, or the CSV file with `?format=csv`"}
}


@router.get("/organization/audit-events", response_model=Page[s.AuditEventRead], responses=_CSV_RESPONSES)
def org_audit_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    project_id: UUID | None = None,
    format: Literal["json", "csv"] = "json",
    filters: audit_queries.AuditFilter = Depends(_filters),
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Uow,
) -> Any:
    """US-162 / FR-AUD-002: every event of the organization, newest first; CSV up to 100,000 events."""
    ctx.require("org.audit.view")
    org_id = ctx.principal.organization_id
    f = audit_queries.AuditFilter(**{**vars(filters), "project_id": project_id})
    if format == "csv":
        rows = audit_queries.export_events(uow.session, org_id, filters=f, limit=AUDIT_EXPORT_MAX)
        return _audit_csv(uow, ctx, rows, file_stem="audit-log")
    items, total = audit_queries.events(
        uow.session, org_id, PageParams(page=page, page_size=page_size), filters=f
    )
    keys = _project_keys(uow, org_id, items)
    return Page[s.AuditEventRead](
        items=[_read(r, keys) for r in items], page=page, page_size=page_size, total=total
    )


@router.get(
    "/projects/{project_id}/audit-events", response_model=Page[s.AuditEventRead], responses=_CSV_RESPONSES
)
def project_audit_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    format: Literal["json", "csv"] = "json",
    filters: audit_queries.AuditFilter = Depends(_filters),
    ctx: AccessContext = Depends(project_context),
    uow: UnitOfWork = Uow,
) -> Any:
    """docs/06 §4.12: the project's audit log (`project.audit.view`), filters as the organization log."""
    ctx.require("project.audit.view")
    org_id = ctx.principal.organization_id
    if format == "csv":
        rows = audit_queries.export_events(
            uow.session, org_id, project_id=ctx.pid, filters=filters, limit=AUDIT_EXPORT_MAX
        )
        project = workspace_queries.project_ref(uow.session, org_id, ctx.pid)
        return _audit_csv(uow, ctx, rows, file_stem=f"{project.key if project else 'project'}-audit-log")
    items, total = audit_queries.events(
        uow.session, org_id, PageParams(page=page, page_size=page_size), project_id=ctx.pid, filters=filters
    )
    keys = _project_keys(uow, org_id, items)
    return Page[s.AuditEventRead](
        items=[_read(r, keys) for r in items], page=page, page_size=page_size, total=total
    )


# -- access review -----------------------------------------------------------------------------------


@router.get(
    "/organization/access-review",
    response_model=list[s.AccessReviewRow],
    responses={
        200: {
            "content": {"text/csv": {}, spreadsheets.MEDIA["xlsx"]: {}},
            "description": "Rows as JSON, or the file with `?format=csv|xlsx`",
        }
    },
)
def get_access_review(
    format: Literal["json", "csv", "xlsx"] = "json",
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = Uow,
) -> Any:
    """US-163 / FR-AUD-004 / TCMS-133: one row per user × scope (organization, then each project)."""
    ctx.require("org.audit.view")
    rows = access_review.rows(uow.session, ctx.principal.organization_id)
    if format == "json":
        return [s.AccessReviewRow(**vars(r)) for r in rows]
    cells = [r.as_cells() for r in rows]
    if format == "csv":
        data = spreadsheets.write_csv(access_review.HEADER, cells, access_review.KINDS)
    else:
        data = spreadsheets.write_xlsx(access_review.HEADER, cells, "Access review", access_review.KINDS)
    transfers.audit_export(uow, ctx, entity="access_review", rows=len(rows), format=format, transfer_id=None)
    return _file(data, format, f"access-review-{clock.now():%Y%m%d-%H%M}.{format}")


# -- system status and jobs --------------------------------------------------------------------------


@router.get("/organization/system-status", response_model=s.SystemStatus)
def system_status(
    request: Request, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = ReadUow
) -> s.SystemStatus:
    """US-165: version, migration head, database and storage checks, job queue and stored files."""
    ctx.require("org.manage")
    state = app_state(request)
    checks = run_checks(state)
    org_id = ctx.principal.organization_id
    st = jobs_admin.stats(uow.session, org_id)
    files, size = attachments.usage(uow.session, org_id)
    return s.SystemStatus(
        version=API_VERSION,
        environment=state.settings.tcms_env.value,
        migration_current=checks.migration_current,
        migration_head=checks.migration_head,
        checks={k: s.CheckRead(ok=v.ok, detail=v.detail) for k, v in checks.checks.items()},
        jobs=s.JobStatsRead(
            counts=st.counts, oldest_due_at=st.oldest_due_at, last_succeeded_at=st.last_succeeded_at
        ),
        attachments=s.StorageUsage(files=files, bytes=size),
        audit_retention_years=workspace_queries.org_policy(uow.session, org_id).audit_retention_years,
        checked_at=clock.now(),
    )


@router.get("/organization/jobs", response_model=Page[s.JobRead])
def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: list[JobStatus] = Query(default=[JobStatus.failed, JobStatus.dead]),
    type: str | None = Query(default=None, max_length=100),
    ctx: AccessContext = Depends(org_context),
    uow: UnitOfWork = ReadUow,
) -> Page[s.JobRead]:
    """TCMS-139: failed and dead jobs by default (`?status=` repeats), newest first."""
    ctx.require("org.manage")
    rows, total = jobs_admin.jobs(
        uow.session,
        ctx.principal.organization_id,
        PageParams(page=page, page_size=page_size),
        statuses=status,
        job_type=type,
    )
    return Page[s.JobRead](
        items=[s.JobRead(**vars(r)) for r in rows], page=page, page_size=page_size, total=total
    )


@router.post("/organization/jobs/{job_id}/retry", response_model=s.JobRead)
def retry_job(job_id: UUID, ctx: AccessContext = Depends(org_context), uow: UnitOfWork = Uow) -> s.JobRead:
    """Put a failed or dead job back in the queue with a fresh attempt budget; `409 invalid_status`
    otherwise."""
    return s.JobRead(**vars(jobs_admin.retry(uow, ctx, job_id)))
