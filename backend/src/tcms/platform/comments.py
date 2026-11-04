"""Comments on records with @mentions (docs/02 §9.1).

Mentions are written as `@[Display Name](user:<uuid>)` tokens (inserted by the UI's picker); only project
members are notified. Authors may edit or delete within 15 minutes; afterwards comments are immutable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.errors import Forbidden, NotFound, ValidationFailed
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.platform import notifications
from tcms.platform.models import Comment
from tcms.platform.records import RecordRef

EDIT_WINDOW = timedelta(minutes=15)
MAX_BODY = 10_000
MENTION_RE = re.compile(r"@\[([^\]\n]{1,100})\]\(user:([0-9a-fA-F-]{36})\)")


def mentioned_ids(body: str) -> set[UUID]:
    out: set[UUID] = set()
    for _, raw in MENTION_RE.findall(body):
        try:
            out.add(UUID(raw))
        except ValueError:
            continue
    return out


@dataclass(frozen=True)
class CommentRow:
    id: UUID
    entity_type: str
    entity_id: UUID
    body: str | None  # None when deleted
    mentions: list[UUID]
    created_by: UUID
    created_at: datetime
    edited_at: datetime | None
    deleted: bool
    editable_until: datetime


def _row(c: Comment) -> CommentRow:
    return CommentRow(
        c.id,
        c.entity_type,
        c.entity_id,
        None if c.deleted_at else c.body,
        list(c.mentions),
        c.created_by,
        c.created_at,
        c.edited_at,
        c.deleted_at is not None,
        c.created_at + EDIT_WINDOW,
    )


def list_comments(uow: UnitOfWork, ctx: AccessContext, record: RecordRef) -> list[CommentRow]:
    ctx.require("project.view")
    rows = uow.session.execute(
        select(Comment)
        .where(
            Comment.organization_id == ctx.principal.organization_id,
            Comment.project_id == record.project_id,
            Comment.entity_type == record.entity_type,
            Comment.entity_id == record.entity_id,
        )
        .order_by(Comment.created_at)
    ).scalars()
    return [_row(c) for c in rows]


def add_comment(
    uow: UnitOfWork,
    ctx: AccessContext,
    record: RecordRef,
    body: str,
    *,
    members: set[UUID],
    require: bool = True,
) -> CommentRow:
    """`members`: user IDs of the project (mention recipients are limited to them)."""
    if require:
        ctx.require("comment.create")
    body = body.strip()
    if not 1 <= len(body) <= MAX_BODY:
        raise ValidationFailed("Comments are 1–10,000 characters", code="validation_error")
    mentions = mentioned_ids(body) & members
    now = clock.now()
    comment = Comment(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=record.project_id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        body=body,
        mentions=sorted(mentions, key=str),
        created_at=now,
        created_by=ctx.principal.user_id,
    )
    uow.session.add(comment)
    uow.session.flush()
    uow.audit(
        ctx,
        "comment.created",
        AuditTarget("comment", comment.id, record.label, project_id=record.project_id),
        extra={"on": f"{record.entity_type}:{record.entity_id}"},
        summary=f"{ctx.principal.display_name} commented on {record.label}",
    )
    if mentions:
        notifications.notify(
            uow,
            organization_id=ctx.principal.organization_id,
            user_ids=mentions,
            type="comment.mentioned",
            project_id=record.project_id,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            payload={"comment_id": str(comment.id), "label": record.label, "by": ctx.principal.display_name},
            exclude=ctx.principal.user_id,
        )
    return _row(comment)


def _own_editable(uow: UnitOfWork, ctx: AccessContext, comment_id: UUID) -> Comment:
    comment = uow.session.execute(
        select(Comment)
        .where(Comment.organization_id == ctx.principal.organization_id, Comment.id == comment_id)
        .with_for_update()
    ).scalar_one_or_none()
    if comment is None or comment.deleted_at is not None:
        raise NotFound()
    if comment.created_by != ctx.principal.user_id:
        raise Forbidden("Only the author can change a comment", code="not_author")
    if clock.now() > comment.created_at + EDIT_WINDOW:
        raise Forbidden("Comments can be changed for 15 minutes", code="edit_window_closed")
    return comment


def edit_comment(
    uow: UnitOfWork, ctx: AccessContext, comment_id: UUID, body: str, *, members: set[UUID]
) -> CommentRow:
    comment = _own_editable(uow, ctx, comment_id)
    body = body.strip()
    if not 1 <= len(body) <= MAX_BODY:
        raise ValidationFailed("Comments are 1–10,000 characters")
    old = comment.body
    comment.body = body
    comment.mentions = sorted(mentioned_ids(body) & members, key=str)
    comment.edited_at = clock.now()
    uow.audit(
        ctx,
        "comment.edited",
        AuditTarget("comment", comment.id, project_id=comment.project_id),
        changes={"body": [old, body]},
    )
    return _row(comment)


def delete_comment(uow: UnitOfWork, ctx: AccessContext, comment_id: UUID) -> None:
    comment = _own_editable(uow, ctx, comment_id)
    comment.deleted_at = clock.now()
    uow.audit(
        ctx,
        "comment.deleted",
        AuditTarget("comment", comment.id, project_id=comment.project_id),
        changes={"body": [comment.body, None]},
    )


def comment_project(uow: UnitOfWork, org_id: UUID, comment_id: UUID) -> UUID | None:
    return uow.session.execute(
        select(Comment.project_id).where(Comment.organization_id == org_id, Comment.id == comment_id)
    ).scalar_one_or_none()


def owner_of(s: Session, comment_id: UUID) -> tuple[UUID, UUID] | None:
    """(organization_id, project_id) of a comment, for request-context resolution."""
    row = s.execute(
        select(Comment.organization_id, Comment.project_id).where(Comment.id == comment_id)
    ).first()
    return (row[0], row[1]) if row else None
