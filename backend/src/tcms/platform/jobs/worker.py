"""Worker loop and scheduler (docs/03 §10). Runs as `tcms worker`."""

from __future__ import annotations

import os
import socket
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tcms.core import clock
from tcms.core.uow import unit_of_work
from tcms.platform.jobs import queue
from tcms.platform.models import Job

log = structlog.get_logger()


@dataclass(frozen=True)
class Schedule:
    """A recurring job. `bucket(now)` returns the period key; one job per key is enqueued (dedupe)."""

    job_type: str
    period: timedelta
    offset: timedelta = timedelta(0)

    def bucket(self, now: datetime) -> str:
        seconds = int((now - self.offset).timestamp() // self.period.total_seconds())
        return f"schedule:{self.job_type}:{seconds}"


SCHEDULES: list[Schedule] = []


def schedule(job_type: str, *, period: timedelta, offset: timedelta = timedelta(0)) -> None:
    if all(s.job_type != job_type for s in SCHEDULES):
        SCHEDULES.append(Schedule(job_type, period, offset))


def run_scheduler_tick(factory: sessionmaker[Session], *, now: datetime | None = None) -> None:
    """Enqueue each schedule's job for the current period unless that period already has one. The unique
    dedupe index only covers queued and running jobs, so a period whose job already finished is skipped
    here; otherwise every tick (30 s) would run it again."""
    current = now or clock.now()
    with unit_of_work(factory) as uow:
        buckets = {s.bucket(current): s for s in SCHEDULES}
        done = set(
            uow.session.execute(select(Job.dedupe_key).where(Job.dedupe_key.in_(list(buckets)))).scalars()
        )
        for key, s in buckets.items():
            if key not in done:
                uow.enqueue_job(s.job_type, {}, dedupe_key=key)


def run_one(factory: sessionmaker[Session], worker_id: str) -> bool:
    """Claim and execute one job. Returns False when the queue had nothing due."""
    with unit_of_work(factory) as claim_uow:
        job = queue.claim_next(claim_uow.session, worker_id)
    if job is None:
        return False
    handler = queue.handler_for(job.type)
    try:
        if handler is None:
            raise queue.PermanentJobError(f"no handler registered for job type {job.type!r}")
        with unit_of_work(factory) as uow:
            handler(job, uow)
    except Exception as exc:
        permanent = isinstance(exc, queue.PermanentJobError)
        error = "".join(traceback.format_exception_only(exc)).strip()
        with unit_of_work(factory) as fail_uow:
            status = queue.mark_failure(fail_uow.session, job, error, permanent=permanent)
        log.warning("job.failed", job_id=str(job.id), job_type=job.type, attempts=job.attempts, status=status)
        return True
    with unit_of_work(factory) as done_uow:
        queue.mark_succeeded(done_uow.session, job.id)
    log.info("job.succeeded", job_id=str(job.id), job_type=job.type, attempts=job.attempts)
    return True


class Worker:
    def __init__(self, factory: sessionmaker[Session], *, concurrency: int, poll_interval: float) -> None:
        self.factory = factory
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.stop_event = threading.Event()
        self.base_id = f"{socket.gethostname()}:{os.getpid()}"

    def _loop(self, n: int) -> None:
        worker_id = f"{self.base_id}:{n}"
        while not self.stop_event.is_set():
            try:
                if not run_one(self.factory, worker_id):
                    self.stop_event.wait(self.poll_interval)
            except Exception:
                log.exception("worker.loop_error", worker_id=worker_id)
                self.stop_event.wait(self.poll_interval)

    def _housekeeping(self) -> None:
        while not self.stop_event.is_set():
            try:
                run_scheduler_tick(self.factory)
                with unit_of_work(self.factory) as uow:
                    requeued = queue.requeue_stale(uow.session)
                if requeued:
                    log.warning("worker.requeued_stale", count=requeued)
            except Exception:
                log.exception("worker.housekeeping_error")
            self.stop_event.wait(30)

    def run(self) -> None:
        threads = [
            threading.Thread(target=self._loop, args=(i,), daemon=True) for i in range(self.concurrency)
        ]
        threads.append(threading.Thread(target=self._housekeeping, daemon=True))
        for t in threads:
            t.start()
        log.info("worker.started", concurrency=self.concurrency, schedules=[s.job_type for s in SCHEDULES])
        try:
            while not self.stop_event.is_set():
                self.stop_event.wait(1)
        finally:
            self.stop_event.set()
            for t in threads:
                t.join(timeout=30)
            log.info("worker.stopped")
