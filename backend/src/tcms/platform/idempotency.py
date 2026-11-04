"""Stored `Idempotency-Key` responses (docs/06 §2.8); HTTP handling is in `tcms.api.idempotency`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from tcms.core import clock
from tcms.platform.models import IdempotencyKey

TTL = timedelta(hours=24)


@dataclass(frozen=True)
class StoredResponse:
    endpoint: str
    request_hash: bytes
    status: int
    body: Any


def find(s: Session, principal_id: UUID, key: str) -> StoredResponse | None:
    """Drops expired keys, then returns the stored response for (principal, key)."""
    s.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < clock.now() - TTL))
    row = s.execute(
        select(IdempotencyKey).where(IdempotencyKey.principal_id == principal_id, IdempotencyKey.key == key)
    ).scalar_one_or_none()
    if row is None:
        return None
    return StoredResponse(row.endpoint, row.request_hash, row.response_status, row.response_body)


def save(
    s: Session, principal_id: UUID, key: str, endpoint: str, request_hash: bytes, status: int, body: Any
) -> None:
    s.execute(
        pg_insert(IdempotencyKey)
        .values(
            principal_id=principal_id,
            key=key,
            endpoint=endpoint,
            request_hash=request_hash,
            response_status=status,
            response_body=body,
            created_at=clock.now(),
        )
        .on_conflict_do_nothing()
    )
