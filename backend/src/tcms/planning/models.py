"""Planning tables (docs/05 §3.4). Private to the planning module."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Date, ForeignKey, ForeignKeyConstraint, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, created_ts, pk
from tcms.core.db import Base
from tcms.core.enums import PlanStatus, PlanType, T


class TestPlan(StdColumns, Base):
    __tablename__ = "test_plans"
    __audit_type__ = "test_plan"
    __test__ = False
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
        Index("ux_test_plans__project_id_key_num", "project_id", "key_num", unique=True),
        Index("ix_test_plans__project_release", "project_id", "release_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    key_num: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[PlanType] = mapped_column(T("plan_type"), nullable=False)
    status: Mapped[PlanStatus] = mapped_column(T("plan_status"), nullable=False, server_default="draft")
    release_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("releases.id"))
    owner_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    objectives: Mapped[str | None] = mapped_column(Text)
    scope_in: Mapped[str | None] = mapped_column(Text)
    scope_out: Mapped[str | None] = mapped_column(Text)
    entry_criteria: Mapped[str | None] = mapped_column(Text)
    exit_criteria_notes: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    exit_rules: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    risks: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    member_ids: Mapped[list[UUID]] = mapped_column(ARRAY(UUIDT), nullable=False, server_default="{}")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    archived_at: Mapped[datetime | None] = mapped_column(TS)


class TestPlanCase(Base):
    __tablename__ = "test_plan_cases"
    __test__ = False
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "plan_id"], ["test_plans.project_id", "test_plans.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["project_id", "test_case_id"], ["test_cases.project_id", "test_cases.id"]),
        Index("ix_test_plan_cases__test_case_id", "test_case_id"),
    )

    plan_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    test_case_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    added_at: Mapped[datetime] = created_ts()
    added_by: Mapped[UUID | None] = mapped_column(UUIDT)


class TestPlanRequirement(Base):
    __tablename__ = "test_plan_requirements"
    __test__ = False
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "plan_id"], ["test_plans.project_id", "test_plans.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["project_id", "requirement_id"], ["requirements.project_id", "requirements.id"]
        ),
        Index("ix_test_plan_requirements__requirement_id", "requirement_id"),
    )

    plan_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    requirement_id: Mapped[UUID] = mapped_column(UUIDT, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    added_at: Mapped[datetime] = created_ts()
    added_by: Mapped[UUID | None] = mapped_column(UUIDT)


class TestPlanEnvironment(Base):
    __tablename__ = "test_plan_environments"
    __test__ = False

    plan_id: Mapped[UUID] = mapped_column(
        UUIDT, ForeignKey("test_plans.id", ondelete="CASCADE"), primary_key=True
    )
    environment_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("environments.id"), primary_key=True)
