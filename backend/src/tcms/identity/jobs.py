"""Identity maintenance jobs (docs/05 §9)."""

from __future__ import annotations

from datetime import timedelta

from tcms.core.uow import UnitOfWork
from tcms.identity import service
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule


@job_handler("sessions.cleanup")
def sessions_cleanup(job: JobInfo, uow: UnitOfWork) -> None:
    service.purge_expired(uow)


schedule("sessions.cleanup", period=timedelta(hours=1))
