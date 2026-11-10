"""Requirement coverage per release (docs/02 §10.5, docs/04 §7; BR-23; ADR-024).

Reporting reads every module's tables through SQL (docs/03 §5). The status rules come from
`requirements.rules`; the rates from `reporting.metrics` (ADR-013).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.references import natural_key
from tcms.reporting import cache as _cache  # noqa: F401  (session memo reset)
from tcms.reporting.metrics import RequirementCoverage
from tcms.requirements import rules

# A reference is in scope for release R when a plan of R lists it, or a linked case ran in a cycle of R
# (D3, Q1 = a). Without a release every non-archived reference is in scope.
_SCOPE_SQL = """
SELECT q.id FROM requirement_refs q
WHERE q.organization_id = :org AND q.project_id = :pid AND q.archived_at IS NULL
  AND (CAST(:rid AS uuid) IS NULL
       OR EXISTS (SELECT 1 FROM plan_requirement_refs pr JOIN test_plans p ON p.id = pr.plan_id
                  WHERE pr.ref_id = q.id AND p.release_id = :rid)
       OR EXISTS (SELECT 1 FROM requirement_ref_cases rc
                  JOIN test_runs r ON r.test_case_id = rc.test_case_id
                  JOIN test_cycles c ON c.id = r.cycle_id
                  WHERE rc.ref_id = q.id AND c.release_id = :rid))
"""

# Latest final, non-N/A attempt per case among non-superseded runs of cycles in the release (§10.5).
_LATEST_SQL = """
SELECT DISTINCT ON (r.test_case_id)
       r.test_case_id, tr.status::text, tr.finished_at, tr.executed_by, r.id AS run_id, c.key AS cycle_key
FROM test_results tr
JOIN test_runs r ON r.id = tr.run_id
JOIN test_cycles c ON c.id = r.cycle_id
WHERE c.organization_id = :org AND c.project_id = :pid
  AND (CAST(:rid AS uuid) IS NULL OR c.release_id = :rid)
  AND r.superseded_by_run_id IS NULL
  AND tr.state = 'final' AND tr.status <> 'not_applicable'
  AND (CAST(:until AS timestamptz) IS NULL OR tr.finished_at < :until)
  AND r.test_case_id = ANY(:case_ids)
ORDER BY r.test_case_id, tr.finished_at DESC, tr.id DESC
"""

_LINKS_SQL = """
SELECT rc.ref_id, tc.id, tc.key, tc.title
FROM requirement_ref_cases rc JOIN test_cases tc ON tc.id = rc.test_case_id
WHERE rc.project_id = :pid AND rc.ref_id = ANY(:ref_ids) AND tc.status <> 'archived'
"""

_REFS_SQL = """
SELECT id, reference, url, title FROM requirement_refs WHERE project_id = :pid AND id = ANY(:ref_ids)
"""


@dataclass(frozen=True)
class CaseLatest:
    status: str
    finished_at: datetime
    executed_by: UUID | None
    run_id: UUID
    cycle_key: str


@dataclass(frozen=True)
class CaseCoverage:
    case_id: UUID
    key: str
    title: str
    latest: CaseLatest | None


@dataclass(frozen=True)
class RefCoverage:
    ref_id: UUID
    reference: str
    url: str | None
    title: str | None
    status: rules.Status
    cases: list[CaseCoverage]


def scope_ids(s: Session, ctx: AccessContext, release_id: UUID | None) -> list[UUID]:
    params = {"org": ctx.principal.organization_id, "pid": ctx.pid, "rid": release_id}
    return list(s.execute(text(_SCOPE_SQL), params).scalars())


def coverage_rows(
    s: Session,
    ctx: AccessContext,
    release_id: UUID | None,
    ref_ids: list[UUID] | None = None,
    *,
    until: datetime | None = None,
) -> list[RefCoverage]:
    """Every reference in scope (or the given ones) with its cases' latest results and its status.
    `until` reads results finished before that instant (daily snapshots, D5). Remembered for the rest of
    the session: a dashboard asks for the same release several times (M8c P3)."""
    memo: dict[object, list[RefCoverage]] = s.info.setdefault("coverage_rows", {})
    key = (ctx.principal.organization_id, ctx.pid, release_id, tuple(ref_ids) if ref_ids else None, until)
    if key not in memo:
        memo[key] = _coverage_rows(s, ctx, release_id, ref_ids, until=until)
    return memo[key]


def _coverage_rows(
    s: Session,
    ctx: AccessContext,
    release_id: UUID | None,
    ref_ids: list[UUID] | None,
    *,
    until: datetime | None,
) -> list[RefCoverage]:
    ids = scope_ids(s, ctx, release_id) if ref_ids is None else ref_ids
    if not ids:
        return []
    base = {"org": ctx.principal.organization_id, "pid": ctx.pid, "rid": release_id, "until": until}
    refs = {r[0]: r for r in s.execute(text(_REFS_SQL), {"pid": ctx.pid, "ref_ids": ids}).all()}
    links: dict[UUID, list[tuple[UUID, str, str]]] = {}
    for ref_id, case_id, key, title in s.execute(text(_LINKS_SQL), {"pid": ctx.pid, "ref_ids": ids}).all():
        links.setdefault(ref_id, []).append((case_id, key, title))
    case_ids = sorted({c[0] for cases in links.values() for c in cases})
    latest = {
        row[0]: CaseLatest(row[1], row[2], row[3], row[4], row[5])
        for row in (s.execute(text(_LATEST_SQL), {**base, "case_ids": case_ids}).all() if case_ids else [])
    }
    out = []
    for ref_id in ids:
        ref = refs.get(ref_id)
        if ref is None:
            continue
        cases = sorted(
            (CaseCoverage(cid, key, title, latest.get(cid)) for cid, key, title in links.get(ref_id, [])),
            key=lambda c: natural_key(c.key),
        )
        status = rules.status_in_release([c.latest.status if c.latest else None for c in cases])
        out.append(RefCoverage(ref_id, ref[1], ref[2], ref[3], status, cases))
    return sorted(out, key=lambda r: natural_key(r.reference))


def summary(rows: list[RefCoverage]) -> RequirementCoverage:
    counts = rules.coverage_counts(r.status for r in rows)
    return RequirementCoverage.from_counts(
        total=counts.total,
        covered=counts.covered,
        passed=counts.passed,
        failed=counts.failed,
        blocked=counts.blocked,
        not_run=counts.not_run,
    )
