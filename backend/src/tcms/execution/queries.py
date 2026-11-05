"""Public read functions of the execution module.

Case execution history (FR-TD-013) and cycle/run reads (docs/06 §4.6, §5.3–5.4). Counts are returned
raw; the metrics built from them come from `reporting/metrics.py` (CLAUDE.md rule 5). Recording
attempts (the runner) arrives in M4.
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
from tcms.core.enums import CycleStatus, PriorityLevel, ResultState, RunStatus
from tcms.core.errors import InvalidFilter, NotFound
from tcms.core.pagination import FilterField, PageParams, paginate, parse_filters, parse_sort
from tcms.execution import repository as exec_repo
from tcms.execution import rules
from tcms.execution.models import TestCycle, TestResult, TestRun
from tcms.testdesign import queries as td

__all__ = [
    "TestCycle"
]  # the read type other layers annotate with (the model stays module-private for writes)
from tcms.workspace import queries as workspace_queries

# -- case execution history (M2 case detail) ------------------------------------------------------


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
    numbers = {v.id: v.version_no for v in td.versions(s, ctx, case_id)}
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


# -- cycles ---------------------------------------------------------------------------------------


def cycle(s: Session, ctx: AccessContext, cycle_id: UUID) -> TestCycle | None:
    return exec_repo.cycle(s, ctx, cycle_id)


def cycle_by_key(s: Session, ctx: AccessContext, key: str) -> TestCycle | None:
    """`SPARK-CY-12`, `CY-12` or `12` within the project."""
    number = _key_number(s, ctx, key, "CY")
    if number is None:
        return None
    return s.execute(exec_repo.cycle_list_stmt(ctx).where(TestCycle.key_num == number)).scalar_one_or_none()


def _key_number(s: Session, ctx: AccessContext, key: str, prefix: str) -> int | None:
    import re

    m = re.match(rf"^(?:([A-Z][A-Z0-9]{{1,9}})-{prefix}-|{prefix}-)?(\d+)$", key.strip(), re.I)
    if not m:
        return None
    if m.group(1):
        p = workspace_queries.project_ref(s, ctx.principal.organization_id, ctx.pid)
        if p is None or m.group(1).upper() != p.key:
            return None
    return int(m.group(2))


def status_counts(s: Session, ctx: AccessContext, cycle_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    return exec_repo.status_counts(s, ctx, cycle_ids)


def needs_retest_counts(s: Session, ctx: AccessContext, cycle_ids: list[UUID]) -> dict[UUID, int]:
    return exec_repo.needs_retest_counts(s, ctx, cycle_ids)


def superseded_count(s: Session, ctx: AccessContext, cycle_id: UUID) -> int:
    return exec_repo.superseded_count(s, ctx, cycle_id)


@dataclass(frozen=True)
class GroupCounts:
    """Run counts by status for one assignee or folder (FR-EXE-013)."""

    id: UUID | None
    name: str
    counts: dict[str, int]


def progress_by_assignee(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[GroupCounts]:
    from tcms.identity import queries as identity_queries

    grouped: dict[UUID | None, dict[str, int]] = {}
    for assignee_id, status, n in exec_repo.assignee_counts(s, ctx, cycle_id):
        grouped.setdefault(assignee_id, {})[status] = n
    refs = identity_queries.user_refs(s, {a for a in grouped if a is not None})
    rows = [
        GroupCounts(a, refs[a].display_name if a in refs else "Unassigned", c) for a, c in grouped.items()
    ]
    return sorted(rows, key=lambda g: (g.id is None, g.name.lower()))


def progress_by_folder(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[GroupCounts]:
    grouped: dict[UUID, dict[str, int]] = {}
    for folder_id, status, n in exec_repo.folder_counts(s, ctx, cycle_id, td.case_columns(ctx)):
        grouped.setdefault(folder_id, {})[status] = n
    names = td.folder_names(s, ctx, list(grouped))
    order = td.folder_order(s, ctx)
    rows = [GroupCounts(f, names.get(f, "—"), c) for f, c in grouped.items()]
    return sorted(rows, key=lambda g: order.get(g.id, len(order)) if g.id else len(order))


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
    "due_date": TestCycle.due_date,  # type: ignore[dict-item]
    "updated_at": TestCycle.updated_at,  # type: ignore[dict-item]
    "created_at": TestCycle.created_at,  # type: ignore[dict-item]
}


def list_cycles(
    s: Session, ctx: AccessContext, params: Mapping[str, str], page: PageParams
) -> tuple[list[TestCycle], int]:
    stmt: Select[Any] = exec_repo.cycle_list_stmt(ctx)
    conditions = parse_filters(params, CYCLE_FILTERS, extra_allowed=("include_archived",))
    if conditions:
        stmt = stmt.where(*conditions)
    if params.get("include_archived") != "true":
        stmt = stmt.where(TestCycle.archived_at.is_(None))
    q = (params.get("q") or "").strip()
    if q:
        number = _key_number(s, ctx, q, "CY")
        text_match = or_(
            TestCycle.name.icontains(q, autoescape=True), TestCycle.key.icontains(q, autoescape=True)
        )
        stmt = stmt.where(or_(text_match, TestCycle.key_num == number) if number is not None else text_match)
    stmt = stmt.order_by(*parse_sort(params.get("sort"), CYCLE_SORTS, default="-key"))
    rows, total = paginate(s, stmt, page)
    return [r[0] for r in rows], total


def cycles_of_plan(s: Session, ctx: AccessContext, plan_id: UUID) -> list[TestCycle]:
    return exec_repo.cycles_of_plan(s, ctx, plan_id)


def open_cycles(s: Session, ctx: AccessContext) -> list[TestCycle]:
    return exec_repo.open_cycles(s, ctx)


@dataclass(frozen=True)
class PlanCaseResult:
    cycle_id: UUID
    cycle_key: str
    status: str


def plan_case_results(
    s: Session, ctx: AccessContext, plan_id: UUID, case_ids: list[UUID]
) -> dict[UUID, list[PlanCaseResult]]:
    """Per case, its run status in every cycle created from the plan (docs/02 §6.2), one query."""
    out: dict[UUID, list[PlanCaseResult]] = {c: [] for c in case_ids}
    if not case_ids:
        return out
    rows = s.execute(
        select(TestRun.test_case_id, TestCycle.id, TestCycle.key, TestRun.status)
        .join(TestCycle, TestCycle.id == TestRun.cycle_id)
        .where(
            TestRun.organization_id == ctx.principal.organization_id,
            TestRun.project_id == ctx.pid,
            TestCycle.plan_id == plan_id,
            TestRun.superseded_by_run_id.is_(None),
            TestRun.test_case_id.in_(case_ids),
        )
        .order_by(TestCycle.key_num)
    ).all()
    for case_id, cid, ckey, status in rows:
        out[case_id].append(PlanCaseResult(cid, ckey, status.value))
    return out


# -- runs -----------------------------------------------------------------------------------------

RUN_SPECIAL = ("assignee_id", "folder_id", "tag", "include_superseded")


@dataclass(frozen=True)
class RunRow:
    run: TestRun
    case_key: str
    title: str
    priority: str
    folder_id: UUID
    folder_name: str
    pinned_version_no: int
    eligible_version_no: int | None  # when a newer eligible version exists (docs/07 §5.8 "v3↑")


def _runs_stmt(
    s: Session, ctx: AccessContext, cycle_id: UUID, params: Mapping[str, str]
) -> tuple[Select[Any], Any]:
    cols = td.case_columns(ctx)
    include_superseded = params.get("include_superseded") == "true"
    stmt = (
        exec_repo.run_list_stmt(ctx, cycle_id, include_superseded=include_superseded)
        .join(cols, cols.c.id == TestRun.test_case_id)
        .add_columns(cols.c.key, cols.c.title, cols.c.priority, cols.c.folder_id)
    )
    allowed: Mapping[str, FilterField] = {
        "status": FilterField(TestRun.status, kind="enum", choices=frozenset(x.value for x in RunStatus)),
        "priority": FilterField(
            cols.c.priority, kind="enum", choices=frozenset(p.value for p in PriorityLevel)
        ),
        "needs_retest": FilterField(TestRun.needs_retest, kind="bool"),
    }
    conditions = parse_filters(params, allowed, extra_allowed=RUN_SPECIAL)
    if conditions:
        stmt = stmt.where(*conditions)
    assignee = params.get("assignee_id")
    if assignee == "me":
        stmt = stmt.where(TestRun.assignee_id == ctx.principal.user_id)
    elif assignee == "none":
        stmt = stmt.where(TestRun.assignee_id.is_(None))
    elif assignee:
        stmt = stmt.where(TestRun.assignee_id.in_([_uuid("assignee_id", a) for a in assignee.split(",")]))
    folder = params.get("folder_id")
    if folder:
        stmt = stmt.where(cols.c.folder_id.in_(td.subtree_folder_ids(s, ctx, _uuid("folder_id", folder))))
    tag = params.get("tag")
    if tag:
        stmt = stmt.where(TestRun.test_case_id.in_(td.tagged_case_ids_stmt(ctx, tag.split(","))))
    q = (params.get("q") or "").strip()
    if q:
        stmt = stmt.where(TestRun.test_case_id.in_(td.search_case_ids_stmt(s, ctx, q)))
    return stmt, cols


def _uuid(name: str, raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as exc:
        raise InvalidFilter(f"Invalid value '{raw}' for '{name}'") from exc


def _rows(s: Session, ctx: AccessContext, raw: list[Any]) -> list[RunRow]:
    runs = [r[0] for r in raw]
    refs = td.case_refs(s, ctx, [r.test_case_id for r in runs])
    approval = _approval_required(s, ctx)
    eligible: dict[UUID, UUID | None] = {}
    for r in runs:
        ref = refs.get(r.test_case_id)
        eligible[r.id] = (
            rules.eligible_version(ref, approval_required=approval, purpose="existing").version_id
            if ref
            else None
        )
    numbers = td.version_numbers(
        s, list({r.test_case_version_id for r in runs} | {v for v in eligible.values() if v is not None})
    )
    folders = td.folder_names(s, ctx, list({row[4] for row in raw}))
    out: list[RunRow] = []
    for row in raw:
        r, key, title, priority, folder_id = row[0], row[1], row[2], row[3], row[4]
        v = eligible[r.id]
        newer = numbers.get(v) if v is not None and v != r.test_case_version_id else None
        out.append(
            RunRow(
                r,
                key,
                title,
                priority.value if hasattr(priority, "value") else str(priority),
                folder_id,
                folders.get(folder_id, "—"),
                numbers.get(r.test_case_version_id, 0),
                newer,
            )
        )
    return out


def _approval_required(s: Session, ctx: AccessContext) -> bool:
    p = workspace_queries.project(s, ctx.principal.organization_id, ctx.pid)
    return bool(p and workspace_queries.project_settings(p)["approval_required"])


def list_runs(
    s: Session, ctx: AccessContext, cycle_id: UUID, params: Mapping[str, str], page: PageParams
) -> tuple[list[RunRow], int]:
    """docs/06 §4.6: filters status, assignee_id (me, none), folder_id, priority, needs_retest, tag, q,
    include_superseded; sort position, key, status, priority, updated_at."""
    stmt, cols = _runs_stmt(s, ctx, cycle_id, params)
    sorts: Mapping[str, ColumnElement[Any]] = {
        "position": TestRun.position,  # type: ignore[dict-item]
        "key": cols.c.key_num,
        "status": TestRun.status,  # type: ignore[dict-item]
        "priority": cols.c.priority_rank,
        "updated_at": TestRun.updated_at,  # type: ignore[dict-item]
    }
    stmt = stmt.order_by(*parse_sort(params.get("sort"), sorts, default="position"), TestRun.id)
    raw, total = paginate(s, stmt, page)
    return _rows(s, ctx, raw), total


def run_ids_matching(s: Session, ctx: AccessContext, cycle_id: UUID, params: Mapping[str, str]) -> list[UUID]:
    """Active run ids matching a runs-list filter (filter-based bulk assign, docs/06 §4.6)."""
    stmt, _ = _runs_stmt(s, ctx, cycle_id, {**params, "include_superseded": "false"})
    return list(s.execute(stmt.with_only_columns(TestRun.id).order_by(TestRun.position)).scalars())


def run_row(s: Session, ctx: AccessContext, run_id: UUID) -> RunRow | None:
    r = exec_repo.run(s, ctx, run_id)
    if r is None:
        return None
    stmt, _ = _runs_stmt(s, ctx, r.cycle_id, {"include_superseded": "true"})
    raw = s.execute(stmt.where(TestRun.id == run_id)).all()
    rows = _rows(s, ctx, list(raw))
    return rows[0] if rows else None


@dataclass(frozen=True)
class AttemptView:
    id: UUID
    attempt_no: int
    state: str
    status: str | None
    executed_by: UUID | None
    started_at: datetime
    finished_at: datetime | None
    skipped_steps: int
    corrects_result_id: UUID | None


@dataclass(frozen=True)
class RunDetail:
    row: RunRow
    cycle: TestCycle
    folder_path: list[str]
    has_attempts: bool
    newer: rules.NewerVersion | None
    history: list[AttemptView]
    draft: AttemptView | None


def run_detail(s: Session, ctx: AccessContext, run_id: UUID) -> RunDetail:
    """docs/06 §5.4 (`GET /runs/{id}`): run, case summary, newer-version info and attempts."""
    row = run_row(s, ctx, run_id)
    if row is None:
        raise NotFound()
    cyc = exec_repo.cycle(s, ctx, row.run.cycle_id)
    if cyc is None:
        raise NotFound()
    attempts = exec_repo.attempts(s, run_id)
    views = [
        AttemptView(
            a.id,
            a.attempt_no,
            a.state.value,
            a.status.value if a.status else None,
            a.executed_by,
            a.started_at,
            a.finished_at,
            a.skipped_steps,
            a.corrects_result_id,
        )
        for a in attempts
    ]
    ref = td.case_refs(s, ctx, [row.run.test_case_id]).get(row.run.test_case_id)
    eligible = (
        rules.eligible_version(
            ref, approval_required=_approval_required(s, ctx), purpose="existing"
        ).version_id
        if ref
        else None
    )
    newer = rules.newer_version(
        pinned_version_id=row.run.test_case_version_id,
        eligible_version_id=eligible,
        has_attempts=bool(attempts),
        cycle_status=cyc.status,
        superseded=row.run.superseded_by_run_id is not None,
    )
    return RunDetail(
        row=row,
        cycle=cyc,
        folder_path=td.folder_path_names(s, ctx, row.folder_id),
        has_attempts=bool(attempts),
        newer=newer,
        history=[v for v in views if v.state == ResultState.final.value],
        draft=next((v for v in views if v.state == ResultState.draft.value), None),
    )


def owning_project_of_cycle(s: Session, cycle_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(TestCycle.organization_id, TestCycle.project_id).where(TestCycle.id == cycle_id)
    ).first()
    return (row[0], row[1]) if row else None


def owning_project_of_run(s: Session, run_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(select(TestRun.organization_id, TestRun.project_id).where(TestRun.id == run_id)).first()
    return (row[0], row[1]) if row else None
