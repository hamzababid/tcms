"""Test design tables (docs/05 §3.3). Private to the testdesign module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, created_ts, pk
from tcms.core.db import Base
from tcms.core.enums import (
    ApprovalMode,
    AutomationStatus,
    CaseFormat,
    CaseLinkType,
    CaseStatus,
    CaseType,
    DesignTechnique,
    PriorityLevel,
    T,
)


def _project_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
    )


def _case_fk(column: str, *, cascade: bool = True) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["project_id", column],
        ["test_cases.project_id", "test_cases.id"],
        ondelete="CASCADE" if cascade else None,
    )


class Folder(StdColumns, Base):
    __tablename__ = "folders"
    __audit_type__ = "folder"
    __table_args__ = (
        _project_fk(),
        # ux_folders__project_parent_lower_name and ix_folders__project_id_path (text_pattern_ops)
        # are expression/opclass indexes, see migrations/env.py.
        Index("ix_folders__parent_id", "parent_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("folders.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    path: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(TS)
    archived_by: Mapped[UUID | None] = mapped_column(UUIDT)


class TestCase(StdColumns, Base):
    __tablename__ = "test_cases"
    __audit_type__ = "test_case"
    __test__ = False  # not a pytest class
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        _project_fk(),
        ForeignKeyConstraint(
            ["latest_version_id"],
            ["test_case_versions.id"],
            name="fk_test_cases_latest_version_id",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["approved_version_id"],
            ["test_case_versions.id"],
            name="fk_test_cases_approved_version_id",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        Index("ux_test_cases__project_id_key_num", "project_id", "key_num", unique=True),
        Index("ux_test_cases__project_id_key", "project_id", "key", unique=True),
        Index("ix_test_cases__project_folder_status", "project_id", "folder_id", "status"),
        Index("ix_test_cases__project_status_priority", "project_id", "status", "priority"),
        Index("ix_test_cases__owner_id", "owner_id"),
        Index("ix_test_cases__search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_test_cases__title_trgm",
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
    folder_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("folders.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[CaseFormat] = mapped_column(T("case_format"), nullable=False, server_default="steps")
    type: Mapped[CaseType] = mapped_column(T("case_type"), nullable=False, server_default="functional")
    design_technique: Mapped[DesignTechnique | None] = mapped_column(T("design_technique"))
    priority: Mapped[PriorityLevel] = mapped_column(
        T("priority_level"), nullable=False, server_default="medium"
    )
    status: Mapped[CaseStatus] = mapped_column(T("case_status"), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    reviewer_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("users.id"))
    automation_status: Mapped[AutomationStatus] = mapped_column(
        T("automation_status"), nullable=False, server_default="manual"
    )
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    latest_version_id: Mapped[UUID | None] = mapped_column(UUIDT)
    approved_version_id: Mapped[UUID | None] = mapped_column(UUIDT)
    latest_version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=False, server_default="")
    archived_at: Mapped[datetime | None] = mapped_column(TS)
    archived_by: Mapped[UUID | None] = mapped_column(UUIDT)


class TestCaseVersion(Base):
    """Immutable except submission/approval columns (BR-01; trigger trg_test_case_versions_guard)."""

    __tablename__ = "test_case_versions"
    __audit_type__ = "test_case_version"
    __test__ = False
    __table_args__ = (
        _case_fk("test_case_id"),
        Index("ux_test_case_versions__case_version", "test_case_id", "version_no", unique=True),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    test_case_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[CaseFormat] = mapped_column(T("case_format"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    preconditions: Mapped[str | None] = mapped_column(Text)
    test_data: Mapped[str | None] = mapped_column(Text)
    expected_result: Mapped[str | None] = mapped_column(Text)
    postconditions: Mapped[str | None] = mapped_column(Text)
    text_body: Mapped[str | None] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    created_at: Mapped[datetime] = created_ts()
    submitted_by: Mapped[UUID | None] = mapped_column(UUIDT)
    submitted_at: Mapped[datetime | None] = mapped_column(TS)
    approved_by: Mapped[UUID | None] = mapped_column(UUIDT)
    approved_at: Mapped[datetime | None] = mapped_column(TS)
    approval_mode: Mapped[ApprovalMode | None] = mapped_column(T("approval_mode"))


class TestCaseStep(Base):
    """Immutable (trigger trg_test_case_steps_guard)."""

    __tablename__ = "test_case_steps"
    __test__ = False
    __table_args__ = (Index("ux_test_case_steps__version_position", "version_id", "position", unique=True),)

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    version_id: Mapped[UUID] = mapped_column(
        UUIDT, ForeignKey("test_case_versions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str | None] = mapped_column(Text)
    data: Mapped[str | None] = mapped_column(Text)


class Tag(Base):
    __tablename__ = "tags"
    __audit_type__ = "tag"
    __table_args__ = (_project_fk(), Index("ux_tags__project_name", "project_id", "name", unique=True))

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)


class TestCaseTag(Base):
    __tablename__ = "test_case_tags"
    __test__ = False
    __table_args__ = (Index("ix_test_case_tags__tag_id", "tag_id"),)

    test_case_id: Mapped[UUID] = mapped_column(
        UUIDT, ForeignKey("test_cases.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class TestCaseLink(Base):
    __tablename__ = "test_case_links"
    __test__ = False
    __table_args__ = (
        _case_fk("source_case_id"),
        _case_fk("target_case_id"),
        Index("ux_test_case_links__pair", "source_case_id", "target_case_id", "link_type", unique=True),
        Index("ix_test_case_links__target", "target_case_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    source_case_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    target_case_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    link_type: Mapped[CaseLinkType] = mapped_column(T("case_link_type"), nullable=False)
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)


class AutomationKey(Base):
    __tablename__ = "automation_keys"
    __table_args__ = (
        _case_fk("test_case_id"),
        Index("ux_automation_keys__project_key", "project_id", "key", unique=True),
        Index("ix_automation_keys__test_case_id", "test_case_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    test_case_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_ts()
    created_by: Mapped[UUID | None] = mapped_column(UUIDT)
