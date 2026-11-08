"""Job queue administration (docs/06 §4.2, US-165, TCMS-139): counts, the failed/dead list, retry.

An organization administrator sees the organization's jobs and the installation's scheduled jobs
(`organization_id IS NULL`). Payloads are never returned: some carry links or addresses meant for one
person (password reset, invitations).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.core.enums import JobStatus
from tcms.core.errors import Conflict, NotFound
from tcms.core.pagination import PageParams
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.platform.jobs import queue
from tcms.platform.models import Job

ERROR_CHARS: Final = 2_000


@dataclass(frozen=True)
class JobStats:
    counts: dict[str, int]  # every JobStatus value
    oldest_due_at: datetime | None  # the longest-waiting queued job that is due now
    last_succeeded_at: datetime | None


@dataclass(frozen=True)
class JobRow:
    id: UUID
    type: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    run_at: datetime
    created_at: datetime
    finished_at: datetime | None
    system: bool  # an installation job, not tied to an organization


def _visible(org_id: UUID) -> ColumnElement[bool]:
    return or_(Job.organization_id == org_id, Job.organization_id.is_(None))


def stats(s: Session, org_id: UUID) -> JobStats:
    counts = {st.value: 0 for st in JobStatus}
    for status, n in s.execute(
        select(Job.status, func.count()).where(_visible(org_id)).group_by(Job.status)
    ).all():
        counts[status.value if hasattr(status, "value") else str(status)] = int(n)
    oldest = s.execute(
        select(func.min(Job.run_at)).where(
            _visible(org_id), Job.status == JobStatus.queued, Job.run_at <= clock.now()
        )
    ).scalar_one()
    last = s.execute(
        select(func.max(Job.finished_at)).where(_visible(org_id), Job.status == JobStatus.succeeded)
    ).scalar_one()
    return JobStats(counts, oldest, last)


def _row(j: Job) -> JobRow:
    error = j.last_error
    if error and len(error) > ERROR_CHARS:
        error = error[:ERROR_CHARS] + "…"
    return JobRow(
        j.id,
        j.type,
        j.status.value,
        j.attempts,
        j.max_attempts,
        error,
        j.run_at,
        j.created_at,
        j.finished_at,
        j.organization_id is None,
    )


def jobs(
    s: Session, org_id: UUID, page: PageParams, *, statuses: list[JobStatus], job_type: str | None = None
) -> tuple[list[JobRow], int]:
    stmt = select(Job).where(_visible(org_id))
    if statuses:
        stmt = stmt.where(Job.status.in_(statuses))
    if job_type:
        stmt = stmt.where(Job.type == job_type)
    total = int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = s.execute(
        stmt.order_by(func.coalesce(Job.finished_at, Job.run_at).desc(), Job.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return [_row(j) for j in rows], total


def job(s: Session, org_id: UUID, job_id: UUID) -> JobRow | None:
    j = s.execute(
        select(Job).where(Job.id == job_id, _visible(org_id)).execution_options(populate_existing=True)
    ).scalar_one_or_none()
    return _row(j) if j else None


RETRYABLE: Final = (JobStatus.failed.value, JobStatus.dead.value)


def retry(uow: UnitOfWork, ctx: AccessContext, job_id: UUID) -> JobRow:
    """Queue a failed or dead job again with a fresh attempt budget (`job.retried`)."""
    ctx.require("org.manage")
    s = uow.session
    found = job(s, ctx.principal.organization_id, job_id)
    if found is None:
        raise NotFound("Job not found")
    if found.status not in RETRYABLE or not queue.retry_dead(s, job_id):
        raise Conflict("Only failed or dead jobs can be retried", code="invalid_status")
    uow.audit(
        ctx,
        "job.retried",
        AuditTarget("job", job_id, found.type),
        summary=f"{ctx.principal.display_name} retried job {found.type}",
        extra={"previous_status": found.status, "attempts": found.attempts},
    )
    s.flush()
    retried = job(s, ctx.principal.organization_id, job_id)
    assert retried is not None
    return retried
