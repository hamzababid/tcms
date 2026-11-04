"""Job-table retention (docs/05 §9): succeeded 14 days; failed/dead 90 days."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, delete, or_

from tcms.core import clock
from tcms.core.enums import JobStatus
from tcms.core.uow import UnitOfWork
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule
from tcms.platform.models import Job

SUCCEEDED_RETENTION = timedelta(days=14)
FAILED_RETENTION = timedelta(days=90)


@job_handler("jobs.cleanup")
def cleanup_jobs(job: JobInfo, uow: UnitOfWork) -> None:
    now = clock.now()
    uow.session.execute(
        delete(Job).where(
            or_(
                and_(Job.status == JobStatus.succeeded, Job.finished_at < now - SUCCEEDED_RETENTION),
                and_(
                    Job.status.in_([JobStatus.failed, JobStatus.dead]),
                    Job.finished_at < now - FAILED_RETENTION,
                ),
            )
        )
    )


schedule("jobs.cleanup", period=timedelta(days=1), offset=timedelta(hours=3))
