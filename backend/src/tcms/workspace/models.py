"""Workspace tables (docs/05 §3.2). Private to the workspace module."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, pk
from tcms.core.db import Base
from tcms.core.enums import ProjectStatus, ReleaseDecisionKind, ReleaseStatus, T


class Organization(StdColumns, Base):
    __tablename__ = "organizations"
    __audit_type__ = "organization"
    __table_args__ = (Index("ux_organizations__slug", "slug", unique=True),)

    id: Mapped[UUID] = pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class Project(StdColumns, Base):
    __tablename__ = "projects"
    __audit_type__ = "project"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        Index("ux_projects__organization_id_key", "organization_id", "key", unique=True),
        # ux_projects__organization_id_lower_name: expression index (lower(name)), see migrations/env.py
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("organizations.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        T("project_status"), nullable=False, server_default=ProjectStatus.active.value
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    archived_at: Mapped[datetime | None] = mapped_column(TS)
    archived_by: Mapped[UUID | None] = mapped_column(UUIDT)


def _project_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
    )


class Environment(StdColumns, Base):
    __tablename__ = "environments"
    __audit_type__ = "environment"
    __table_args__ = (_project_fk(),)  # ux_environments__project_lower_name: expression index

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(TS)
    archived_by: Mapped[UUID | None] = mapped_column(UUIDT)


class Release(StdColumns, Base):
    __tablename__ = "releases"
    __audit_type__ = "release"
    __table_args__ = (_project_fk(),)  # ux_releases__project_lower_name: expression index

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReleaseStatus] = mapped_column(
        T("release_status"), nullable=False, server_default=ReleaseStatus.planned.value
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    released_at: Mapped[datetime | None] = mapped_column(TS)
    archived_at: Mapped[datetime | None] = mapped_column(TS)


class ReleaseDecision(Base):
    """Append-only (BR-26 family): the app role has INSERT/SELECT only."""

    __tablename__ = "release_decisions"
    __audit_type__ = "release_decision"
    __table_args__ = (_project_fk(),)

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    release_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("releases.id"), nullable=False)
    decision: Mapped[ReleaseDecisionKind] = mapped_column(T("release_decision_kind"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    risks: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())


class KeySequence(Base):
    __tablename__ = "key_sequences"

    project_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("projects.id"), primary_key=True)
    entity: Mapped[str] = mapped_column(Text, primary_key=True)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")


Index(
    "ix_release_decisions__release_id_decided_at",
    ReleaseDecision.release_id,
    ReleaseDecision.decided_at.desc(),
)
