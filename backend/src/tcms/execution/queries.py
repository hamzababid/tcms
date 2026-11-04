"""Public read functions of the execution module.

M2 needs only a case's execution history (FR-TD-013); cycles and runs arrive in M3/M4, so the result is
empty until then (a real query, not a placeholder).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.execution.models import TestCycle, TestResult, TestRun
from tcms.testdesign.queries import versions as case_versions


@dataclass(frozen=True)
class CaseExecution:
    run_id: UUID
    cycle_id: UUID
    cycle_key: str
    cycle_name: str
    cycle_status: str
    release_id: UUID | None
    environment_id: UUID
    version_no: int
    status: str
    superseded: bool
    executed_by: UUID | None
    finished_at: datetime | None
    due_date: date | None


def case_executions(s: Session, ctx: AccessContext, case_id: UUID) -> list[CaseExecution]:
    numbers = {v.id: v.version_no for v in case_versions(s, ctx, case_id)}
    rows = s.execute(
        select(TestRun, TestCycle, TestResult)
        .join(TestCycle, TestCycle.id == TestRun.cycle_id)
        .outerjoin(TestResult, TestResult.id == TestRun.latest_result_id)
        .where(
            TestRun.organization_id == ctx.principal.organization_id,
            TestRun.project_id == ctx.pid,
            TestRun.test_case_id == case_id,
        )
        .order_by(TestCycle.created_at.desc())
    ).all()
    return [
        CaseExecution(
            run.id,
            cyc.id,
            cyc.key,
            cyc.name,
            cyc.status.value,
            cyc.release_id,
            cyc.environment_id,
            numbers.get(run.test_case_version_id, 0),
            run.status.value,
            run.superseded_by_run_id is not None,
            res.executed_by if res else None,
            res.finished_at if res else None,
            cyc.due_date,
        )
        for run, cyc, res in rows
    ]
