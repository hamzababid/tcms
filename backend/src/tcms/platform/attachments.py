"""Attachments: upload, link, unlink, copy, GC (docs/02 §9.2, docs/03 §11, docs/04 §10.2, BR-28).

The owning module resolves the record (`RecordRef`): its project, the permission needed to attach, and
whether it is immutable (BR-28). Objects are streamed to S3 under random keys; names are sanitized.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO, TYPE_CHECKING
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.errors import Conflict, Forbidden, NotFound
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.platform import storage
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule
from tcms.platform.models import Attachment, AttachmentLink
from tcms.platform.records import RecordRef

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

MAX_PER_RECORD = 50
INLINE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"})


@dataclass(frozen=True)
class Storage:
    client: S3Client
    bucket: str


@dataclass(frozen=True)
class AttachmentRow:
    id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by: UUID
    uploaded_at: datetime
    entity_type: str
    entity_id: UUID


class AttachmentLimit(Conflict):
    code, title = "attachment_limit", "A record can have at most 50 attachments"


class RecordImmutable(Conflict):
    code, title = "immutable_record", "Attachments on this record can no longer change"


def sanitize_file_name(name: str) -> str:
    """Keep a readable, safe name: no paths, control characters or reserved characters."""
    name = unicodedata.normalize("NFC", name).replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]", "_", name).strip(" .")
    return (name or "file")[:255]


def _row(a: Attachment, link: AttachmentLink) -> AttachmentRow:
    return AttachmentRow(
        a.id,
        a.file_name,
        a.content_type,
        a.size_bytes,
        a.uploaded_by,
        a.uploaded_at,
        link.entity_type,
        link.entity_id,
    )


def _count(uow: UnitOfWork, record: RecordRef) -> int:
    return int(
        uow.session.execute(
            select(func.count())
            .select_from(AttachmentLink)
            .join(Attachment, Attachment.id == AttachmentLink.attachment_id)
            .where(
                AttachmentLink.entity_type == record.entity_type,
                AttachmentLink.entity_id == record.entity_id,
                Attachment.deleted_at.is_(None),
            )
        ).scalar_one()
    )


def upload(
    uow: UnitOfWork,
    ctx: AccessContext,
    record: RecordRef,
    stream: IO[bytes],
    file_name: str,
    *,
    max_bytes: int,
    store: Storage,
) -> AttachmentRow:
    ctx.require(record.write_permission)
    if record.immutable:
        raise RecordImmutable()
    if _count(uow, record) >= MAX_PER_RECORD:
        raise AttachmentLimit()
    key = storage.object_key_for(ctx.principal.organization_id)
    stored = storage.store(store.client, store.bucket, key, stream, max_bytes=max_bytes)
    now = clock.now()
    att = Attachment(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=record.project_id,
        object_key=key,
        file_name=sanitize_file_name(file_name),
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        uploaded_by=ctx.principal.user_id,
        uploaded_at=now,
    )
    link = AttachmentLink(
        id=ids.new_id(),
        attachment_id=att.id,
        organization_id=att.organization_id,
        project_id=record.project_id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        created_at=now,
        created_by=ctx.principal.user_id,
    )
    uow.session.add_all([att, link])
    uow.session.flush()
    uow.audit(
        ctx,
        "attachment.uploaded",
        AuditTarget("attachment", att.id, record.label, project_id=record.project_id),
        changes={"file_name": [None, att.file_name], "size_bytes": [None, att.size_bytes]},
        extra={"on": f"{record.entity_type}:{record.entity_id}"},
        summary=f"{ctx.principal.display_name} attached {att.file_name} to {record.label}",
    )
    return _row(att, link)


def list_for(
    uow: UnitOfWork, org_id: UUID, entity_type: str, entity_ids: Iterable[UUID]
) -> dict[UUID, list[AttachmentRow]]:
    ids_ = list(entity_ids)
    out: dict[UUID, list[AttachmentRow]] = {i: [] for i in ids_}
    if not ids_:
        return out
    rows = uow.session.execute(
        select(Attachment, AttachmentLink)
        .join(AttachmentLink, AttachmentLink.attachment_id == Attachment.id)
        .where(
            AttachmentLink.organization_id == org_id,
            AttachmentLink.entity_type == entity_type,
            AttachmentLink.entity_id.in_(ids_),
            Attachment.deleted_at.is_(None),
        )
        .order_by(Attachment.uploaded_at)
    ).all()
    for att, link in rows:
        out[link.entity_id].append(_row(att, link))
    return out


def get(uow: UnitOfWork, org_id: UUID, attachment_id: UUID) -> Attachment | None:
    att = uow.session.execute(
        select(Attachment).where(Attachment.organization_id == org_id, Attachment.id == attachment_id)
    ).scalar_one_or_none()
    return att if att is not None and att.deleted_at is None else None


def project_of(uow: UnitOfWork, org_id: UUID, attachment_id: UUID) -> UUID | None:
    att = get(uow, org_id, attachment_id)
    return att.project_id if att else None


def unlink(uow: UnitOfWork, ctx: AccessContext, attachment_id: UUID, record: RecordRef) -> None:
    """Uploader or holder of the record's write permission (docs/02 §9.2), unless BR-28 forbids."""
    att = get(uow, ctx.principal.organization_id, attachment_id)
    link = uow.session.execute(
        select(AttachmentLink).where(
            AttachmentLink.attachment_id == attachment_id,
            AttachmentLink.entity_type == record.entity_type,
            AttachmentLink.entity_id == record.entity_id,
        )
    ).scalar_one_or_none()
    if att is None or link is None:
        raise NotFound()
    if att.uploaded_by != ctx.principal.user_id and not ctx.has(record.write_permission):
        raise Forbidden(f"Requires permission {record.write_permission}", code="permission_denied")
    if record.immutable:
        raise RecordImmutable()
    uow.session.delete(link)
    uow.session.flush()
    remaining = uow.session.execute(
        select(func.count()).select_from(AttachmentLink).where(AttachmentLink.attachment_id == attachment_id)
    ).scalar_one()
    if remaining == 0:
        att.deleted_at = clock.now()  # object removed by attachments.gc
    uow.audit(
        ctx,
        "attachment.deleted",
        AuditTarget("attachment", att.id, record.label, project_id=record.project_id),
        changes={"file_name": [att.file_name, None]},
        extra={"on": f"{record.entity_type}:{record.entity_id}"},
        summary=f"{ctx.principal.display_name} removed {att.file_name} from {record.label}",
    )


def relink(uow: UnitOfWork, ctx: AccessContext, attachment_ids: Iterable[UUID], target: RecordRef) -> int:
    """Link existing attachments to another record (step attachments carried forward, docs/04 §4.2)."""
    now = clock.now()
    n = 0
    for aid in attachment_ids:
        uow.session.add(
            AttachmentLink(
                id=ids.new_id(),
                attachment_id=aid,
                organization_id=ctx.principal.organization_id,
                project_id=target.project_id,
                entity_type=target.entity_type,
                entity_id=target.entity_id,
                created_at=now,
                created_by=ctx.principal.user_id,
            )
        )
        n += 1
    return n


def copy_to(
    uow: UnitOfWork, ctx: AccessContext, rows: Iterable[AttachmentRow], target: RecordRef, store: Storage
) -> int:
    """Duplicate a case: attachments become new objects (docs/02 §5.5)."""
    now = clock.now()
    n = 0
    for r in rows:
        src = get(uow, ctx.principal.organization_id, r.id)
        if src is None:
            continue
        key = storage.object_key_for(ctx.principal.organization_id)
        store.client.copy_object(
            Bucket=store.bucket, Key=key, CopySource={"Bucket": store.bucket, "Key": src.object_key}
        )
        att = Attachment(
            id=ids.new_id(),
            organization_id=src.organization_id,
            project_id=target.project_id,
            object_key=key,
            file_name=src.file_name,
            content_type=src.content_type,
            size_bytes=src.size_bytes,
            sha256=src.sha256,
            uploaded_by=ctx.principal.user_id,
            uploaded_at=now,
        )
        uow.session.add(att)
        uow.session.add(
            AttachmentLink(
                id=ids.new_id(),
                attachment_id=att.id,
                organization_id=att.organization_id,
                project_id=target.project_id,
                entity_type=target.entity_type,
                entity_id=target.entity_id,
                created_at=now,
                created_by=ctx.principal.user_id,
            )
        )
        n += 1
    return n


def remove_links_of(uow: UnitOfWork, org_id: UUID, entity_type: str, entity_ids: Iterable[UUID]) -> None:
    """Hard delete of the owning record (BR-14): links go; orphaned attachments are soft-deleted for GC."""
    ids_ = list(entity_ids)
    if not ids_:
        return
    attachment_ids = set(
        uow.session.execute(
            select(AttachmentLink.attachment_id).where(
                AttachmentLink.organization_id == org_id,
                AttachmentLink.entity_type == entity_type,
                AttachmentLink.entity_id.in_(ids_),
            )
        ).scalars()
    )
    uow.session.execute(
        delete(AttachmentLink).where(
            AttachmentLink.entity_type == entity_type, AttachmentLink.entity_id.in_(ids_)
        )
    )
    if attachment_ids:
        still_linked = set(
            uow.session.execute(
                select(AttachmentLink.attachment_id).where(AttachmentLink.attachment_id.in_(attachment_ids))
            ).scalars()
        )
        now = clock.now()
        for att in uow.session.execute(
            select(Attachment).where(Attachment.id.in_(attachment_ids - still_linked))
        ).scalars():
            att.deleted_at = now


def open_object(store: Storage, uow: UnitOfWork, attachment_id: UUID) -> tuple[object, str]:
    att = uow.session.get(Attachment, attachment_id)
    if att is None or att.deleted_at is not None:
        raise NotFound()
    obj = store.client.get_object(Bucket=store.bucket, Key=att.object_key)
    return obj["Body"], ("inline" if att.content_type in INLINE_TYPES else "attachment")


_gc_store: Storage | None = None


def configure_gc(store: Storage) -> None:
    global _gc_store
    _gc_store = store


@job_handler("attachments.gc")
def gc(job: JobInfo, uow: UnitOfWork) -> None:
    """docs/03 §10: delete objects of deleted attachments; orphan uploads older than 24 h become deleted."""
    now = clock.now()
    orphans = uow.session.execute(
        select(Attachment).where(
            Attachment.deleted_at.is_(None),
            Attachment.uploaded_at < now - timedelta(hours=24),
            ~select(AttachmentLink.id).where(AttachmentLink.attachment_id == Attachment.id).exists(),
        )
    ).scalars()
    for att in orphans:
        att.deleted_at = now
    if _gc_store is None:
        return
    # Objects deleted within the last week (daily job; delete_object is idempotent, so overlap is harmless).
    recent = select(Attachment).where(
        Attachment.deleted_at.is_not(None), Attachment.deleted_at > now - timedelta(days=7)
    )
    for att in uow.session.execute(recent).scalars():
        _gc_store.client.delete_object(Bucket=_gc_store.bucket, Key=att.object_key)  # idempotent


schedule("attachments.gc", period=timedelta(days=1), offset=timedelta(hours=4))


def owner_of(s: Session, attachment_id: UUID) -> tuple[UUID, UUID] | None:
    """(organization_id, project_id) of a live attachment, for request-context resolution."""
    row = s.execute(
        select(Attachment.organization_id, Attachment.project_id).where(
            Attachment.id == attachment_id, Attachment.deleted_at.is_(None)
        )
    ).first()
    return (row[0], row[1]) if row else None


def metadata(uow: UnitOfWork, org_id: UUID, attachment_id: UUID) -> AttachmentRow | None:
    """A live attachment with its first link (the record it was uploaded to)."""
    row = uow.session.execute(
        select(Attachment, AttachmentLink)
        .join(AttachmentLink, AttachmentLink.attachment_id == Attachment.id)
        .where(
            Attachment.organization_id == org_id,
            Attachment.id == attachment_id,
            Attachment.deleted_at.is_(None),
        )
        .order_by(AttachmentLink.created_at)
        .limit(1)
    ).first()
    return _row(row[0], row[1]) if row else None


def content_disposition(kind: str, file_name: str) -> str:
    """RFC 6266 header with an ASCII fallback and the UTF-8 name."""
    ascii_name = file_name.encode("ascii", "replace").decode().replace('"', "_").replace("?", "_")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name, safe='')}"
