"""Public read functions of the execution module.

Case execution history (FR-TD-013) plus, from M3, cycle/run reads (lists, summary, progress).
Recording attempts (the runner) arrives in M4.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.enums import CycleStatus, RunStatus
from tcms.core.pagination import FilterField, PageParams, paginate, parse_filters, parse_sort
from tcms.execution import repository as exec_repo
from tcms.execution.models import TestCycle, TestResult, TestRun
from tcms.testdesign.queries import case_refs
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


# -- cycles and runs (M3) -------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleSummaryData:
    total: int
    by_status: dict[str, int]


def cycle_summary(s: Session, ctx: AccessContext, cycle_id: UUID) -> CycleSummaryData:
    counts = exec_repo.status_counts(s, ctx, cycle_id)
    return CycleSummaryData(total=sum(counts.values()), by_status=counts)


@dataclass(frozen=True)
class AssigneeProgressData:
    assignee_id: UUID | None
    by_status: dict[str, int]
    total: int


def cycle_progress_by_assignee(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[AssigneeProgressData]:
    grouped: dict[UUID | None, dict[str, int]] = {}
    for assignee_id, status, n in exec_repo.assignee_counts(s, ctx, cycle_id):
        grouped.setdefault(assignee_id, {})[status] = n
    return [AssigneeProgressData(a, by_status, sum(by_status.values())) for a, by_status in grouped.items()]


CYCLE_FILTERS: Mapping[str, FilterField] = {
    "status": FilterField(TestCycle.status, kind="enum", choices=frozenset(s.value for s in CycleStatus)),
    "release_id": FilterField(TestCycle.release_id, kind="uuid"),
    "plan_id": FilterField(TestCycle.plan_id, kind="uuid"),
    "environment_id": FilterField(TestCycle.environment_id, kind="uuid"),
    "owner_id": FilterField(TestCycle.owner_id, kind="uuid"),
}
CYCLE_SORTS: Mapping[str, ColumnElement[Any]] = {
    "key": TestCycle.key_num,  # type: ignore[dict-item]
    "name": func.lower(TestCycle.name),
    "status": TestCycle.status,  # type: ignore[dict-item]
    "updated_at": TestCycle.updated_at,  # type: ignore[dict-item]
    "created_at": TestCycle.created_at,  # type: ignore[dict-item]
}


def cycle(s: Session, ctx: AccessContext, cycle_id: UUID) -> TestCycle | None:
    return exec_repo.cycle(s, ctx, cycle_id)


def list_cycles(
    s: Session, ctx: AccessContext, params: Mapping[str, str], page: PageParams
) -> tuple[list[TestCycle], int]:
    stmt: Select[Any] = exec_repo.cycle_list_stmt(ctx)
    conditions = parse_filters(params, CYCLE_FILTERS)
    if conditions:
        stmt = stmt.where(*conditions)
    if "status" not in params and params.get("include_archived") != "true":
        stmt = stmt.where(TestCycle.archived_at.is_(None))
    q = (params.get("q") or "").strip()
    if q:
        stmt = stmt.where(or_(TestCycle.name.icontains(q, autoescape=True), TestCycle.key.icontains(q)))
    stmt = stmt.order_by(*parse_sort(params.get("sort"), CYCLE_SORTS, default="key"))
    rows, total = paginate(s, stmt, page)
    return [r[0] for r in rows], total


RUN_FILTERS: Mapping[str, FilterField] = {
    "status": FilterField(TestRun.status, kind="enum", choices=frozenset(s.value for s in RunStatus)),
    "needs_retest": FilterField(TestRun.needs_retest, kind="bool"),
}
RUN_SORTS: Mapping[str, ColumnElement[Any]] = {
    "position": TestRun.position,  # type: ignore[dict-item]
    "status": TestRun.status,  # type: ignore[dict-item]
    "updated_at": TestRun.updated_at,  # type: ignore[dict-item]
}


@dataclass(frozen=True)
class RunRowData:
    run: TestRun
    case_key: str
    title: str
    version_no: int
    latest_version_no: int


def list_runs(
    s: Session, ctx: AccessContext, cycle_id: UUID, params: Mapping[str, str], page: PageParams
) -> tuple[list[RunRowData], int]:
    base = exec_repo.run_list_stmt(
        ctx, cycle_id, include_superseded=params.get("include_superseded") == "true"
    )
    conditions = parse_filters(params, RUN_FILTERS, extra_allowed=("include_superseded", "assignee_id"))
    if conditions:
        base = base.where(*conditions)
    assignee = params.get("assignee_id")
    if assignee == "me" and ctx.principal.user_id is not None:
        base = base.where(TestRun.assignee_id == ctx.principal.user_id)
    elif assignee == "none":
        base = base.where(TestRun.assignee_id.is_(None))
    elif assignee:
        base = base.where(TestRun.assignee_id == UUID(assignee))
    base = base.order_by(*parse_sort(params.get("sort"), RUN_SORTS, default="position"))
    rows, total = paginate(s, base, page)
    runs = [r[0] for r in rows]
    refs = case_refs(s, ctx, [r.test_case_id for r in runs])
    version_numbers = _version_numbers(s, [r.test_case_version_id for r in runs])
    out: list[RunRowData] = []
    for r in runs:
        ref = refs.get(r.test_case_id)
        out.append(
            RunRowData(
                run=r,
                case_key=ref.key if ref else "",
                title=ref.title if ref else "",
                version_no=version_numbers.get(r.test_case_version_id, 0),
                latest_version_no=_latest_version_no(s, ctx, r.test_case_id),
            )
        )
    return out, total


def _version_numbers(s: Session, version_ids: list[UUID]) -> dict[UUID, int]:
    from tcms.testdesign.queries import version_numbers

    return version_numbers(s, version_ids)


def _latest_version_no(s: Session, ctx: AccessContext, case_id: UUID) -> int:
    ref = case_refs(s, ctx, [case_id]).get(case_id)
    if ref is None or ref.latest_version_id is None:
        return 0
    return _version_numbers(s, [ref.latest_version_id]).get(ref.latest_version_id, 0)


def run_row(s: Session, ctx: AccessContext, run_id: UUID) -> RunRowData | None:
    r = exec_repo.run(s, ctx, run_id)
    if r is None:
        return None
    ref = case_refs(s, ctx, [r.test_case_id]).get(r.test_case_id)
    return RunRowData(
        run=r,
        case_key=ref.key if ref else "",
        title=ref.title if ref else "",
        version_no=_version_numbers(s, [r.test_case_version_id]).get(r.test_case_version_id, 0),
        latest_version_no=_latest_version_no(s, ctx, r.test_case_id),
    )


def owning_project_of_cycle(s: Session, cycle_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(TestCycle.organization_id, TestCycle.project_id).where(TestCycle.id == cycle_id)
    ).first()
    return (row[0], row[1]) if row else None


def owning_project_of_run(s: Session, run_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(select(TestRun.organization_id, TestRun.project_id).where(TestRun.id == run_id)).first()
    return (row[0], row[1]) if row else None
