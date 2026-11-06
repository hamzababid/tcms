"""Daily metric snapshots (FR-RPT-003, docs/02 §11.3, docs/03 §6.5, docs/04 §8; M7 D5).

A snapshot is the state of a scope (project, release or cycle) at the end of a UTC day, computed from
the attempts finished before midnight — so any past day can be computed again and the job is
idempotent (upsert on `ux_metric_snapshots__scope_day`). Counters replace the defect counters of the
first design (ADR-023): bug-link counts instead of open defects by severity.

Run status at a past instant = the latest final attempt finished before it (BR-08); runs created later
or superseded earlier are left out (BR-05). There is no "in progress" in the past: a run without a final
attempt is "not run".
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcms.core import clock, ids
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.uow import UnitOfWork
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule
from tcms.reporting import coverage

COUNTERS = (
    "total", "na", "passed", "failed", "blocked", "skipped", "not_run", "in_progress",
    "executed_on_day", "passed_on_day", "failed_on_day", "blocked_on_day",
    "bug_links_added", "bug_refs", "failed_without_bug",
    "req_total", "req_covered", "req_passed", "req_failed",
)  # fmt: skip

_RUNS = """
WITH rs AS (
  SELECT r.id, r.test_case_id, la.status AS st, la.id AS result_id
  FROM test_runs r
  JOIN test_cycles c ON c.id = r.cycle_id
  LEFT JOIN LATERAL (
    SELECT tr.id, tr.status::text AS status FROM test_results tr
    WHERE tr.run_id = r.id AND tr.state = 'final' AND tr.finished_at < :until
    ORDER BY tr.attempt_no DESC LIMIT 1
  ) la ON TRUE
  WHERE c.organization_id = :org AND c.project_id = :pid
    AND (CAST(:rid AS uuid) IS NULL OR c.release_id = :rid)
    AND (CAST(:cid AS uuid) IS NULL OR c.id = :cid)
    AND r.created_at < :until
    AND (r.superseded_by_run_id IS NULL OR r.superseded_at >= :until)
)
"""


def _bounds(day: date) -> tuple[datetime, datetime]:
    lo = datetime.combine(day, time.min, UTC)
    return lo, lo + timedelta(days=1)


def counters(
    s: Session, ctx: AccessContext, day: date, *, release_id: UUID | None = None, cycle_id: UUID | None = None
) -> dict[str, int]:
    lo, until = _bounds(day)
    p = {
        "org": ctx.principal.organization_id,
        "pid": ctx.pid,
        "rid": release_id,
        "cid": cycle_id,
        "until": until,
        "lo": lo,
    }
    out = dict.fromkeys(COUNTERS, 0)
    status_key = {"not_applicable": "na", None: "not_run"}
    for st, n in s.execute(text(_RUNS + "SELECT st, count(*) FROM rs GROUP BY st"), p).all():
        out[status_key.get(st, st)] += int(n)
        out["total"] += int(n)
    for st, n in s.execute(
        text(
            _RUNS + "SELECT tr.status::text, count(*) FROM test_results tr JOIN rs ON rs.id = tr.run_id"
            " WHERE tr.state = 'final' AND tr.finished_at >= :lo AND tr.finished_at < :until GROUP BY 1"
        ),
        p,
    ).all():
        if st in ("passed", "failed", "blocked"):
            out[f"{st}_on_day"] += int(n)
            out["executed_on_day"] += int(n)
    added, refs, without = s.execute(
        text(
            _RUNS
            + """
            SELECT
              (SELECT count(*) FROM bug_links b JOIN rs ON rs.id = b.run_id
                 WHERE b.created_at >= :lo AND b.created_at < :until),
              (SELECT count(DISTINCT b.reference_norm) FROM bug_links b JOIN rs ON rs.id = b.run_id
                 WHERE b.created_at < :until),
              (SELECT count(*) FROM rs WHERE rs.st = 'failed' AND NOT EXISTS (
                 SELECT 1 FROM bug_links b WHERE b.result_id = rs.result_id AND b.created_at < :until))
            """
        ),
        p,
    ).one()
    out.update(bug_links_added=int(added), bug_refs=int(refs), failed_without_bug=int(without))
    if cycle_id is None:
        rows = coverage.coverage_rows(s, ctx, release_id, until=until)
        out["req_total"] = len(rows)
        out["req_covered"] = sum(1 for r in rows if r.status != "not_covered")
        out["req_passed"] = sum(1 for r in rows if r.status == "passed")
        out["req_failed"] = sum(1 for r in rows if r.status == "failed")
    return out


def write(
    s: Session, ctx: AccessContext, day: date, *, release_id: UUID | None = None, cycle_id: UUID | None = None
) -> dict[str, int]:
    values = counters(s, ctx, day, release_id=release_id, cycle_id=cycle_id)
    import json

    s.execute(
        text(
            """
            INSERT INTO metric_snapshots (id, organization_id, project_id, release_id, cycle_id, day,
              counters)
            VALUES (:id, :org, :pid, :rid, :cid, :day, CAST(:counters AS jsonb))
            ON CONFLICT (project_id, coalesce(release_id, tcms_nil_uuid()), coalesce(cycle_id,
              tcms_nil_uuid()), day)
            DO UPDATE SET counters = EXCLUDED.counters, created_at = now()
            """
        ),
        {
            "id": ids.new_id(),
            "org": ctx.principal.organization_id,
            "pid": ctx.pid,
            "rid": release_id,
            "cid": cycle_id,
            "day": day,
            "counters": json.dumps(values),
        },
    )
    return values


def scopes(s: Session, ctx: AccessContext, day: date) -> list[tuple[UUID | None, UUID | None]]:
    """(release_id, cycle_id) scopes worth a snapshot for `day`: the project, open or recently released
    releases, and open or just-closed cycles."""
    _, until = _bounds(day)
    p = {"org": ctx.principal.organization_id, "pid": ctx.pid, "until": until}
    releases = s.execute(
        text(
            "SELECT id FROM releases WHERE organization_id = :org AND project_id = :pid AND status"
            " <> 'archived'"
            " AND (status <> 'released' OR released_at >= CAST(:until AS timestamptz) - interval '30 days')"
        ),
        p,
    ).scalars()
    cycles = s.execute(
        text(
            "SELECT id FROM test_cycles WHERE organization_id = :org AND project_id = :pid AND"
            " archived_at IS NULL"
            " AND created_at < :until"
            " AND (status <> 'closed' OR closed_at >= CAST(:until AS timestamptz) - interval '2 days')"
        ),
        p,
    ).scalars()
    return [(None, None), *((r, None) for r in releases), *((None, c) for c in cycles)]


def snapshot_project(s: Session, ctx: AccessContext, day: date) -> int:
    n = 0
    for release_id, cycle_id in scopes(s, ctx, day):
        write(s, ctx, day, release_id=release_id, cycle_id=cycle_id)
        n += 1
    return n


def stored(
    s: Session, ctx: AccessContext, *, release_id: UUID | None, lo: date, hi: date
) -> dict[date, dict[str, int]]:
    """Project-level (release_id None) or release-level snapshots for days in [lo, hi]."""
    rows = s.execute(
        text(
            "SELECT day, counters FROM metric_snapshots WHERE organization_id = :org AND project_id = :pid"
            " AND cycle_id IS NULL AND coalesce(release_id, tcms_nil_uuid()) = coalesce(CAST(:rid"
            " AS uuid), tcms_nil_uuid())"
            " AND day BETWEEN :lo AND :hi"
        ),
        {"org": ctx.principal.organization_id, "pid": ctx.pid, "rid": release_id, "lo": lo, "hi": hi},
    ).all()
    return {d: {k: int(c.get(k, 0)) for k in COUNTERS} for d, c in rows}


def at_or_before(s: Session, ctx: AccessContext, release_id: UUID, day: date) -> dict[str, int] | None:
    row = s.execute(
        text(
            "SELECT counters FROM metric_snapshots WHERE organization_id = :org AND project_id = :pid"
            " AND release_id = :rid AND cycle_id IS NULL AND day <= :day ORDER BY day DESC LIMIT 1"
        ),
        {"org": ctx.principal.organization_id, "pid": ctx.pid, "rid": release_id, "day": day},
    ).first()
    return {k: int(row[0].get(k, 0)) for k in COUNTERS} if row else None


def trend(
    s: Session, ctx: AccessContext, *, release_id: UUID | None, lo: date, hi: date
) -> list[tuple[date, dict[str, int]]]:
    """Snapshots for past days plus today computed live (docs/03 §6.5)."""
    today = clock.now().astimezone(UTC).date()
    days = stored(s, ctx, release_id=release_id, lo=lo, hi=min(hi, today - timedelta(days=1)))
    if lo <= today <= hi:
        days[today] = counters(s, ctx, today, release_id=release_id)
    return sorted(days.items())


def _project_ctx(org_id: UUID, project_id: UUID) -> AccessContext:
    return AccessContext.for_principal(
        Principal.system(org_id, "metrics.snapshot"),
        RequestMeta("job:metrics.snapshot"),
        project_id=project_id,
    )


@job_handler("metrics.snapshot")
def run_snapshot(job: JobInfo, uow: UnitOfWork) -> None:
    """Nightly (00:15 UTC): yesterday for every active project. With a payload `{project_id, day}`, one
    project and day (the "Refresh" button: today)."""
    d: dict[str, Any] = job.payload or {}
    s = uow.session
    if d.get("project_id"):
        org = s.execute(
            text("SELECT organization_id FROM projects WHERE id = :p"), {"p": d["project_id"]}
        ).scalar_one()
        targets = [(org, UUID(d["project_id"]))]
        day = date.fromisoformat(d["day"])
    else:
        targets = [
            (o, p)
            for o, p in s.execute(text("SELECT organization_id, id FROM projects WHERE status = 'active'"))
        ]
        day = clock.now().astimezone(UTC).date() - timedelta(days=1)
    for org_id, project_id in targets:
        snapshot_project(s, _project_ctx(org_id, project_id), day)


schedule("metrics.snapshot", period=timedelta(days=1), offset=timedelta(minutes=15))
