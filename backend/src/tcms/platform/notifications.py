"""In-app notifications (docs/02 §2.7). M2 writes the rows; listing and the bell arrive in M7 (E16)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.uow import UnitOfWork
from tcms.platform.models import Notification


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
    for user_id in recipients:
        uow.session.add(
            Notification(
                id=ids.new_id(),
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
    return len(recipients)
