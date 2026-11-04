"""US-004 / NFR-REL-02 / TCMS-139: jobs retry with backoff, dead-letter, dedupe and stale requeue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from tcms.core import clock
from tcms.core.uow import UnitOfWork, unit_of_work
from tcms.platform.jobs import queue
from tcms.platform.jobs.queue import JobInfo, PermanentJobError, job_handler
from tcms.platform.jobs.worker import Schedule, run_one, run_scheduler_tick

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("clean_jobs")]

T0 = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
calls: list[dict[str, Any]] = []


@job_handler("test.always_fails")
def _fails(job: JobInfo, uow: UnitOfWork) -> None:
    calls.append({"attempt": job.attempts})
    raise ValueError("transient failure")


@job_handler("test.permanent")
def _permanent(job: JobInfo, uow: UnitOfWork) -> None:
    raise PermanentJobError("bad payload")


@job_handler("test.succeeds")
def _succeeds(job: JobInfo, uow: UnitOfWork) -> None:
    calls.append(job.payload)


def _job(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, attempts, run_at, last_error FROM jobs")).mappings().one()
    return dict(row)


def _enqueue(factory: sessionmaker[Session], job_type: str, **kw: Any) -> None:
    with unit_of_work(factory) as uow:
        uow.enqueue_job(job_type, kw.pop("payload", {}), **kw)


def test_failing_job_retried_with_backoff_then_dead(
    session_factory: sessionmaker[Session], app_engine: Engine
) -> None:
    calls.clear()
    with clock.frozen(T0):
        _enqueue(session_factory, "test.always_fails", max_attempts=3)
    now = T0
    for attempt in (1, 2):
        with clock.frozen(now):
            assert run_one(session_factory, "w1")
        job = _job(app_engine)
        assert job["status"] == "queued"
        assert job["attempts"] == attempt
        assert job["run_at"] == now + queue.backoff(attempt)
        assert "transient failure" in job["last_error"]
        with clock.frozen(job["run_at"] - timedelta(seconds=1)):
            assert not run_one(session_factory, "w1"), "not due before its backoff elapses"
        now = job["run_at"]
    with clock.frozen(now):
        assert run_one(session_factory, "w1")
    job = _job(app_engine)
    assert job["status"] == "dead"
    assert job["attempts"] == 3
    assert [c["attempt"] for c in calls] == [1, 2, 3]


def test_backoff_formula() -> None:
    assert queue.backoff(1) == timedelta(seconds=60)
    assert queue.backoff(3) == timedelta(seconds=240)
    assert queue.backoff(20) == timedelta(hours=4)


def test_permanent_error_fails_without_retry(
    session_factory: sessionmaker[Session], app_engine: Engine
) -> None:
    _enqueue(session_factory, "test.permanent")
    assert run_one(session_factory, "w1")
    assert _job(app_engine)["status"] == "failed"


def test_unknown_job_type_fails(session_factory: sessionmaker[Session], app_engine: Engine) -> None:
    _enqueue(session_factory, "test.no_such_handler")
    assert run_one(session_factory, "w1")
    job = _job(app_engine)
    assert job["status"] == "failed"
    assert "no handler" in job["last_error"]


def test_successful_job(session_factory: sessionmaker[Session], app_engine: Engine) -> None:
    calls.clear()
    _enqueue(session_factory, "test.succeeds", payload={"n": 1})
    assert run_one(session_factory, "w1")
    assert _job(app_engine)["status"] == "succeeded"
    assert calls == [{"n": 1}]


def test_dedupe_key_prevents_duplicates(session_factory: sessionmaker[Session], app_engine: Engine) -> None:
    for _ in range(3):
        _enqueue(session_factory, "test.succeeds", dedupe_key="same-key")
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1


def test_dedupe_key_reusable_after_completion(
    session_factory: sessionmaker[Session], app_engine: Engine
) -> None:
    _enqueue(session_factory, "test.succeeds", dedupe_key="k")
    assert run_one(session_factory, "w1")
    _enqueue(session_factory, "test.succeeds", dedupe_key="k")
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 2


def test_stale_running_job_is_requeued(session_factory: sessionmaker[Session], app_engine: Engine) -> None:
    with clock.frozen(T0):
        _enqueue(session_factory, "test.succeeds")
        with unit_of_work(session_factory) as uow:
            assert queue.claim_next(uow.session, "crashed-worker") is not None
    with unit_of_work(session_factory) as uow:
        assert queue.requeue_stale(uow.session, now=T0 + timedelta(minutes=10)) == 0
    with unit_of_work(session_factory) as uow:
        assert queue.requeue_stale(uow.session, now=T0 + timedelta(minutes=16)) == 1
    assert _job(app_engine)["status"] == "queued"


def test_retry_dead_job(session_factory: sessionmaker[Session], app_engine: Engine) -> None:
    _enqueue(session_factory, "test.permanent")
    run_one(session_factory, "w1")
    with app_engine.connect() as conn:
        job_id = conn.execute(text("SELECT id FROM jobs")).scalar_one()
    with unit_of_work(session_factory) as uow:
        assert queue.retry_dead(uow.session, job_id)
    assert _job(app_engine)["status"] == "queued"


def test_concurrent_claims_lock_distinct_jobs(session_factory: sessionmaker[Session]) -> None:
    """SKIP LOCKED: two workers never claim the same job."""
    _enqueue(session_factory, "test.succeeds")
    _enqueue(session_factory, "test.succeeds")
    s1, s2 = session_factory(), session_factory()
    try:
        a = queue.claim_next(s1, "w1")
        b = queue.claim_next(s2, "w2")
        assert a is not None
        assert b is not None
        assert a.id != b.id
        assert queue.claim_next(session_factory(), "w3") is None
    finally:
        s1.rollback()
        s2.rollback()
        s1.close()
        s2.close()


def test_scheduler_enqueues_once_per_period(
    session_factory: sessionmaker[Session], app_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tcms.platform.jobs import worker

    monkeypatch.setattr(worker, "SCHEDULES", [Schedule("test.succeeds", timedelta(hours=1))])
    run_scheduler_tick(session_factory, now=T0)
    run_scheduler_tick(session_factory, now=T0 + timedelta(minutes=30))
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
    run_scheduler_tick(session_factory, now=T0 + timedelta(hours=1, minutes=1))
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 2
