"""Platform tables (docs/05 §3.8). Private to the platform module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, created_ts, pk
from tcms.core.db import Base
from tcms.core.enums import ActorTypeEnum, JobStatus, T, TransferKind, TransferStatus, ViewVisibility


def _project_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
    )


class Comment(Base):
    __tablename__ = "comments"
    __audit_type__ = "comment"
    __table_args__ = (_project_fk(), Index("ix_comments__entity", "entity_type", "entity_id", "created_at"))

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[list[UUID]] = mapped_column(ARRAY(UUIDT), nullable=False, server_default="{}")
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(TS)
    deleted_at: Mapped[datetime | None] = mapped_column(TS)


class Attachment(Base):
    __tablename__ = "attachments"
    __audit_type__ = "attachment"
    __table_args__ = (_project_fk(), Index("ux_attachments__object_key", "object_key", unique=True))

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    uploaded_at: Mapped[datetime] = created_ts()
    deleted_at: Mapped[datetime | None] = mapped_column(TS)


class AttachmentLink(Base):
    __tablename__ = "attachment_links"
    __table_args__ = (
        Index("ux_attachment_links__target", "attachment_id", "entity_type", "entity_id", unique=True),
        Index("ix_attachment_links__entity", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = pk()
    attachment_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("attachments.id"), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("projects.id"))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[UUID | None] = mapped_column(UUIDT)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = created_ts()
    read_at: Mapped[datetime | None] = mapped_column(TS)


class SavedView(StdColumns, Base):
    __tablename__ = "saved_views"
    __audit_type__ = "saved_view"
    __table_args__ = (_project_fk(),)  # ux_saved_views__owner_name: expression index (lower(name))

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[ViewVisibility] = mapped_column(
        T("view_visibility"), nullable=False, server_default="private"
    )
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class AuditEvent(Base):
    """Append-only (BR-26): trigger blocks UPDATE/DELETE; the app role has INSERT/SELECT only."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events__action", "action"),  # DESC indexes are declared below the class
    )

    id: Mapped[UUID] = pk()
    occurred_at: Mapped[datetime] = created_ts()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(UUIDT)
    actor_type: Mapped[ActorTypeEnum] = mapped_column(T("actor_type"), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(UUIDT)
    actor_display: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(UUIDT)
    entity_key: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    summary: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    hash: Mapped[bytes | None] = mapped_column(LargeBinary)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs__queue", "run_at", postgresql_where=text("status = 'queued'")),
        Index("ix_jobs__running_locked", "locked_at", postgresql_where=text("status = 'running'")),
        Index(
            "ux_jobs__dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND status IN ('queued','running')"),
        ),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID | None] = mapped_column(UUIDT)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[JobStatus] = mapped_column(T("job_status"), nullable=False, server_default="queued")
    run_at: Mapped[datetime] = created_ts()
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(TS)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_ts()
    finished_at: Mapped[datetime | None] = mapped_column(TS)


class DataTransfer(Base):
    __tablename__ = "data_transfers"
    __audit_type__ = "data_transfer"
    __table_args__ = (_project_fk(),)

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    kind: Mapped[TransferKind] = mapped_column(T("transfer_kind"), nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TransferStatus] = mapped_column(T("transfer_status"), nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    source_object_key: Mapped[str | None] = mapped_column(Text)
    result_object_key: Mapped[str | None] = mapped_column(Text)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    errors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_by: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    created_at: Mapped[datetime] = created_ts()
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    expires_at: Mapped[datetime | None] = mapped_column(TS)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (Index("ix_idempotency_keys__created_at", "created_at"),)

    principal_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_ts()


# Indexes with DESC columns (declared after the classes so they can use column expressions).
Index(
    "ix_notifications__user_unread",
    Notification.user_id,
    Notification.read_at,
    Notification.created_at.desc(),
)
Index("ix_audit_events__org_occurred", AuditEvent.organization_id, AuditEvent.occurred_at.desc())
Index("ix_audit_events__project_occurred", AuditEvent.project_id, AuditEvent.occurred_at.desc())
Index("ix_audit_events__entity", AuditEvent.entity_type, AuditEvent.entity_id, AuditEvent.occurred_at.desc())
Index("ix_audit_events__actor", AuditEvent.actor_id, AuditEvent.occurred_at.desc())
Index("ix_data_transfers__project_created", DataTransfer.project_id, DataTransfer.created_at.desc())
