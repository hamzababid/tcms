"""The six standard reports (FR-RPT-004, docs/02 §11.5; columns per M7 D9).

Each report declares its columns once; the same rows feed the paginated JSON, CSV and XLSX (D8).
Run-based reports are built on `queries.runs_sql`, so their numbers match the dashboards (TCMS-115).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.reporting import coverage, queries
from tcms.reporting.queries import Scope

Kind = Literal["text", "int", "datetime", "date"]


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: Kind = "text"


@dataclass(frozen=True)
class Filters:
    scope: Scope
    status: tuple[str, ...] = ()
    assignee_id: UUID | None = None
    case_status: tuple[str, ...] = ()
    case_type: tuple[str, ...] = ()
    priority: tuple[str, ...] = ()


Rows = Callable[[Session, AccessContext, Filters, int, int], tuple[list[dict[str, Any]], int]]


@dataclass(frozen=True)
class Report:
    name: str
    title: str
    columns: tuple[Column, ...]
    filters: frozenset[str]
    rows: Rows


_FOLDER_PATH = (
    "(SELECT string_agg(a.name, ' / ' ORDER BY a.depth) FROM folders a"
    " WHERE a.id = ANY(CAST(string_to_array(btrim(f.path, '/'), '/') AS uuid[])))"
)
_USER = "(SELECT u.display_name FROM users u WHERE u.id = {col})"


def _page(
    s: Session, sql: str, params: dict[str, Any], limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    total = int(s.execute(text(f"SELECT count(*) FROM ({sql}) x"), params).scalar_one())
    rows = s.execute(text(f"{sql} LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset})
    return [dict(r._mapping) for r in rows], total


def _runs(ctx: AccessContext, f: Filters) -> tuple[str, dict[str, Any], list[str]]:
    sql, params = queries.runs_sql(ctx, f.scope)
    extra: list[str] = []
    if f.status:
        extra.append("rs.status = ANY(:status)")
        params["status"] = list(f.status)
    if f.assignee_id:
        extra.append("rs.assignee_id = :assignee")
        params["assignee"] = f.assignee_id
    return sql, params, extra


def _where(extra: list[str]) -> str:
    return (" WHERE " + " AND ".join(extra)) if extra else ""


# -- cycle execution -------------------------------------------------------------------------------


def _cycle_execution(
    s: Session, ctx: AccessContext, f: Filters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    runs, params, extra = _runs(ctx, f)
    sql = f"""
        WITH rs AS ({runs})
        SELECT c.key AS cycle, tc.key AS case_key, tc.title, {_FOLDER_PATH} AS folder,
          tc.priority::text AS priority,
               {_USER.format(col="rs.assignee_id")} AS assignee, rs.status,
                 {_USER.format(col="rs.executed_by")} AS executed_by,
               rs.finished_at, v.version_no AS version, e.name AS environment, coalesce(lr.build,
                 c.build) AS build,
               (SELECT string_agg(DISTINCT b.reference, ', ') FROM bug_links b WHERE b.run_id = rs.id) AS bugs
        FROM rs
        JOIN test_runs r ON r.id = rs.id
        JOIN test_cycles c ON c.id = rs.cycle_id
        JOIN test_cases tc ON tc.id = rs.test_case_id
        JOIN folders f ON f.id = tc.folder_id
        JOIN test_case_versions v ON v.id = r.test_case_version_id
        JOIN environments e ON e.id = c.environment_id
        LEFT JOIN test_results lr ON lr.id = rs.latest_result_id
        {_where(extra)}
        ORDER BY c.key_num, r.position, tc.key_num
    """
    return _page(s, sql, params, limit, offset)


# -- results history -------------------------------------------------------------------------------


def _results_history(
    s: Session, ctx: AccessContext, f: Filters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    lo, hi = f.scope.window()
    runs, params, _ = _runs(ctx, replace(f, scope=replace(f.scope, tester_id=None)))
    extra = ["tr.state = 'final'"]
    if lo:
        extra.append("tr.finished_at >= :lo")
        params["lo"] = lo
    if hi:
        extra.append("tr.finished_at < :hi")
        params["hi"] = hi
    if f.scope.tester_id:
        extra.append("tr.executed_by = :tester_by")
        params["tester_by"] = f.scope.tester_id
    if f.status:
        extra.append("tr.status::text = ANY(:status)")
        params["status"] = list(f.status)
    sql = f"""
        WITH rs AS ({runs})
        SELECT tr.finished_at, c.key AS cycle, tc.key AS case_key, tc.title, tr.attempt_no AS attempt,
               tr.status::text AS status, {_USER.format(col="tr.executed_by")} AS executed_by,
                 e.name AS environment,
               tr.build, (SELECT string_agg(DISTINCT b.reference, ',
                 ') FROM bug_links b WHERE b.result_id = tr.id) AS bugs
        FROM test_results tr
        JOIN rs ON rs.id = tr.run_id
        JOIN test_cycles c ON c.id = rs.cycle_id
        JOIN test_cases tc ON tc.id = rs.test_case_id
        JOIN environments e ON e.id = tr.environment_id
        {_where(extra)}
        ORDER BY tr.finished_at DESC, tr.id DESC
    """
    return _page(s, sql, params, limit, offset)


# -- bug links -------------------------------------------------------------------------------------


def _bug_links(
    s: Session, ctx: AccessContext, f: Filters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    lo, hi = f.scope.window()
    runs, params, _ = _runs(ctx, f)
    sc = f.scope
    whole_project = (
        sc.release_id is None and sc.cycle_ids is None and sc.plan_id is None and sc.environment_id is None
    )
    params.update(lo=lo, hi=hi, all=whole_project, module=sc.module_folder_id)
    sql = f"""
        WITH rs AS ({runs})
        SELECT b.reference, b.url, b.title, tc.key AS case_key, c.key AS cycle, r.status::text AS run_status,
               st.position AS step, {_USER.format(col="b.created_by")} AS linked_by, b.created_at AS linked_at
        FROM bug_links b
        JOIN test_cases tc ON tc.id = b.test_case_id
        JOIN folders f ON f.id = tc.folder_id
        LEFT JOIN rs ON rs.id = b.run_id
        LEFT JOIN test_runs r ON r.id = b.run_id
        LEFT JOIN test_cycles c ON c.id = r.cycle_id
        LEFT JOIN test_case_steps st ON st.id = b.step_id
        WHERE b.organization_id = :org AND b.project_id = :pid
          AND (rs.id IS NOT NULL OR (b.run_id IS NULL AND CAST(:all AS boolean)
               AND (CAST(:module AS uuid) IS NULL
                    OR f.path LIKE (SELECT m.path FROM folders m WHERE m.id = :module) || '%')))
          AND (CAST(:lo AS timestamptz) IS NULL OR b.created_at >= :lo)
          AND (CAST(:hi AS timestamptz) IS NULL OR b.created_at < :hi)
        ORDER BY b.created_at DESC, b.id DESC
    """
    return _page(s, sql, params, limit, offset)


# -- traceability ----------------------------------------------------------------------------------


def _traceability(
    s: Session, ctx: AccessContext, f: Filters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    rows = coverage.coverage_rows(s, ctx, f.scope.release_id)
    if f.status:
        rows = [r for r in rows if r.status in f.status]
    users: dict[UUID, str] = {}
    ids_ = {c.latest.executed_by for r in rows for c in r.cases if c.latest and c.latest.executed_by}
    if ids_:
        users = dict(
            s.execute(
                text("SELECT id, display_name FROM users WHERE id = ANY(:ids)"), {"ids": list(ids_)}
            ).all()
        )
    case_ids = sorted({c.case_id for r in rows for c in r.cases})
    run_ids = None
    if f.scope.release_id is not None:
        run_ids = set(
            s.execute(
                text(
                    "SELECT r.id FROM test_runs r JOIN test_cycles c ON c.id = r.cycle_id"
                    " WHERE c.project_id = :pid AND c.release_id = :rid"
                ),
                {"pid": ctx.pid, "rid": f.scope.release_id},
            ).scalars()
        )
    bugs: dict[UUID, set[str]] = {}
    if case_ids:
        for case_id, ref, run_id in s.execute(
            text(
                "SELECT test_case_id, reference, run_id FROM bug_links WHERE project_id = :pid AND"
                " test_case_id = ANY(:ids)"
            ),
            {"pid": ctx.pid, "ids": case_ids},
        ).all():
            if run_id is None or run_ids is None or run_id in run_ids:
                bugs.setdefault(case_id, set()).add(ref)
    out: list[dict[str, Any]] = []
    for r in rows:
        base = {
            "requirement": r.reference,
            "requirement_title": r.title,
            "url": r.url,
            "status_in_release": r.status,
        }
        if not r.cases:
            out.append(
                {
                    **base,
                    "case_key": None,
                    "case_title": None,
                    "latest_status": None,
                    "cycle": None,
                    "finished_at": None,
                    "executed_by": None,
                    "bugs": None,
                }
            )
        for c in r.cases:
            latest = c.latest
            out.append(
                {
                    **base,
                    "case_key": c.key,
                    "case_title": c.title,
                    "latest_status": latest.status if latest else None,
                    "cycle": latest.cycle_key if latest else None,
                    "finished_at": latest.finished_at if latest else None,
                    "executed_by": users.get(latest.executed_by) if latest and latest.executed_by else None,
                    "bugs": ", ".join(sorted(bugs.get(c.case_id, ()))) or None,
                }
            )
    return out[offset : offset + limit], len(out)


# -- tester activity -------------------------------------------------------------------------------


def _tester_activity(
    s: Session, ctx: AccessContext, f: Filters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    lo, hi = f.scope.window()
    runs, params, _ = _runs(ctx, replace(f, scope=replace(f.scope, tester_id=None)))
    params.update(lo=lo, hi=hi, tester_by=f.scope.tester_id)
    sql = f"""
        WITH rs AS ({runs})
        SELECT (tr.finished_at AT TIME ZONE 'UTC')::date AS day,
          {_USER.format(col="tr.executed_by")} AS tester,
               count(*) FILTER (WHERE tr.status IN ('passed', 'failed', 'blocked')) AS executed,
               count(*) FILTER (WHERE tr.status = 'passed') AS passed,
               count(*) FILTER (WHERE tr.status = 'failed') AS failed,
               count(*) FILTER (WHERE tr.status = 'blocked') AS blocked
        FROM test_results tr JOIN rs ON rs.id = tr.run_id
        WHERE tr.state = 'final' AND tr.executed_by IS NOT NULL
          AND (CAST(:lo AS timestamptz) IS NULL OR tr.finished_at >= :lo)
          AND (CAST(:hi AS timestamptz) IS NULL OR tr.finished_at < :hi)
          AND (CAST(:tester_by AS uuid) IS NULL OR tr.executed_by = :tester_by)
        GROUP BY 1, tr.executed_by
        ORDER BY 1 DESC, 2
    """
    return _page(s, sql, params, limit, offset)


# -- test case inventory ---------------------------------------------------------------------------


def _case_inventory(
    s: Session, ctx: AccessContext, f: Filters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    sc = f.scope
    params: dict[str, Any] = {"org": ctx.principal.organization_id, "pid": ctx.pid, "rid": sc.release_id}
    where = ["tc.organization_id = :org", "tc.project_id = :pid"]
    if f.case_status:
        where.append("tc.status::text = ANY(:case_status)")
        params["case_status"] = list(f.case_status)
    else:
        where.append("tc.status <> 'archived'")
    if f.case_type:
        where.append("tc.type::text = ANY(:case_type)")
        params["case_type"] = list(f.case_type)
    if f.priority:
        where.append("tc.priority::text = ANY(:priority)")
        params["priority"] = list(f.priority)
    if sc.module_folder_id:
        where.append(
            "f.path LIKE (SELECT m.path FROM folders m WHERE m.id = :module AND m.project_id = :pid) || '%'"
        )
        params["module"] = sc.module_folder_id
    if sc.tag:
        where.append(
            "EXISTS (SELECT 1 FROM test_case_tags ct JOIN tags t ON t.id = ct.tag_id"
            " WHERE ct.test_case_id = tc.id AND t.name = :tag)"
        )
        params["tag"] = sc.tag
    cond = " AND ".join(where)
    total = int(
        s.execute(
            text(f"SELECT count(*) FROM test_cases tc JOIN folders f ON f.id = tc.folder_id WHERE {cond}"),
            params,
        ).scalar_one()
    )
    # Page first, then the per-case lookups (latest result, tags, references) for that page only.
    sql = f"""
        WITH pg AS (
          SELECT tc.* FROM test_cases tc JOIN folders f ON f.id = tc.folder_id
          WHERE {cond} ORDER BY tc.key_num LIMIT :limit OFFSET :offset
        )
        SELECT tc.key AS case_key, tc.title, {_FOLDER_PATH} AS folder, tc.type::text AS type,
               tc.priority::text AS priority, tc.status::text AS status, tc.latest_version_no AS version,
               {_USER.format(col="tc.owner_id")} AS owner, tc.automation_status::text AS automation_status,
               (SELECT string_agg(t.name, ', ' ORDER BY t.name) FROM test_case_tags ct
                 JOIN tags t ON t.id = ct.tag_id WHERE ct.test_case_id = tc.id) AS tags,
               (SELECT string_agg(q.reference, ', ' ORDER BY q.reference_norm) FROM requirement_ref_cases rc
                 JOIN requirement_refs q ON q.id = rc.ref_id WHERE rc.test_case_id = tc.id) AS requirements,
               lt.status AS latest_status, lt.finished_at AS latest_finished_at
        FROM pg tc
        JOIN folders f ON f.id = tc.folder_id
        LEFT JOIN LATERAL (
          SELECT tr.status::text AS status, tr.finished_at FROM test_results tr
          JOIN test_runs r ON r.id = tr.run_id JOIN test_cycles c ON c.id = r.cycle_id
          WHERE r.test_case_id = tc.id AND r.superseded_by_run_id IS NULL AND tr.state = 'final'
            AND (CAST(:rid AS uuid) IS NULL OR c.release_id = :rid)
          ORDER BY tr.finished_at DESC, tr.id DESC LIMIT 1
        ) lt ON TRUE
        ORDER BY tc.key_num
    """
    rows = s.execute(text(sql), {**params, "limit": limit, "offset": offset})
    return [dict(r._mapping) for r in rows], total


RUN_FILTERS = frozenset(
    {"release_id", "cycle_ids", "environment_id", "module_folder_id", "tester_id", "status", "assignee_id"}
)
DATED = frozenset({"date_from", "date_to"})

REPORTS: dict[str, Report] = {
    r.name: r
    for r in (
        Report(
            "cycle-execution",
            "Cycle execution",
            (
                Column("cycle", "Cycle"),
                Column("case_key", "Case"),
                Column("title", "Title"),
                Column("folder", "Folder"),
                Column("priority", "Priority"),
                Column("assignee", "Assignee"),
                Column("status", "Status"),
                Column("executed_by", "Executed by"),
                Column("finished_at", "Finished at", "datetime"),
                Column("version", "Version", "int"),
                Column("environment", "Environment"),
                Column("build", "Build"),
                Column("bugs", "Bugs"),
            ),
            RUN_FILTERS,
            _cycle_execution,
        ),
        Report(
            "results-history",
            "Results history",
            (
                Column("finished_at", "Finished at", "datetime"),
                Column("cycle", "Cycle"),
                Column("case_key", "Case"),
                Column("title", "Title"),
                Column("attempt", "Attempt", "int"),
                Column("status", "Status"),
                Column("executed_by", "Executed by"),
                Column("environment", "Environment"),
                Column("build", "Build"),
                Column("bugs", "Bugs"),
            ),
            RUN_FILTERS | DATED,
            _results_history,
        ),
        Report(
            "bug-links",
            "Bug links",
            (
                Column("reference", "Bug"),
                Column("url", "Link"),
                Column("title", "Title"),
                Column("case_key", "Case"),
                Column("cycle", "Cycle"),
                Column("run_status", "Run status"),
                Column("step", "Step", "int"),
                Column("linked_by", "Linked by"),
                Column("linked_at", "Linked at", "datetime"),
            ),
            frozenset({"release_id", "cycle_ids", "environment_id", "module_folder_id"}) | DATED,
            _bug_links,
        ),
        Report(
            "traceability",
            "Traceability",
            (
                Column("requirement", "Requirement"),
                Column("requirement_title", "Requirement title"),
                Column("url", "Link"),
                Column("status_in_release", "Status in release"),
                Column("case_key", "Case"),
                Column("case_title", "Case title"),
                Column("latest_status", "Latest result"),
                Column("cycle", "Cycle"),
                Column("finished_at", "Finished at", "datetime"),
                Column("executed_by", "Executed by"),
                Column("bugs", "Bugs"),
            ),
            frozenset({"release_id", "status"}),
            _traceability,
        ),
        Report(
            "tester-activity",
            "Tester activity",
            (
                Column("day", "Day", "date"),
                Column("tester", "Tester"),
                Column("executed", "Executed", "int"),
                Column("passed", "Passed", "int"),
                Column("failed", "Failed", "int"),
                Column("blocked", "Blocked", "int"),
            ),
            frozenset({"release_id", "cycle_ids", "environment_id", "tester_id"}) | DATED,
            _tester_activity,
        ),
        Report(
            "case-inventory",
            "Test case inventory",
            (
                Column("case_key", "Case"),
                Column("title", "Title"),
                Column("folder", "Folder"),
                Column("type", "Type"),
                Column("priority", "Priority"),
                Column("status", "Status"),
                Column("version", "Version", "int"),
                Column("owner", "Owner"),
                Column("automation_status", "Automation"),
                Column("tags", "Tags"),
                Column("requirements", "Requirements"),
                Column("latest_status", "Latest result"),
                Column("latest_finished_at", "Latest result at", "datetime"),
            ),
            frozenset({"release_id", "module_folder_id", "tag", "case_status", "case_type", "priority"}),
            _case_inventory,
        ),
    )
}


def iterate(
    s: Session, ctx: AccessContext, report: Report, f: Filters, *, batch: int = 2000
) -> Iterator[dict[str, Any]]:
    """Every row in order, in pages (exports)."""
    offset = 0
    while True:
        rows, _ = report.rows(s, ctx, f, batch, offset)
        yield from rows
        if len(rows) < batch:
            return
        offset += batch


def cell(value: Any) -> Any:
    """JSON/CSV-friendly value."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
