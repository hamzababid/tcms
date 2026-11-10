"""Filtered reads behind every dashboard, readiness rule, snapshot and report (docs/02 §11.1–11.2,
docs/04 §8, ADR-013, BR-24).

Reporting reads every module's tables through SQL (docs/03 §5). One `Scope` describes the filters of
docs/02 §11.1; `runs_sql` turns it into the "runs in scope" relation (non-superseded runs, BR-05) that
every count below is built on, so dashboards, readiness and reports cannot disagree (TCMS-115). The
metrics themselves are computed in `reporting/metrics.py`.

SQL is assembled only from fixed fragments; every value is a bound parameter.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.reporting import cache as _cache  # noqa: F401  (session memo reset)
from tcms.reporting.metrics import BugMetrics, ExecutionSummary, RepositoryMetrics

EXECUTED = ("passed", "failed", "blocked")


@dataclass(frozen=True)
class Scope:
    """docs/02 §11.1 filters. `cycle_ids` narrows to those cycles; `plan_id` to a plan's cycles."""

    release_id: UUID | None = None
    cycle_ids: tuple[UUID, ...] | None = None
    plan_id: UUID | None = None
    environment_id: UUID | None = None
    module_folder_id: UUID | None = None
    tester_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    tag: str | None = None
    open_cycles_only: bool = False

    def window(self) -> tuple[datetime | None, datetime | None]:
        """[from 00:00 UTC, to + 1 day 00:00 UTC) — dates are UTC days."""
        lo = datetime.combine(self.date_from, time.min, UTC) if self.date_from else None
        hi = datetime.combine(self.date_to + timedelta(days=1), time.min, UTC) if self.date_to else None
        return lo, hi


@dataclass
class _Sql:
    where: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    def add(self, clause: str, **params: Any) -> None:
        self.where.append(clause)
        self.params.update(params)

    @property
    def clause(self) -> str:
        return " AND ".join(self.where) if self.where else "TRUE"


def cycle_filter(ctx: AccessContext, scope: Scope, alias: str = "c") -> _Sql:
    q = _Sql()
    q.add(
        f"{alias}.organization_id = :org AND {alias}.project_id = :pid",
        org=ctx.principal.organization_id,
        pid=ctx.pid,
    )
    if scope.release_id is not None:
        q.add(f"{alias}.release_id = :rid", rid=scope.release_id)
    if scope.cycle_ids is not None:
        q.add(f"{alias}.id = ANY(:cycle_ids)", cycle_ids=list(scope.cycle_ids))
    if scope.plan_id is not None:
        q.add(f"{alias}.plan_id = :plan_id", plan_id=scope.plan_id)
    if scope.environment_id is not None:
        q.add(f"{alias}.environment_id = :env", env=scope.environment_id)
    if scope.open_cycles_only:
        q.add(f"{alias}.status IN ('planned', 'active')")
    return q


def runs_sql(ctx: AccessContext, scope: Scope) -> tuple[str, dict[str, Any]]:
    """`SELECT …` of the runs in scope with their current attempt (BR-08) — use as a CTE named `rs`.

    Tester (docs/02 §11.1): `executed_by` of the current attempt for executed, skipped and N/A runs,
    the assignee for pending ones.
    """
    q = cycle_filter(ctx, scope)
    q.add("r.superseded_by_run_id IS NULL")
    if scope.module_folder_id is not None:
        q.add(
            "f.path LIKE (SELECT m.path FROM folders m WHERE m.id = :module AND m.project_id = :pid) || '%'",
            module=scope.module_folder_id,
        )
    if scope.tester_id is not None:
        q.add(
            "(CASE WHEN r.status IN ('not_run', 'in_progress') THEN r.assignee_id ELSE lr.executed_by END)"
            " = :tester",
            tester=scope.tester_id,
        )
    if scope.tag is not None:
        q.add(
            "EXISTS (SELECT 1 FROM test_case_tags ct JOIN tags t ON t.id = ct.tag_id"
            " WHERE ct.test_case_id = r.test_case_id AND t.name = :tag)",
            tag=scope.tag,
        )
    sql = f"""
        SELECT r.id, r.status::text AS status, r.assignee_id, r.needs_retest, r.test_case_id, r.cycle_id,
               r.latest_result_id, lr.executed_by, lr.finished_at, tc.folder_id
        FROM test_runs r
        JOIN test_cycles c ON c.id = r.cycle_id
        JOIN test_cases tc ON tc.id = r.test_case_id
        JOIN folders f ON f.id = tc.folder_id
        LEFT JOIN test_results lr ON lr.id = r.latest_result_id AND lr.state = 'final'
        WHERE {q.clause}
    """
    return sql, q.params


def _with_runs(ctx: AccessContext, scope: Scope, body: str) -> tuple[Any, dict[str, Any]]:
    sql, params = runs_sql(ctx, scope)
    return text(f"WITH rs AS ({sql}) {body}"), params


# -- execution summary -------------------------------------------------------------------------------


def status_counts(s: Session, ctx: AccessContext, scope: Scope) -> tuple[dict[str, int], int]:
    """(counts by current run status, runs needing retest); remembered for the session (M8c P3)."""
    memo: dict[object, tuple[dict[str, int], int]] = s.info.setdefault("status_counts", {})
    key = (ctx.principal.organization_id, ctx.pid, scope)
    if key not in memo:
        memo[key] = _status_counts(s, ctx, scope)
    counts, retest = memo[key]
    return dict(counts), retest


def _status_counts(s: Session, ctx: AccessContext, scope: Scope) -> tuple[dict[str, int], int]:
    stmt, params = _with_runs(
        ctx, scope, "SELECT status, count(*), count(*) FILTER (WHERE needs_retest) FROM rs GROUP BY status"
    )
    counts: dict[str, int] = {}
    retest = 0
    for st, n, r in s.execute(stmt, params).all():
        counts[st] = int(n)
        retest += int(r)
    return counts, retest


def summary(s: Session, ctx: AccessContext, scope: Scope) -> ExecutionSummary:
    counts, retest = status_counts(s, ctx, scope)
    return ExecutionSummary.from_counts(counts, needs_retest=retest)


def counts_by_cycle(s: Session, ctx: AccessContext, scope: Scope) -> dict[UUID, tuple[dict[str, int], int]]:
    stmt, params = _with_runs(
        ctx,
        scope,
        "SELECT cycle_id, status, count(*), count(*) FILTER (WHERE needs_retest) FROM rs GROUP BY"
        " cycle_id, status",
    )
    out: dict[UUID, tuple[dict[str, int], int]] = {}
    for cid, st, n, r in s.execute(stmt, params).all():
        counts, retest = out.get(cid, ({}, 0))
        counts[st] = int(n)
        out[cid] = (counts, retest + int(r))
    return out


def retest_count(s: Session, ctx: AccessContext, scope: Scope) -> int:
    """docs/02 §11.2: finalized attempts with attempt_no > 1 on runs in scope (date range on finished_at)."""
    lo, hi = scope.window()
    stmt, params = _with_runs(
        ctx,
        scope,
        "SELECT count(*) FROM test_results tr JOIN rs ON rs.id = tr.run_id WHERE tr.state = 'final'"
        " AND tr.attempt_no > 1 AND (CAST(:lo AS timestamptz) IS NULL OR tr.finished_at >= :lo)"
        " AND (CAST(:hi AS timestamptz) IS NULL OR tr.finished_at < :hi)",
    )
    return int(s.execute(stmt, {**params, "lo": lo, "hi": hi}).scalar_one())


# -- bugs (ADR-023) ----------------------------------------------------------------------------------


def bug_metrics(s: Session, ctx: AccessContext, scope: Scope) -> BugMetrics:
    """Linked bugs = distinct references linked to runs in scope; on failing runs = linked to a run whose
    current status is failed; failures without a bug = failed runs with no link on the current attempt."""
    lo, hi = scope.window()
    stmt, params = _with_runs(
        ctx,
        scope,
        """
        SELECT
          (SELECT count(DISTINCT b.reference_norm) FROM bug_links b JOIN rs ON rs.id = b.run_id
            WHERE (CAST(:lo AS timestamptz) IS NULL OR b.created_at >= :lo)
              AND (CAST(:hi AS timestamptz) IS NULL OR b.created_at < :hi)),
          (SELECT count(DISTINCT b.reference_norm) FROM bug_links b JOIN rs ON rs.id = b.run_id
            WHERE rs.status = 'failed'),
          (SELECT count(*) FROM rs WHERE rs.status = 'failed' AND NOT EXISTS
             (SELECT 1 FROM bug_links b WHERE b.result_id = rs.latest_result_id))
        """,
    )
    linked, failing, without = s.execute(stmt, {**params, "lo": lo, "hi": hi}).one()
    return BugMetrics(linked=int(linked), on_failing_runs=int(failing), failures_without_bug=int(without))


@dataclass(frozen=True)
class BugRow:
    reference: str
    url: str | None
    title: str | None
    failing_runs: int
    runs: int


def bugs_on_failing_runs(s: Session, ctx: AccessContext, scope: Scope, limit: int = 10) -> list[BugRow]:
    stmt, params = _with_runs(
        ctx,
        scope,
        """
        SELECT min(b.reference), max(b.url), max(b.title),
               count(DISTINCT b.run_id) FILTER (WHERE rs.status = 'failed'), count(DISTINCT b.run_id)
        FROM bug_links b JOIN rs ON rs.id = b.run_id
        GROUP BY b.reference_norm
        HAVING count(*) FILTER (WHERE rs.status = 'failed') > 0
        ORDER BY 4 DESC, 1 LIMIT :limit
        """,
    )
    return [BugRow(*row) for row in s.execute(stmt, {**params, "limit": limit}).all()]


# -- team progress -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TesterRow:
    user_id: UUID | None
    assigned: int
    executed: int
    remaining: int
    failed: int
    blocked: int


def team(s: Session, ctx: AccessContext, scope: Scope) -> list[TesterRow]:
    """docs/02 §11.3 team progress per assignee; `user_id` None = the unassigned pool."""
    stmt, params = _with_runs(
        ctx,
        scope,
        """
        SELECT assignee_id, count(*) FILTER (WHERE status <> 'not_applicable'),
               count(*) FILTER (WHERE status IN ('passed', 'failed', 'blocked')),
               count(*) FILTER (WHERE status IN ('not_run', 'in_progress')),
               count(*) FILTER (WHERE status = 'failed'), count(*) FILTER (WHERE status = 'blocked')
        FROM rs GROUP BY assignee_id
        """,
    )
    rows = [TesterRow(*(r[0], *(int(x) for x in r[1:]))) for r in s.execute(stmt, params).all()]
    return sorted(rows, key=lambda t: (t.user_id is None, -t.assigned))


# -- cycles ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleRow:
    id: UUID
    key: str
    name: str
    status: str
    release_id: UUID | None
    environment_id: UUID
    due_date: date | None
    start_date: date | None


def cycles(s: Session, ctx: AccessContext, scope: Scope) -> list[CycleRow]:
    q = cycle_filter(ctx, scope)
    rows = s.execute(
        text(
            "SELECT c.id, c.key, c.name, c.status::text, c.release_id, c.environment_id,"
            " c.due_date, c.start_date"
            f" FROM test_cycles c WHERE {q.clause} AND c.archived_at IS NULL"
            " ORDER BY c.due_date NULLS LAST, c.key_num"
        ),
        q.params,
    ).all()
    return [CycleRow(*r) for r in rows]


# -- repository --------------------------------------------------------------------------------------


def repository(s: Session, ctx: AccessContext, module_folder_id: UUID | None = None) -> RepositoryMetrics:
    params: dict[str, Any] = {
        "org": ctx.principal.organization_id,
        "pid": ctx.pid,
        "module": module_folder_id,
    }
    module = (
        " AND f.path LIKE (SELECT m.path FROM folders m WHERE m.id = :module AND m.project_id = :pid) || '%'"
        if module_folder_id
        else ""
    )
    base = (
        "FROM test_cases tc JOIN folders f ON f.id = tc.folder_id"
        f" WHERE tc.organization_id = :org AND tc.project_id = :pid AND tc.status <> 'archived'{module}"
    )
    by_status = {
        k: int(n) for k, n in s.execute(text(f"SELECT tc.status::text, count(*) {base} GROUP BY 1"), params)
    }
    by_type = {
        k: int(n) for k, n in s.execute(text(f"SELECT tc.type::text, count(*) {base} GROUP BY 1"), params)
    }
    by_auto = {
        k: int(n)
        for k, n in s.execute(text(f"SELECT tc.automation_status::text, count(*) {base} GROUP BY 1"), params)
    }
    folders = int(
        s.execute(
            text(
                "SELECT count(*) FROM folders f WHERE f.organization_id = :org AND f.project_id = :pid"
                f" AND f.archived_at IS NULL{module}"
            ),
            params,
        ).scalar_one()
    )
    plans = {
        k: int(n)
        for k, n in s.execute(
            text(
                "SELECT status::text, count(*) FROM test_plans WHERE organization_id = :org AND"
                " project_id = :pid"
                " GROUP BY 1"
            ),
            params,
        )
    }
    return RepositoryMetrics.from_counts(
        by_status=by_status, by_type=by_type, by_automation=by_auto, folders=folders, plans_by_status=plans
    )


# -- trends (live part; history comes from snapshots) -----------------------------------------------


def attempts_per_day(
    s: Session, ctx: AccessContext, scope: Scope, lo: datetime, hi: datetime
) -> dict[date, dict[str, int]]:
    """Final attempts per UTC day by status on runs in scope, finished in [lo, hi)."""
    stmt, params = _with_runs(
        ctx,
        scope,
        "SELECT (tr.finished_at AT TIME ZONE 'UTC')::date, tr.status::text, count(*) FROM test_results tr"
        " JOIN rs ON rs.id = tr.run_id WHERE tr.state = 'final' AND tr.finished_at >= :lo AND"
        " tr.finished_at < :hi"
        " GROUP BY 1, 2",
    )
    out: dict[date, dict[str, int]] = {}
    for d, st, n in s.execute(stmt, {**params, "lo": lo, "hi": hi}).all():
        out.setdefault(d, {})[st] = int(n)
    return out


def bug_links_per_day(
    s: Session, ctx: AccessContext, scope: Scope, lo: datetime, hi: datetime
) -> dict[date, int]:
    stmt, params = _with_runs(
        ctx,
        scope,
        "SELECT (b.created_at AT TIME ZONE 'UTC')::date, count(*) FROM bug_links b JOIN rs ON rs.id"
        " = b.run_id"
        " WHERE b.created_at >= :lo AND b.created_at < :hi GROUP BY 1",
    )
    return {d: int(n) for d, n in s.execute(stmt, {**params, "lo": lo, "hi": hi}).all()}


def bugs_by_module(s: Session, ctx: AccessContext, scope: Scope, depth: int) -> list[tuple[UUID, str, int]]:
    """Distinct bug references on runs in scope per module (folder ancestor at `report_module_depth`)."""
    stmt, params = _with_runs(
        ctx,
        scope,
        """
        SELECT m.id, m.name, count(DISTINCT b.reference_norm)
        FROM bug_links b JOIN rs ON rs.id = b.run_id
        JOIN folders f ON f.id = rs.folder_id
        JOIN folders m ON m.id = CAST(split_part(f.path, '/', LEAST(f.depth, :depth) + 1) AS uuid)
        GROUP BY m.id, m.name ORDER BY 3 DESC, 2
        """,
    )
    return [(r[0], r[1], int(r[2])) for r in s.execute(stmt, {**params, "depth": depth}).all()]


def today_window() -> tuple[date, datetime, datetime]:
    now = clock.now()
    day = now.astimezone(UTC).date()
    lo = datetime.combine(day, time.min, UTC)
    return day, lo, lo + timedelta(days=1)


def last_activity(s: Session, org_id: UUID, project_ids: Sequence[UUID]) -> dict[UUID, datetime]:
    if not project_ids:
        return {}
    rows = s.execute(
        text(
            "SELECT project_id, max(occurred_at) FROM audit_events WHERE organization_id = :org"
            " AND project_id = ANY(:ids) GROUP BY project_id"
        ),
        {"org": org_id, "ids": list(project_ids)},
    ).all()
    return {p: t for p, t in rows}


def release_counts(s: Session, ctx: AccessContext, release_id: UUID) -> tuple[int, int]:
    """(plans, cycles) of a release (not archived)."""
    p = {"pid": ctx.pid, "rid": release_id}
    plans = s.execute(
        text(
            "SELECT count(*) FROM test_plans WHERE project_id = :pid AND release_id = :rid AND"
            " status <> 'archived'"
        ),
        p,
    ).scalar_one()
    cycles_ = s.execute(
        text(
            "SELECT count(*) FROM test_cycles WHERE project_id = :pid AND release_id = :rid AND"
            " archived_at IS NULL"
        ),
        p,
    ).scalar_one()
    return int(plans), int(cycles_)


def last_snapshot_day(s: Session, ctx: AccessContext) -> date | None:
    value: date | None = s.execute(
        text("SELECT max(day) FROM metric_snapshots WHERE project_id = :pid AND organization_id = :org"),
        {"pid": ctx.pid, "org": ctx.principal.organization_id},
    ).scalar_one()
    return value


# -- My Work for engineers (docs/02 §11.3, R-142) ---------------------------------------------------


@dataclass(frozen=True)
class AttentionRow:
    run_id: UUID
    project_id: UUID
    cycle_id: UUID
    cycle_key: str
    case_key: str
    title: str
    status: str
    needs_retest: bool


def my_attention(
    s: Session, org_id: UUID, project_ids: Sequence[UUID], user_id: UUID, limit: int = 20
) -> list[AttentionRow]:
    """My failed and blocked runs, and runs flagged for retest, in planned and active cycles; flagged runs
    first, then the most recently changed."""
    if not project_ids:
        return []
    rows = s.execute(
        text(
            """
            SELECT r.id, r.project_id, c.id, c.key, tc.key, tc.title, r.status::text, r.needs_retest
            FROM test_runs r JOIN test_cycles c ON c.id = r.cycle_id
            JOIN test_cases tc ON tc.id = r.test_case_id
            WHERE r.organization_id = :org AND r.project_id = ANY(:pids) AND r.assignee_id = :me
              AND r.superseded_by_run_id IS NULL AND c.status IN ('planned', 'active')
              AND (r.status IN ('failed', 'blocked') OR r.needs_retest)
            ORDER BY r.needs_retest DESC, r.updated_at DESC, r.id DESC
            LIMIT :limit
            """
        ),
        {"org": org_id, "pids": list(project_ids), "me": user_id, "limit": limit},
    ).all()
    return [AttentionRow(*r) for r in rows]


def my_bug_links(
    s: Session, org_id: UUID, project_ids: Sequence[UUID], user_id: UUID, since: datetime
) -> int:
    if not project_ids:
        return 0
    return int(
        s.execute(
            text(
                "SELECT count(DISTINCT reference_norm) FROM bug_links WHERE organization_id = :org"
                " AND project_id = ANY(:pids) AND created_by = :me AND created_at >= :since"
            ),
            {"org": org_id, "pids": list(project_ids), "me": user_id, "since": since},
        ).scalar_one()
    )
