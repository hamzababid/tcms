"""Read access to audit events: activity feed (FR-WS-007), record history (FR-AUD-002)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tcms.core.pagination import PageParams
from tcms.platform.models import AuditEvent


@dataclass(frozen=True)
class EventRow:
    id: UUID
    occurred_at: datetime
    project_id: UUID | None
    actor_type: str
    actor_id: UUID | None
    actor_display: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_key: str | None
    changes: dict[str, Any] | None
    summary: str | None


def _row(e: AuditEvent) -> EventRow:
    return EventRow(
        e.id,
        e.occurred_at,
        e.project_id,
        e.actor_type.value if hasattr(e.actor_type, "value") else str(e.actor_type),
        e.actor_id,
        e.actor_display,
        e.action,
        e.entity_type,
        e.entity_id,
        e.entity_key,
        e.changes,
        e.summary,
    )


def project_activity(
    s: Session,
    org_id: UUID,
    project_id: UUID,
    page: PageParams,
    *,
    entity_type: str | None = None,
    actor_id: UUID | None = None,
) -> tuple[list[EventRow], int]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == org_id, AuditEvent.project_id == project_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    # Sign-in noise and admin access markers are not part of the project feed.
    stmt = stmt.where(~AuditEvent.action.in_(("project.admin_accessed",)))
    total = int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = s.execute(
        stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return [_row(e) for e in rows], total


def entity_history(
    s: Session, org_id: UUID, entity_type: str, entity_id: UUID, page: PageParams
) -> tuple[list[EventRow], int]:
    stmt = select(AuditEvent).where(
        AuditEvent.organization_id == org_id,
        AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id == entity_id,
    )
    total = int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = s.execute(
        stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return [_row(e) for e in rows], total


def entity_projects(s: Session, org_id: UUID, entity_type: str, entity_id: UUID) -> set[UUID | None]:
    """Projects an entity's events belong to (None = organization-level)."""
    return set(
        s.execute(
            select(AuditEvent.project_id)
            .where(
                AuditEvent.organization_id == org_id,
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .distinct()
        ).scalars()
    )


def admin_access_recorded(s: Session, org_id: UUID, project_id: UUID, session_id: UUID) -> bool:
    return (
        s.execute(
            select(AuditEvent.id)
            .where(
                AuditEvent.organization_id == org_id,
                AuditEvent.entity_type == "project",
                AuditEvent.entity_id == project_id,
                AuditEvent.action == "project.admin_accessed",
                AuditEvent.context["session_id"].astext == str(session_id),
            )
            .limit(1)
        ).first()
        is not None
    )
