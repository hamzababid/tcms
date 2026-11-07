"""My notifications and email preferences (docs/06 §4.1, docs/02 §2.7; M7 D11, D13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from tcms.api.deps import Auth, get_read_uow, get_uow, user_context
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, ValidationFailed
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.identity import service as identity
from tcms.identity.service import Authenticated
from tcms.notifications import render
from tcms.notifications import schemas as s
from tcms.platform import notifications

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/me/notifications", response_model=s.NotificationPage)
def list_notifications(
    unread: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    auth: Authenticated = Auth,
    uow: UnitOfWork = Depends(get_read_uow),
) -> s.NotificationPage:
    """The bell (US-170): newest first, each with a rendered title and link."""
    rows, total = notifications.list_for(
        uow, auth.organization_id, auth.user_id, unread=unread, limit=page_size, offset=(page - 1) * page_size
    )
    lk = render.lookups(uow.session, rows)
    items = []
    for n in rows:
        r = render.render(n, lk)
        items.append(
            s.NotificationRead(
                id=n.id,
                type=n.type,
                title=r.title,
                url=r.url,
                project_key=r.project_key,
                created_at=n.created_at,
                read_at=n.read_at,
            )
        )
    return s.NotificationPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        unread=notifications.unread_count(uow, auth.organization_id, auth.user_id),
    )


@router.get("/me/notifications/unread-count", response_model=s.UnreadCount)
def unread_count(auth: Authenticated = Auth, uow: UnitOfWork = Depends(get_read_uow)) -> s.UnreadCount:
    """Polled by the bell every 60 s and on window focus."""
    return s.UnreadCount(count=notifications.unread_count(uow, auth.organization_id, auth.user_id))


@router.post("/me/notifications/read", response_model=s.MarkedRead)
def mark_read(
    body: s.MarkRead, auth: Authenticated = Auth, uow: UnitOfWork = Depends(get_uow)
) -> s.MarkedRead:
    """`{ids: [...]}` or `{all: true}`; only the caller's own notifications."""
    if body.all == (body.ids is not None):
        raise ValidationFailed(errors=[FieldError("ids", "field_required", "Give ids or all: true")])
    updated = notifications.mark_read(
        uow, auth.organization_id, auth.user_id, notification_ids=None if body.all else list(body.ids or [])
    )
    return s.MarkedRead(
        updated=updated, unread=notifications.unread_count(uow, auth.organization_id, auth.user_id)
    )


@router.get("/me/notification-preferences", response_model=s.EmailPreferences)
def get_preferences(
    auth: Authenticated = Auth, uow: UnitOfWork = Depends(get_read_uow)
) -> s.EmailPreferences:
    me = identity_queries.recipients(uow.session, {auth.user_id})[auth.user_id]
    return s.EmailPreferences(mentions=me.email_mentions, digest=me.email_digest)


@router.patch("/me/notification-preferences", response_model=s.EmailPreferences)
def patch_preferences(
    body: s.EmailPreferencesPatch,
    ctx: AccessContext = Depends(user_context),
    uow: UnitOfWork = Depends(get_uow),
) -> s.EmailPreferences:
    """US-171: opt out of mention emails and the daily digest (in-app notifications stay)."""
    out = identity.set_email_preferences(uow, ctx, mentions=body.mentions, digest=body.digest)
    return s.EmailPreferences(**out)
