"""Data transfers: background export and import records and their files (docs/05 `data_transfers`,
docs/06 §4.13).

Exports (M7 D10): `generating` → `ready` (file in S3, kept 7 days) or `failed`.
Imports (M8 D4): `uploaded` → `validating` → `validated` → `committing` → `committed` (report file) or
`failed`. A daily job marks files older than 7 days `expired` and deletes the objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.enums import TransferKind, TransferStatus
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.platform.attachments import Storage
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule
from tcms.platform.models import DataTransfer

KEEP_DAYS = 7


@dataclass(frozen=True)
class TransferView:
    id: UUID
    organization_id: UUID
    project_id: UUID
    kind: str
    entity: str
    status: str
    format: str
    options: dict[str, Any]
    summary: dict[str, Any]
    errors: list[Any]
    created_by: UUID
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    result_object_key: str | None
    source_object_key: str | None


def _view(t: DataTransfer) -> TransferView:
    return TransferView(
        t.id, t.organization_id, t.project_id, t.kind.value, t.entity, t.status.value, t.format,
        dict(t.options), dict(t.summary), list(t.errors), t.created_by, t.created_at, t.finished_at,
        t.expires_at, t.result_object_key, t.source_object_key,
    )  # fmt: skip


def create_export(
    uow: UnitOfWork, ctx: AccessContext, *, entity: str, format: str, options: dict[str, Any]
) -> TransferView:
    assert ctx.principal.user_id is not None
    t = DataTransfer(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        kind=TransferKind.export,
        entity=entity,
        status=TransferStatus.generating,
        format=format,
        options=options,
        created_by=ctx.principal.user_id,
        created_at=clock.now(),
    )
    uow.session.add(t)
    uow.session.flush()
    return _view(t)


def create_import(
    uow: UnitOfWork, ctx: AccessContext, *, entity: str, format: str, source_key: str, options: dict[str, Any]
) -> TransferView:
    assert ctx.principal.user_id is not None
    t = DataTransfer(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        kind=TransferKind.import_,
        entity=entity,
        status=TransferStatus.uploaded,
        format=format,
        source_object_key=source_key,
        options=options,
        created_by=ctx.principal.user_id,
        created_at=clock.now(),
        expires_at=clock.now() + timedelta(days=KEEP_DAYS),
    )
    uow.session.add(t)
    uow.session.flush()
    return _view(t)


def update(
    uow: UnitOfWork,
    transfer_id: UUID,
    *,
    status: TransferStatus,
    options: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    errors: list[Any] | None = None,
    result_key: str | None = None,
    finished: bool = False,
) -> TransferView:
    t = uow.session.get(DataTransfer, transfer_id, with_for_update=True)
    assert t is not None
    t.status = status
    if options is not None:
        t.options = options
    if summary is not None:
        t.summary = summary
    if errors is not None:
        t.errors = errors
    if result_key is not None:
        t.result_object_key = result_key
    if finished:
        t.finished_at = clock.now()
    return _view(t)


def get(s: Session, org_id: UUID, transfer_id: UUID) -> TransferView | None:
    t = s.execute(
        select(DataTransfer).where(DataTransfer.organization_id == org_id, DataTransfer.id == transfer_id)
    ).scalar_one_or_none()
    return _view(t) if t else None


def owner_of(s: Session, transfer_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(DataTransfer.organization_id, DataTransfer.project_id).where(DataTransfer.id == transfer_id)
    ).first()
    return (row[0], row[1]) if row else None


def finish(
    uow: UnitOfWork,
    transfer_id: UUID,
    *,
    object_key: str | None,
    summary: dict[str, Any],
    error: str | None = None,
) -> TransferView:
    t = uow.session.get(DataTransfer, transfer_id)
    assert t is not None
    now = clock.now()
    t.finished_at = now
    t.summary = summary
    if error is None:
        t.status = TransferStatus.ready
        t.result_object_key = object_key
        t.expires_at = now + timedelta(days=KEEP_DAYS)
    else:
        t.status = TransferStatus.failed
        t.errors = [{"code": "export_failed", "detail": error}]
    return _view(t)


def audit_export(
    uow: UnitOfWork, ctx: AccessContext, *, entity: str, rows: int, format: str, transfer_id: UUID | None
) -> None:
    uow.audit(
        ctx,
        "export.created",
        AuditTarget("data_transfer" if transfer_id else "report", transfer_id, entity, ctx.project_id),
        summary=f"{ctx.principal.display_name} exported {entity} ({rows} rows, {format.upper()})",
        extra={"rows": rows, "format": format},
    )


_store: Storage | None = None


def configure(store: Storage) -> None:
    global _store
    _store = store


def store() -> Storage:
    if _store is None:
        raise RuntimeError("transfer storage is not configured")
    return _store


@job_handler("transfers.expire")
def expire(job: JobInfo, uow: UnitOfWork) -> None:
    """Daily: transfers past `expires_at` (ready exports; finished, failed or abandoned imports) become
    `expired`; their objects are deleted (idempotent)."""
    del job
    now = clock.now()
    done = (
        TransferStatus.ready, TransferStatus.committed, TransferStatus.failed,
        TransferStatus.uploaded, TransferStatus.validated,
    )  # fmt: skip
    rows = uow.session.execute(
        select(DataTransfer).where(DataTransfer.status.in_(done), DataTransfer.expires_at < now)
    ).scalars()
    for t in rows:
        if _store is not None:
            for key in (t.result_object_key, t.source_object_key):
                if key:
                    _store.client.delete_object(Bucket=_store.bucket, Key=key)
        t.status = TransferStatus.expired


schedule("transfers.expire", period=timedelta(days=1), offset=timedelta(hours=5))
