"""The single definition of execution metrics (docs/02 §11.2, docs/04 §8, ADR-013, BR-24).

Every screen and endpoint that shows execution numbers builds them here. Rates carry their numerator
and denominator, and are `None` when the denominator is 0 (never 0% or 100%).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

STATUSES = ("passed", "failed", "blocked", "skipped", "in_progress", "not_run", "not_applicable")


@dataclass(frozen=True)
class Rate:
    numerator: int
    denominator: int
    value: float | None

    @classmethod
    def of(cls, numerator: int, denominator: int) -> Rate:
        return cls(numerator, denominator, None if denominator == 0 else numerator / denominator)


@dataclass(frozen=True)
class ExecutionSummary:
    """docs/06 §5.7 over the runs in scope (non-superseded runs; the caller selects them)."""

    total: int
    not_applicable: int
    applicable: int
    passed: int
    failed: int
    blocked: int
    skipped: int
    in_progress: int
    not_run: int
    executed: int
    execution_progress: Rate
    pass_rate: Rate
    pass_rate_applicable: Rate
    failure_rate: Rate
    blocked_rate: Rate
    needs_retest: int

    @classmethod
    def from_counts(cls, counts: Mapping[str, int], *, needs_retest: int = 0) -> ExecutionSummary:
        """Counts by run status → summary. Unknown statuses count towards the total only."""
        n = {s: int(counts.get(s, 0)) for s in STATUSES}
        total = sum(int(v) for v in counts.values())
        applicable = total - n["not_applicable"]
        executed = n["passed"] + n["failed"] + n["blocked"]  # skipped and in progress are not executed
        return cls(
            total=total,
            not_applicable=n["not_applicable"],
            applicable=applicable,
            passed=n["passed"],
            failed=n["failed"],
            blocked=n["blocked"],
            skipped=n["skipped"],
            in_progress=n["in_progress"],
            not_run=n["not_run"],
            executed=executed,
            execution_progress=Rate.of(executed, applicable),
            pass_rate=Rate.of(n["passed"], executed),
            pass_rate_applicable=Rate.of(n["passed"], applicable),
            failure_rate=Rate.of(n["failed"], executed),
            blocked_rate=Rate.of(n["blocked"], applicable),
            needs_retest=needs_retest,
        )


@dataclass(frozen=True)
class RequirementCoverage:
    """docs/02 §10.5 coverage metrics over the requirement references in scope (BR-23, ADR-024)."""

    total: int
    covered: int
    not_covered: int
    passed: int
    failed: int
    blocked: int
    not_run: int
    coverage: Rate
    verified: Rate

    @classmethod
    def from_counts(
        cls, *, total: int, covered: int, passed: int, failed: int, blocked: int, not_run: int
    ) -> RequirementCoverage:
        return cls(
            total=total,
            covered=covered,
            not_covered=total - covered,
            passed=passed,
            failed=failed,
            blocked=blocked,
            not_run=not_run,
            coverage=Rate.of(covered, total),
            verified=Rate.of(passed, total),
        )
