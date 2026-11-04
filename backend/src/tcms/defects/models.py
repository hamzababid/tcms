"""Defect tables (docs/05 §3.6). Private to the defects module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, created_ts, pk
from tcms.core.db import Base
from tcms.core.enums import DefectResolution, DefectStatus, PriorityLevel, T


class Defect(StdColumns, Base):
    __tablename__ = "defects"
    __audit_type__ = "defect"
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
        Index("ux_defects__project_id_key_num", "project_id", "key_num", unique=True),
        Index("ux_defects__project_id_key", "project_id", "key", unique=True),
        Index("ix_defects__project_status_severity", "project_id", "status", "severity"),
        Index("ix_defects__assignee_status", "assignee_id", "status"),
        Index("ix_defects__found_in_release", "found_in_release_id"),
        Index("ix_defects__folder_id", "folder_id"),
        Index("ix_defects__search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_defects__title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    key_num: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    steps_to_reproduce: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    actual_result: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[PriorityLevel] = mapped_column(
        T("priority_level"), nullable=False, server_default="medium"
    )
    priority: Mapped[PriorityLevel] = mapped_column(
        T("priority_level"), nullable=False, server_default="medium"
    )
    status: Mapped[DefectStatus] = mapped_column(T("defect_status"), nullable=False, server_default="open")
    environment_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("environments.id"))
    build: Mapped[str | None] = mapped_column(Text)
    browser_device: Mapped[str | None] = mapped_column(Text)
    folder_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("folders.id"))
    found_in_release_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("releases.id"))
    fix_version: Mapped[str | None] = mapped_column(Text)
    reporter_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("users.id"))
    resolution: Mapped[DefectResolution | None] = mapped_column(T("defect_resolution"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    duplicate_of_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("defects.id"))
    external_owner: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=False, server_default="")


class DefectLink(Base):
    __tablename__ = "defect_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "defect_id"], ["defects.project_id", "defects.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["project_id", "result_id"], ["test_results.project_id", "test_results.id"]),
        ForeignKeyConstraint(["project_id", "run_id"], ["test_runs.project_id", "test_runs.id"]),
        ForeignKeyConstraint(["project_id", "test_case_id"], ["test_cases.project_id", "test_cases.id"]),
        ForeignKeyConstraint(
            ["project_id", "requirement_id"], ["requirements.project_id", "requirements.id"]
        ),
        # ux_defect_links__target is an expression index (coalesce), see migrations/env.py.
        Index("ix_defect_links__result_id", "result_id"),
        Index("ix_defect_links__run_id", "run_id"),
        Index("ix_defect_links__test_case_id", "test_case_id"),
        Index("ix_defect_links__requirement_id", "requirement_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    defect_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    result_id: Mapped[UUID | None] = mapped_column(UUIDT)
    run_id: Mapped[UUID | None] = mapped_column(UUIDT)
    step_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("test_case_steps.id"))
    test_case_id: Mapped[UUID | None] = mapped_column(UUIDT)
    requirement_id: Mapped[UUID | None] = mapped_column(UUIDT)
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)


class DefectStatusHistory(Base):
    """Append-only (trigger + no UPDATE/DELETE grant)."""

    __tablename__ = "defect_status_history"
    __table_args__ = (Index("ix_defect_status_history__defect_changed", "defect_id", "changed_at"),)

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    defect_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("defects.id"), nullable=False)
    from_status: Mapped[DefectStatus | None] = mapped_column(T("defect_status"))
    to_status: Mapped[DefectStatus] = mapped_column(T("defect_status"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())


class DefectWatcher(Base):
    __tablename__ = "defect_watchers"

    defect_id: Mapped[UUID] = mapped_column(
        UUIDT, ForeignKey("defects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), primary_key=True)
