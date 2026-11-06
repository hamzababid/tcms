"""Release and plan readiness (FR-RPT-006, docs/02 §11.4, docs/04 §8; M7 D1/D2).

D1 (product owner, 2026-11-06): each plan's exit rules are evaluated over that plan's cycles in the
release, and its coverage rules over the plan's requirement references (listed on the plan or linked
to its cases). The release is ready when every plan with rules is ready. When no plan of the release
has rules, the default rules run over every cycle of the release.

D2: an undefined actual value (zero denominator, no runs in scope) is not met. Evaluation is pure
(`evaluate`); `plan_readiness` / `release_readiness` gather the inputs through `reporting.queries`
and `reporting.coverage`, so the numbers match the dashboards (TCMS-115).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcms.core import clock
from tcms.core.context import AccessContext
from tcms.reporting import coverage, queries
from tcms.reporting.metrics import ExecutionSummary, Rate, RequirementCoverage

# docs/02 §11.4 defaults (thresholds as stored: fractions and whole numbers).
DEFAULT_RULES: Final[tuple[dict[str, Any], ...]] = (
    {"type": "min_execution_progress", "threshold": 1.0},
    {"type": "max_failed", "threshold": 0},
    {"type": "min_pass_rate_applicable", "threshold": 0.95},
    {"type": "min_requirement_coverage", "threshold": 0.9},
)
COVERAGE_RULES: Final = frozenset({"min_requirement_coverage", "min_requirements_verified"})


@dataclass(frozen=True)
class PlanRef:
    id: UUID
    key: str
    name: str


@dataclass(frozen=True)
class RuleResult:
    type: str
    threshold: float
    params: dict[str, Any]
    actual: Rate | None  # percentage rules and tag_fully_executed
    count: int | None  # count rules
    met: bool
    note: str | None = None
    plan: PlanRef | None = None


@dataclass(frozen=True)
class Inputs:
    summary: ExecutionSummary
    coverage: RequirementCoverage
    tag_summaries: dict[str, ExecutionSummary] = field(default_factory=dict)


def _percent(kind: str, inputs: Inputs) -> Rate:
    s, c = inputs.summary, inputs.coverage
    return {
        "min_execution_progress": s.execution_progress,
        "min_pass_rate": s.pass_rate,
        "min_pass_rate_applicable": s.pass_rate_applicable,
        "min_requirement_coverage": c.coverage,
        "min_requirements_verified": c.verified,
    }[kind]


def evaluate(rule: dict[str, Any], inputs: Inputs, plan: PlanRef | None = None) -> RuleResult:
    """One rule → met / not met with its actual value (D2)."""
    kind = str(rule["type"])
    threshold = float(rule.get("threshold") or 0)
    params = dict(rule.get("params") or {})
    s = inputs.summary
    if kind in ("max_failed", "max_blocked"):
        n = s.failed if kind == "max_failed" else s.blocked
        if s.applicable == 0:
            return RuleResult(kind, threshold, params, None, n, False, "No runs in scope", plan)
        return RuleResult(kind, threshold, params, None, n, n <= threshold, None, plan)
    if kind == "tag_fully_executed":
        tag = str(params.get("tag") or "")
        ts = inputs.tag_summaries.get(tag)
        if ts is None or ts.applicable == 0:
            return RuleResult(
                kind, threshold, params, Rate.of(0, 0), None, False, f"No runs of cases tagged {tag}", plan
            )
        return RuleResult(
            kind, threshold, params, ts.execution_progress, None, ts.executed == ts.applicable, None, plan
        )
    rate = _percent(kind, inputs)
    if rate.value is None:
        note = "No requirements in scope" if kind in COVERAGE_RULES else "No runs in scope"
        return RuleResult(kind, threshold, params, rate, None, False, note, plan)
    # Compare on the counts so 0.95 × 20 = 19 is met exactly (no float drift).
    met = rate.numerator >= threshold * rate.denominator - 1e-9
    return RuleResult(kind, threshold, params, rate, None, met, None, plan)


@dataclass(frozen=True)
class Readiness:
    ready: bool
    rules: list[RuleResult]
    uses_defaults: bool
    summary: ExecutionSummary
    coverage: RequirementCoverage
    evaluated_at: datetime
    plans: list[tuple[PlanRef, bool]]


@dataclass(frozen=True)
class _Plan:
    ref: PlanRef
    release_id: UUID | None
    rules: list[dict[str, Any]]


def _plans(
    s: Session, ctx: AccessContext, *, release_id: UUID | None = None, plan_id: UUID | None = None
) -> list[_Plan]:
    where = "project_id = :pid AND organization_id = :org AND status <> 'archived'"
    params: dict[str, Any] = {"pid": ctx.pid, "org": ctx.principal.organization_id}
    if release_id is not None:
        where += " AND release_id = :rid"
        params["rid"] = release_id
    if plan_id is not None:
        where = "project_id = :pid AND organization_id = :org AND id = :plan"
        params["plan"] = plan_id
    rows = s.execute(
        text(f"SELECT id, key, name, release_id, exit_rules FROM test_plans WHERE {where} ORDER BY key_num"),
        params,
    ).all()
    return [_Plan(PlanRef(r[0], r[1], r[2]), r[3], list(r[4] or [])) for r in rows]


def _plan_ref_ids(s: Session, ctx: AccessContext, plan_id: UUID) -> list[UUID]:
    """References a plan must cover: listed on the plan or linked to its cases (not archived)."""
    return list(
        s.execute(
            text(
                """
                SELECT q.id FROM requirement_refs q
                WHERE q.project_id = :pid AND q.archived_at IS NULL AND (
                  EXISTS (SELECT 1 FROM plan_requirement_refs pr WHERE pr.ref_id = q.id
                    AND pr.plan_id = :plan)
                  OR EXISTS (SELECT 1 FROM requirement_ref_cases rc
                             JOIN test_plan_cases pc ON pc.test_case_id = rc.test_case_id
                             WHERE rc.ref_id = q.id AND pc.plan_id = :plan))
                """
            ),
            {"pid": ctx.pid, "plan": plan_id},
        ).scalars()
    )


def _inputs(
    s: Session,
    ctx: AccessContext,
    scope: queries.Scope,
    release_id: UUID | None,
    ref_ids: list[UUID] | None,
    rules: list[dict[str, Any]],
) -> Inputs:
    summary = queries.summary(s, ctx, scope)
    cov = coverage.summary(coverage.coverage_rows(s, ctx, release_id, ref_ids))
    tags = {str((r.get("params") or {}).get("tag")) for r in rules if r.get("type") == "tag_fully_executed"}
    tag_summaries = {t: queries.summary(s, ctx, _with_tag(scope, t)) for t in tags if t}
    return Inputs(summary, cov, tag_summaries)


def _with_tag(scope: queries.Scope, tag: str) -> queries.Scope:
    return replace(scope, tag=tag)


def _plan_results(
    s: Session, ctx: AccessContext, p: _Plan, release_id: UUID | None
) -> tuple[list[RuleResult], Inputs]:
    scope = queries.Scope(release_id=release_id, plan_id=p.ref.id)
    inputs = _inputs(s, ctx, scope, release_id, _plan_ref_ids(s, ctx, p.ref.id), p.rules)
    return [evaluate(r, inputs, p.ref) for r in p.rules], inputs


def plan_readiness(s: Session, ctx: AccessContext, plan_id: UUID) -> Readiness | None:
    """The plan Overview (L25): the plan's own rules over its cycles (in its release when it has one)."""
    found = _plans(s, ctx, plan_id=plan_id)
    if not found:
        return None
    p = found[0]
    results, inputs = _plan_results(s, ctx, p, p.release_id)
    ready = bool(results) and all(r.met for r in results)
    return Readiness(ready, results, False, inputs.summary, inputs.coverage, clock.now(), [(p.ref, ready)])


def release_readiness(s: Session, ctx: AccessContext, release_id: UUID) -> Readiness:
    """D1: every plan with rules over its own cycles; defaults over the whole release otherwise."""
    plans = [p for p in _plans(s, ctx, release_id=release_id) if p.rules]
    release_scope = queries.Scope(release_id=release_id)
    summary = queries.summary(s, ctx, release_scope)
    cov = coverage.summary(coverage.coverage_rows(s, ctx, release_id))
    if not plans:
        rules = [dict(r) for r in DEFAULT_RULES]
        if cov.total == 0:  # the default coverage rule applies only when the release has references
            rules = [r for r in rules if r["type"] not in COVERAGE_RULES]
        inputs = _inputs(s, ctx, release_scope, release_id, None, rules)
        defaults = [evaluate(r, inputs) for r in rules]
        return Readiness(all(r.met for r in defaults), defaults, True, summary, cov, clock.now(), [])
    results: list[RuleResult] = []
    per_plan: list[tuple[PlanRef, bool]] = []
    for p in plans:
        plan_results, _ = _plan_results(s, ctx, p, release_id)
        results += plan_results
        per_plan.append((p.ref, all(r.met for r in plan_results)))
    return Readiness(all(ok for _, ok in per_plan), results, False, summary, cov, clock.now(), per_plan)


def as_json(r: Readiness) -> dict[str, Any]:
    """The decision snapshot (docs/02 §11.4, docs/06 §5.9): every rule result and the metrics, frozen."""

    def rate(x: Rate | None) -> dict[str, Any] | None:
        return (
            None if x is None else {"numerator": x.numerator, "denominator": x.denominator, "value": x.value}
        )

    s, c = r.summary, r.coverage
    return {
        "ready": r.ready,
        "uses_defaults": r.uses_defaults,
        "evaluated_at": r.evaluated_at.isoformat(),
        "rules": [
            {
                "type": x.type,
                "threshold": x.threshold,
                "params": x.params,
                "actual": rate(x.actual),
                "count": x.count,
                "met": x.met,
                "note": x.note,
                "plan": {"id": str(x.plan.id), "key": x.plan.key, "name": x.plan.name} if x.plan else None,
            }
            for x in r.rules
        ],
        "plans": [{"id": str(p.id), "key": p.key, "name": p.name, "ready": ok} for p, ok in r.plans],
        "summary": {
            **{
                k: getattr(s, k)
                for k in (
                    "total",
                    "not_applicable",
                    "applicable",
                    "passed",
                    "failed",
                    "blocked",
                    "skipped",
                    "in_progress",
                    "not_run",
                    "executed",
                    "needs_retest",
                )
            },
            **{
                k: rate(getattr(s, k))
                for k in (
                    "execution_progress",
                    "pass_rate",
                    "pass_rate_applicable",
                    "failure_rate",
                    "blocked_rate",
                )
            },
        },
        "coverage": {
            **{
                k: getattr(c, k)
                for k in ("total", "covered", "not_covered", "passed", "failed", "blocked", "not_run")
            },
            "coverage": rate(c.coverage),
            "verified": rate(c.verified),
        },
    }
