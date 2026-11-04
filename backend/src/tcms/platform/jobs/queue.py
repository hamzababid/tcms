"""PostgreSQL job queue (docs/03 §10, docs/04 §10.1, ADR-005).

States: `queued` → `running` → `succeeded` | `failed` (permanent error, no retry) | `dead` (retries
exhausted). A retryable failure goes back to `queued` with exponential backoff.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from tcms.core import clock, ids
from tcms.core.enums import JobStatus
from tcms.core.uow import JobRequest, UnitOfWork
from tcms.platform.models import Job

STALE_AFTER = timedelta(minutes=15)
MAX_BACKOFF = timedelta(hours=4)
BASE_BACKOFF = timedelta(seconds=30)


class PermanentJobError(Exception):
    """Raised by a handler when retrying cannot help; the job ends as `failed`."""


@dataclass(frozen=True)
class JobInfo:
    id: UUID
    type: str
    payload: dict[str, Any]
    organization_id: UUID | None
    attempts: int
    max_attempts: int


JobHandler = Callable[[JobInfo, UnitOfWork], None]
_handlers: dict[str, JobHandler] = {}


def job_handler(job_type: str) -> Callable[[JobHandler], JobHandler]:
    def register(fn: JobHandler) -> JobHandler:
        _handlers[job_type] = fn
        return fn

    return register


def handler_for(job_type: str) -> JobHandler | None:
    return _handlers.get(job_type)


def backoff(attempts: int) -> timedelta:
    """min(2^attempts × 30 s, 4 h) (docs/04 §10.1)."""
    delay: timedelta = BASE_BACKOFF * (2**attempts)
    return min(delay, MAX_BACKOFF)


def write_jobs(session: Session, requests: list[JobRequest]) -> None:
    now = clock.now()
    for r in requests:
        stmt = pg_insert(Job).values(
            id=ids.new_id(),
            organization_id=r.organization_id,
            type=r.type,
            payload=r.payload,
            status=JobStatus.queued,
            run_at=r.run_at or now,
            attempts=0,
            max_attempts=r.max_attempts,
            dedupe_key=r.dedupe_key,
            created_at=now,
        )
        if r.dedupe_key is not None:
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["dedupe_key"],
                index_where=text("dedupe_key IS NOT NULL AND status IN ('queued','running')"),
            )
        session.execute(stmt)


def claim_next(session: Session, worker_id: str) -> JobInfo | None:
    """Lock and mark the next due job as running. Caller commits."""
    now = clock.now()
    job = session.execute(
        select(Job)
        .where(Job.status == JobStatus.queued, Job.run_at <= now)
        .order_by(Job.run_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.running
    job.locked_by = worker_id
    job.locked_at = now
    job.attempts += 1
    return JobInfo(job.id, job.type, dict(job.payload), job.organization_id, job.attempts, job.max_attempts)


def mark_succeeded(session: Session, job_id: UUID) -> None:
    session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=JobStatus.succeeded, finished_at=clock.now(), locked_by=None, locked_at=None)
    )


def mark_failure(session: Session, job: JobInfo, error: str, *, permanent: bool) -> JobStatus:
    now = clock.now()
    if permanent:
        status, run_at, finished = JobStatus.failed, None, now
    elif job.attempts >= job.max_attempts:
        status, run_at, finished = JobStatus.dead, None, now
    else:
        status, run_at, finished = JobStatus.queued, now + backoff(job.attempts), None
    values: dict[str, Any] = {
        "status": status,
        "last_error": error[:10_000],
        "locked_by": None,
        "locked_at": None,
        "finished_at": finished,
    }
    if run_at is not None:
        values["run_at"] = run_at
    session.execute(update(Job).where(Job.id == job.id).values(**values))
    return status


def requeue_stale(session: Session, *, now: datetime | None = None) -> int:
    """Jobs left `running` by a crashed worker for > 15 min go back to the queue."""
    cutoff = (now or clock.now()) - STALE_AFTER
    result = session.execute(
        update(Job)
        .where(and_(Job.status == JobStatus.running, Job.locked_at < cutoff))
        .values(
            status=JobStatus.queued,
            locked_by=None,
            locked_at=None,
            last_error="requeued: worker lock expired",
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def retry_dead(session: Session, job_id: UUID) -> bool:
    """Admin action (docs/06 §4.2): put a dead/failed job back in the queue with a fresh budget."""
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_([JobStatus.dead, JobStatus.failed]))
        .values(status=JobStatus.queued, run_at=clock.now(), attempts=0, finished_at=None)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
