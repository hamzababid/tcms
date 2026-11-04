"""Reporting tables (docs/05 §3.8). Private to the reporting module."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Date, ForeignKey, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import UUIDT, created_ts, pk
from tcms.core.db import Base


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    # ux_metric_snapshots__scope_day is an expression index (coalesce), see migrations/env.py.
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    release_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("releases.id"))
    cycle_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("test_cycles.id"))
    day: Mapped[date] = mapped_column(Date, nullable=False)
    counters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_ts()
