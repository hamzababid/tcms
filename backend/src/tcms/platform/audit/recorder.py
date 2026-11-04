"""Writes audit records collected by the UnitOfWork (docs/04 §3.5, BR-26)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from tcms.core.uow import AuditRecord
from tcms.platform.audit.render import render_summary
from tcms.platform.models import AuditEvent

_SECRET_FIELDS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "token_hash",
        "totp_secret_enc",
        "secret",
        "code_hash",
        "recovery_codes",
    }
)


def redact(changes: dict[str, Any] | None) -> dict[str, Any] | None:
    if changes is None:
        return None
    return {k: (["[redacted]", "[redacted]"] if k in _SECRET_FIELDS else v) for k, v in changes.items()}


def write_audit(session: Session, records: list[AuditRecord]) -> None:
    rows = [
        {
            "id": r.id,
            "occurred_at": r.occurred_at,
            "organization_id": r.organization_id,
            "project_id": r.project_id,
            "actor_type": r.actor_type.value,
            "actor_id": r.actor_id,
            "actor_display": r.actor_display,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "entity_key": r.entity_key,
            "changes": redact(r.changes),
            "context": r.context,
            "summary": r.summary or render_summary(r),
        }
        for r in records
    ]
    session.execute(insert(AuditEvent), rows)
