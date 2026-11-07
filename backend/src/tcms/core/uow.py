"""Unit of Work: one transaction per request or job (docs/04 §3.1).

The UoW collects audit records, domain events and job requests while a service runs and writes
them in the same transaction before commit (BR-26, ADR-005 outbox). `core` is the lowest layer, so
the writers for audit rows and jobs are installed by `tcms.platform.install()`; committing pending
audit or jobs without a writer is a programming error and raises.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tcms.core import clock, ids
from tcms.core.context import AccessContext, ActorType
from tcms.core.events import DomainEvent, handlers_for


class Auditable(Protocol):
    __audit_type__: str
    id: UUID


@dataclass(frozen=True)
class AuditTarget:
    """Explicit audit target for things that are not ORM rows (e.g. a login attempt)."""

    entity_type: str
    entity_id: UUID | None = None
    entity_key: str | None = None
    project_id: UUID | None = None


@dataclass(frozen=True)
class AuditRecord:
    id: UUID
    occurred_at: datetime
    organization_id: UUID
    project_id: UUID | None
    actor_type: ActorType
    actor_id: UUID | None
    actor_display: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_key: str | None
    changes: dict[str, Any] | None
    context: dict[str, Any]
    summary: str | None


@dataclass(frozen=True)
class JobRequest:
    type: str
    payload: dict[str, Any]
    organization_id: UUID | None = None
    run_at: datetime | None = None
    dedupe_key: str | None = None
    max_attempts: int = 5


AuditWriter = Callable[[Session, list[AuditRecord]], None]
JobWriter = Callable[[Session, list[JobRequest]], None]

_audit_writer: AuditWriter | None = None
_job_writer: JobWriter | None = None


def install_writers(*, audit: AuditWriter, jobs: JobWriter) -> None:
    global _audit_writer, _job_writer
    _audit_writer, _job_writer = audit, jobs


class ReadOnlyViolation(RuntimeError):
    pass


@dataclass
class UnitOfWork:
    session: Session
    read_only: bool = False
    _audit: list[AuditRecord] = field(default_factory=list)
    _events: list[DomainEvent] = field(default_factory=list)
    _jobs: list[JobRequest] = field(default_factory=list)
    _after_commit: list[Callable[[], None]] = field(default_factory=list)
    bulk_operation_id: UUID | None = None

    # -- audit -------------------------------------------------------------------------------------
    def audit(
        self,
        ctx: AccessContext,
        action: str,
        entity: Auditable | AuditTarget,
        *,
        changes: dict[str, Any] | None = None,
        summary: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._guard_writable()
        if isinstance(entity, AuditTarget):
            entity_type, entity_id, entity_key = entity.entity_type, entity.entity_id, entity.entity_key
            project_id = entity.project_id if entity.project_id is not None else ctx.project_id
        else:
            entity_type = entity.__audit_type__
            entity_id = entity.id
            entity_key = getattr(entity, "key", None) or getattr(entity, "name", None)
            project_id = getattr(entity, "project_id", None) or ctx.project_id
        context: dict[str, Any] = {"request_id": ctx.request_id}
        if ctx.ip:
            context["ip"] = ctx.ip
        if ctx.user_agent:
            context["user_agent"] = ctx.user_agent
        if self.bulk_operation_id:
            context["bulk_operation_id"] = str(self.bulk_operation_id)
        if extra:
            context.update(extra)
        p = ctx.principal
        self._audit.append(
            AuditRecord(
                id=ids.new_id(),
                occurred_at=clock.now(),
                organization_id=p.organization_id,
                project_id=project_id,
                actor_type=p.actor_type if p.token_id is None else ActorType.api_token,
                actor_id=p.token_id or p.user_id,
                actor_display=p.display_name,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_key=entity_key,
                changes=changes,
                context=context,
                summary=summary,
            )
        )

    # -- events and jobs ---------------------------------------------------------------------------
    def emit(self, event: DomainEvent) -> None:
        self._guard_writable()
        self._events.append(event)

    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        organization_id: UUID | None = None,
        run_at: datetime | None = None,
        dedupe_key: str | None = None,
        max_attempts: int = 5,
    ) -> None:
        self._guard_writable()
        self._jobs.append(JobRequest(job_type, payload, organization_id, run_at, dedupe_key, max_attempts))

    def after_commit(self, fn: Callable[[], None]) -> None:
        self._after_commit.append(fn)

    @contextmanager
    def savepoint(self) -> Iterator[None]:
        """All-or-nothing part of a transaction: on an exception the database changes **and** the audit
        records, events and jobs queued inside are dropped, then the exception propagates (M8 import
        commit, AC-IMP-03)."""
        marks = (len(self._audit), len(self._events), len(self._jobs))
        nested = self.session.begin_nested()
        try:
            yield
            self.session.flush()
            nested.commit()
        except BaseException:
            nested.rollback()
            del self._audit[marks[0] :]
            del self._events[marks[1] :]
            del self._jobs[marks[2] :]
            raise

    @property
    def pending_audit(self) -> list[AuditRecord]:
        return list(self._audit)

    # -- lifecycle ---------------------------------------------------------------------------------
    def dispatch_in_tx_events(self) -> None:
        while self._events:
            event = self._events.pop(0)
            for handler in handlers_for(event):
                handler(self, event)

    def flush_side_records(self) -> None:
        if self._audit:
            if _audit_writer is None:
                raise RuntimeError("audit writer not installed (call tcms.platform.install())")
            _audit_writer(self.session, self._audit)
            self._audit = []
        if self._jobs:
            if _job_writer is None:
                raise RuntimeError("job writer not installed (call tcms.platform.install())")
            _job_writer(self.session, self._jobs)
            self._jobs = []

    def _guard_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyViolation("write attempted in a read-only unit of work")


@contextmanager
def unit_of_work(factory: sessionmaker[Session], *, read_only: bool = False) -> Iterator[UnitOfWork]:
    session = factory()
    uow = UnitOfWork(session=session, read_only=read_only)
    try:
        if read_only:
            session.execute(text("SET TRANSACTION READ ONLY"))
        yield uow
        if not read_only:
            uow.dispatch_in_tx_events()
            uow.flush_side_records()
            session.commit()
        else:
            session.rollback()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
    for fn in uow._after_commit:
        try:
            fn()
        except Exception:  # after-commit hooks must never fail the request
            structlog.get_logger().exception("uow.after_commit_failed")
