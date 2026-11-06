"""Bug links table (docs/05 §3.6, docs/schema/04_m5_bug_links.sql). Private to the bugs module."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from tcms.core.columns import UUIDT, StdColumns, pk
from tcms.core.db import Base


class BugLink(StdColumns, Base):
    __tablename__ = "bug_links"
    __audit_type__ = "bug_link"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "project_id"], ["projects.organization_id", "projects.id"]),
        ForeignKeyConstraint(["project_id", "test_case_id"], ["test_cases.project_id", "test_cases.id"]),
        ForeignKeyConstraint(["project_id", "run_id"], ["test_runs.project_id", "test_runs.id"]),
        ForeignKeyConstraint(["project_id", "result_id"], ["test_results.project_id", "test_results.id"]),
        # ux_bug_links__target is an expression index (coalesce), see migrations/env.py.
        Index("ix_bug_links__project_reference", "project_id", "reference_norm"),
        Index("ix_bug_links__run_id", "run_id"),
        Index("ix_bug_links__result_id", "result_id"),
        Index("ix_bug_links__test_case_id", "test_case_id"),
    )

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    project_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    reference_norm: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    test_case_id: Mapped[UUID] = mapped_column(UUIDT, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(UUIDT)
    result_id: Mapped[UUID | None] = mapped_column(UUIDT)
    step_id: Mapped[UUID | None] = mapped_column(UUIDT, ForeignKey("test_case_steps.id"))
