"""Audit purge primitive (docs/02 §13.2). Only a `tcms_owner` session may delete audit rows; the
append-only trigger rejects any other role. Scheduling and the `audit.purged` record live in
`tcms.workspace.retention`."""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tcms.platform.models import AuditEvent

BATCH: Final = 10_000


def purge(s: Session, org_id: UUID, before: datetime, *, batch: int = BATCH) -> int:
    """Delete the organization's events that occurred before `before`, `batch` rows per statement."""
    total = 0
    while True:
        ids = (
            select(AuditEvent.id)
            .where(AuditEvent.organization_id == org_id, AuditEvent.occurred_at < before)
            .limit(batch)
            .scalar_subquery()
        )
        result = s.execute(delete(AuditEvent).where(AuditEvent.id.in_(ids)))
        deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
        total += deleted
        if deleted < batch:
            return total
