"""Requirements tables (docs/05 §3.7). Private to the requirements module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, created_ts, pk
from tcms.core.db import Base
from tcms.core.enums import PriorityLevel, RequirementSource, RequirementStatus, RequirementType, T


class Requirement(StdColumns, Base):
    __tablename__ = "requirements"
    __audit_type__ = "requirement"
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
        Index("ux_requirements__project_id_key_num", "project_id", "key_num", unique=True),
        Index("ux_requirements__project_id_key", "project_id", "key", unique=True),
        Index("ix_requirements__project_release", "project_id", "target_release_id"),
        Index("ix_requirements__parent_id", "parent_id"),
        Index("ix_requirements__search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    key_num: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    external_key: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    type: Mapped[RequirementType] = mapped_column(T("requirement_type"), nullable=False)
    priority: Mapped[PriorityLevel] = mapped_column(
        T("priority_level"), nullable=False, server_default="medium"
    )
    status: Mapped[RequirementStatus] = mapped_column(
        T("requirement_status"), nullable=False, server_default="draft"
    )
    owner_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("users.id"))
    target_release_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("releases.id"))
    parent_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("requirements.id"))
    source: Mapped[RequirementSource] = mapped_column(
        T("requirement_source"), nullable=False, server_default="internal"
    )
    search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=False, server_default="")
    archived_at: Mapped[datetime | None] = mapped_column(TS)


class RequirementCaseLink(Base):
    __tablename__ = "requirement_case_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "requirement_id"],
            ["requirements.project_id", "requirements.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "test_case_id"], ["test_cases.project_id", "test_cases.id"], ondelete="CASCADE"
        ),
        Index("ix_requirement_case_links__test_case_id", "test_case_id"),
    )

    requirement_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    test_case_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)
