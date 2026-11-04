"""Execution tables (docs/05 §3.5). Private to the execution module."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import TS, UUIDT, StdColumns, pk
from tcms.core.db import Base
from tcms.core.enums import CycleStatus, ResultSource, ResultState, ResultStatus, RunStatus, StepStatus, T


class TestCycle(StdColumns, Base):
    __tablename__ = "test_cycles"
    __audit_type__ = "test_cycle"
    __test__ = False
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
        ForeignKeyConstraint(["project_id", "plan_id"], ["test_plans.project_id", "test_plans.id"]),
        Index("ux_test_cycles__project_id_key_num", "project_id", "key_num", unique=True),
        Index("ix_test_cycles__project_status", "project_id", "status"),
        Index("ix_test_cycles__release_id", "release_id"),
        Index("ix_test_cycles__plan_id", "plan_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    key_num: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    release_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("releases.id"))
    plan_id: Mapped[UUID | None] = mapped_column(UUIDT)
    environment_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("environments.id"), nullable=False)
    build: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CycleStatus] = mapped_column(T("cycle_status"), nullable=False, server_default="planned")
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    runs_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    started_at: Mapped[datetime | None] = mapped_column(TS)
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    closed_by: Mapped[UUID | None] = mapped_column(UUIDT)
    archived_at: Mapped[datetime | None] = mapped_column(TS)


_ACTIVE = text("superseded_by_run_id IS NULL")


class TestRun(StdColumns, Base):
    __tablename__ = "test_runs"
    __audit_type__ = "test_run"
    __test__ = False
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        ForeignKeyConstraint(["project_id", "cycle_id"], ["test_cycles.project_id", "test_cycles.id"]),
        ForeignKeyConstraint(["project_id", "test_case_id"], ["test_cases.project_id", "test_cases.id"]),
        ForeignKeyConstraint(
            ["latest_result_id"],
            ["test_results.id"],
            name="fk_test_runs_latest_result_id",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["superseded_by_run_id"],
            ["test_runs.id"],
            name="fk_test_runs_superseded_by_run_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "ux_test_runs__cycle_case_active",
            "cycle_id",
            "test_case_id",
            unique=True,
            postgresql_where=_ACTIVE,
        ),
        Index("ix_test_runs__cycle_status", "cycle_id", "status", postgresql_where=_ACTIVE),
        Index("ix_test_runs__assignee_status", "assignee_id", "status", postgresql_where=_ACTIVE),
        Index("ix_test_runs__test_case_id", "test_case_id"),
        Index("ix_test_runs__cycle_position", "cycle_id", "position"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    test_case_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    test_case_version_id: Mapped[UUID] = mapped_column(
        UUIDT, ForeignKey("test_case_versions.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("users.id"))
    status: Mapped[RunStatus] = mapped_column(T("run_status"), nullable=False, server_default="not_run")
    latest_result_id: Mapped[UUID | None] = mapped_column(UUIDT)
    needs_retest: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    superseded_by_run_id: Mapped[UUID | None] = mapped_column(UUIDT)
    superseded_at: Mapped[datetime | None] = mapped_column(TS)


class TestResult(Base):
    """An attempt. Immutable once final (BR-06; trigger trg_test_results_guard)."""

    __tablename__ = "test_results"
    __audit_type__ = "test_result"
    __test__ = False
    __table_args__ = (
        UniqueConstraint("project_id", "id"),
        ForeignKeyConstraint(["project_id", "run_id"], ["test_runs.project_id", "test_runs.id"]),
        Index("ux_test_results__run_attempt", "run_id", "attempt_no", unique=True),
        Index("ux_test_results__run_draft", "run_id", unique=True, postgresql_where=text("state = 'draft'")),
        Index(
            "ix_test_results__project_finished",
            "project_id",
            "finished_at",
            postgresql_where=text("state = 'final'"),
        ),
        Index("ix_test_results__executed_by_finished", "executed_by", "finished_at"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    run_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[ResultState] = mapped_column(T("result_state"), nullable=False, server_default="draft")
    status: Mapped[ResultStatus | None] = mapped_column(T("result_status"))
    source: Mapped[ResultSource] = mapped_column(T("result_source"), nullable=False, server_default="manual")
    executed_by: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    build: Mapped[str | None] = mapped_column(Text)
    environment_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("environments.id"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    skipped_steps: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    corrects_result_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("test_results.id"))
    automation_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    updated_by: Mapped[UUID | None] = mapped_column(UUIDT)


class TestStepResult(Base):
    __tablename__ = "test_step_results"
    __test__ = False
    __table_args__ = (
        Index("ux_test_step_results__result_step", "result_id", "step_id", unique=True),
        Index("ix_test_step_results__result_position", "result_id", "position"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    result_id: Mapped[UUID] = mapped_column(
        UUIDT, ForeignKey("test_results.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[UUID] = mapped_column(UUIDT, ForeignKey("test_case_steps.id"), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[StepStatus] = mapped_column(T("step_status"), nullable=False, server_default="not_run")
    actual_result: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    updated_by: Mapped[UUID | None] = mapped_column(UUIDT)
