"""Data transfers: background export records and their files (docs/05 `data_transfers`, docs/06 §4.13).

M7 uses them for large report exports (D10): `generating` → `ready` (file in S3, kept 7 days) or `failed`;
a daily job marks expired files `expired` and deletes the objects. Imports arrive in M8.
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


def _view(t: DataTransfer) -> TransferView:
    return TransferView(
        t.id, t.organization_id, t.project_id, t.kind.value, t.entity, t.status.value, t.format,
        dict(t.options), dict(t.summary), list(t.errors), t.created_by, t.created_at, t.finished_at,
        t.expires_at, t.result_object_key,
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
    """Daily: ready exports past `expires_at` become `expired`; their objects are deleted (idempotent)."""
    del job
    now = clock.now()
    rows = uow.session.execute(
        select(DataTransfer).where(
            DataTransfer.kind == TransferKind.export,
            DataTransfer.status == TransferStatus.ready,
            DataTransfer.expires_at < now,
        )
    ).scalars()
    for t in rows:
        if _store is not None and t.result_object_key:
            _store.client.delete_object(Bucket=_store.bucket, Key=t.result_object_key)
        t.status = TransferStatus.expired


schedule("transfers.expire", period=timedelta(days=1), offset=timedelta(hours=5))
