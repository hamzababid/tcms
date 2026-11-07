"""In-app notifications (docs/02 §2.7, docs/04 §10.4; M7 D11–D13).

Modules call `notify` in their own transaction. Types sent by email right away (mentions) also enqueue
`notifications.email`, handled by `tcms.notifications` (which knows users, preferences and project keys).
The bell lists, counts and marks rows here; old rows are purged after 180 days (docs/05 §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update

from tcms.core import clock, ids
from tcms.core.uow import UnitOfWork
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule
from tcms.platform.models import Notification

# docs/02 §2.7: "Mentioned in a comment — in-app + email (opt-out)". Assignments go in the daily digest.
EMAIL_NOW = frozenset({"comment.mentioned"})
RETENTION_DAYS = 180


def notify(
    uow: UnitOfWork,
    *,
    organization_id: UUID,
    user_ids: set[UUID],
    type: str,
    project_id: UUID | None,
    entity_type: str | None,
    entity_id: UUID | None,
    payload: dict[str, Any],
    exclude: UUID | None = None,
) -> int:
    """Create one notification per recipient (the actor is never notified about their own action)."""
    now = clock.now()
    recipients = sorted(user_ids - ({exclude} if exclude else set()), key=str)
    created: list[UUID] = []
    for user_id in recipients:
        nid = ids.new_id()
        created.append(nid)
        uow.session.add(
            Notification(
                id=nid,
                organization_id=organization_id,
                user_id=user_id,
                project_id=project_id,
                type=type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
                created_at=now,
            )
        )
    if created and type in EMAIL_NOW:
        uow.enqueue_job(
            "notifications.email",
            {"ids": [str(i) for i in created]},
            organization_id=organization_id,
            dedupe_key=f"notifications.email:{created[0]}",
        )
    return len(recipients)


@dataclass(frozen=True)
class NotificationView:
    id: UUID
    organization_id: UUID
    user_id: UUID
    project_id: UUID | None
    type: str
    entity_type: str | None
    entity_id: UUID | None
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


def _view(n: Notification) -> NotificationView:
    return NotificationView(
        n.id, n.organization_id, n.user_id, n.project_id, n.type, n.entity_type, n.entity_id,
        dict(n.payload or {}), n.created_at, n.read_at,
    )  # fmt: skip


def list_for(
    uow: UnitOfWork, org_id: UUID, user_id: UUID, *, unread: bool, limit: int, offset: int
) -> tuple[list[NotificationView], int]:
    """Newest first (ix_notifications__user_unread)."""
    cond = [Notification.organization_id == org_id, Notification.user_id == user_id]
    if unread:
        cond.append(Notification.read_at.is_(None))
    total = int(uow.session.execute(select(func.count()).select_from(Notification).where(*cond)).scalar_one())
    rows = uow.session.execute(
        select(Notification)
        .where(*cond)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return [_view(n) for n in rows], total


def unread_count(uow: UnitOfWork, org_id: UUID, user_id: UUID) -> int:
    return int(
        uow.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.organization_id == org_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        ).scalar_one()
    )


def mark_read(uow: UnitOfWork, org_id: UUID, user_id: UUID, *, notification_ids: list[UUID] | None) -> int:
    """Own notifications only; `None` = all. Already-read rows keep their first read time."""
    cond = [
        Notification.organization_id == org_id,
        Notification.user_id == user_id,
        Notification.read_at.is_(None),
    ]
    if notification_ids is not None:
        if not notification_ids:
            return 0
        cond.append(Notification.id.in_(notification_ids))
    result = uow.session.execute(update(Notification).where(*cond).values(read_at=clock.now()))
    return int(getattr(result, "rowcount", 0) or 0)


def by_ids(uow: UnitOfWork, notification_ids: list[UUID]) -> list[NotificationView]:
    rows = uow.session.execute(select(Notification).where(Notification.id.in_(notification_ids))).scalars()
    return [_view(n) for n in rows]


def of_type_since(uow: UnitOfWork, user_id: UUID, type_: str, since: datetime) -> list[NotificationView]:
    rows = uow.session.execute(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.type == type_, Notification.created_at > since)
        .order_by(Notification.created_at)
    ).scalars()
    return [_view(n) for n in rows]


@job_handler("notifications.cleanup")
def cleanup(job: JobInfo, uow: UnitOfWork) -> None:
    """docs/05 §9: notifications are kept 180 days."""
    del job
    cutoff = clock.now() - timedelta(days=RETENTION_DAYS)
    uow.session.execute(delete(Notification).where(Notification.created_at < cutoff))


schedule("notifications.cleanup", period=timedelta(days=1), offset=timedelta(hours=3, minutes=30))
