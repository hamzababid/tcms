"""Shared column helpers for ORM models (docs/05 §1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

UUIDT = PGUUID(as_uuid=True)
TS = DateTime(timezone=True)


def pk() -> Mapped[UUID]:
    return mapped_column(UUIDT, primary_key=True)


def created_ts() -> Mapped[datetime]:
    return mapped_column(TS, nullable=False, server_default=func.now())


class StdColumns:
    """The "std" block: created_at/by, updated_at/by, row_version."""

    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)
    updated_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    updated_by: Mapped[UUID | None] = mapped_column(UUIDT)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
