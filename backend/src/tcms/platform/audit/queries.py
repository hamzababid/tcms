"""Read access to audit events: activity feed (FR-WS-007), record history (FR-AUD-002)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
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
    context: dict[str, Any] = field(default_factory=dict)  # request id, ip, user agent, extra


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
        dict(e.context or {}),
    )


@dataclass(frozen=True)
class AuditFilter:
    """Audit list filters (docs/06 §4.12: actor_id, action, entity_type, occurred_at__gte/lte; q)."""

    entity_type: str | None = None
    actor_id: UUID | None = None
    action: str | None = None
    occurred_from: date | None = None
    occurred_to: date | None = None
    q: str | None = None
    project_id: UUID | None = None  # organization audit log only


def _filtered(stmt: Select[AuditEvent], f: AuditFilter) -> Select[AuditEvent]:
    if f.entity_type:
        stmt = stmt.where(AuditEvent.entity_type == f.entity_type)
    if f.actor_id:
        stmt = stmt.where(AuditEvent.actor_id == f.actor_id)
    if f.action:
        stmt = stmt.where(AuditEvent.action == f.action)
    if f.project_id:
        stmt = stmt.where(AuditEvent.project_id == f.project_id)
    if f.occurred_from:
        stmt = stmt.where(AuditEvent.occurred_at >= datetime.combine(f.occurred_from, time.min, tzinfo=UTC))
    if f.occurred_to:
        end = datetime.combine(f.occurred_to + timedelta(days=1), time.min, tzinfo=UTC)
        stmt = stmt.where(AuditEvent.occurred_at < end)
    if f.q and f.q.strip():
        needle = f.q.strip()
        stmt = stmt.where(
            or_(
                AuditEvent.summary.icontains(needle, autoescape=True),
                AuditEvent.entity_key.icontains(needle, autoescape=True),
                AuditEvent.actor_display.icontains(needle, autoescape=True),
            )
        )
    return stmt


def project_activity(
    s: Session,
    org_id: UUID,
    project_id: UUID,
    page: PageParams,
    *,
    filters: AuditFilter = AuditFilter(),
) -> tuple[list[EventRow], int]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == org_id, AuditEvent.project_id == project_id)
    stmt = _filtered(stmt, filters)
    # Sign-in noise and admin access markers are not part of the project feed.
    stmt = stmt.where(~AuditEvent.action.in_(("project.admin_accessed",)))
    total = int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = s.execute(
        stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return [_row(e) for e in rows], total


def _paged(s: Session, stmt: Select[AuditEvent], page: PageParams) -> tuple[list[EventRow], int]:
    total = int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = s.execute(
        stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return [_row(e) for e in rows], total


def _scope(org_id: UUID, project_id: UUID | None) -> Select[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == org_id)
    return stmt.where(AuditEvent.project_id == project_id) if project_id else stmt


def events(
    s: Session,
    org_id: UUID,
    page: PageParams,
    *,
    project_id: UUID | None = None,
    filters: AuditFilter = AuditFilter(),
) -> tuple[list[EventRow], int]:
    """The audit log (docs/02 §13.3): every event of the organization, or of one project, unfiltered by
    kind (unlike the activity feed)."""
    return _paged(s, _filtered(_scope(org_id, project_id), filters), page)


def export_events(
    s: Session,
    org_id: UUID,
    *,
    project_id: UUID | None = None,
    filters: AuditFilter = AuditFilter(),
    limit: int,
) -> list[EventRow]:
    """Newest first, at most `limit` (+1 so the caller can tell the file would be cut)."""
    stmt = _filtered(_scope(org_id, project_id), filters)
    rows = s.execute(
        stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    ).scalars()
    return [_row(e) for e in rows]


def entity_history(
    s: Session,
    org_id: UUID,
    entity_type: str,
    entity_id: UUID,
    page: PageParams,
    *,
    filters: AuditFilter = AuditFilter(),
) -> tuple[list[EventRow], int]:
    stmt = select(AuditEvent).where(
        AuditEvent.organization_id == org_id,
        AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id == entity_id,
    )
    stmt = _filtered(stmt, filters)
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
