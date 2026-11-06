"""Readiness rule evaluation (docs/02 §11.4, M7 D2), repository metrics and export escaping (TCMS-117)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tcms.reporting import exports, readiness
from tcms.reporting.metrics import ExecutionSummary, RepositoryMetrics, RequirementCoverage
from tcms.reporting.reports import Column


def _inputs(
    counts: dict[str, int],
    *,
    cov: tuple[int, int, int] = (0, 0, 0),
    tags: dict[str, dict[str, int]] | None = None,
) -> readiness.Inputs:
    total, covered, passed = cov
    return readiness.Inputs(
        ExecutionSummary.from_counts(counts),
        RequirementCoverage.from_counts(
            total=total, covered=covered, passed=passed, failed=0, blocked=0, not_run=0
        ),
        {k: ExecutionSummary.from_counts(v) for k, v in (tags or {}).items()},
    )


@pytest.mark.parametrize(
    ("rule", "counts", "met"),
    [
        ({"type": "min_pass_rate", "threshold": 0.95}, {"passed": 19, "failed": 1}, True),  # exactly 95 %
        ({"type": "min_pass_rate", "threshold": 0.95}, {"passed": 18, "failed": 2}, False),
        ({"type": "min_execution_progress", "threshold": 1.0}, {"passed": 2, "not_run": 1}, False),
        ({"type": "min_execution_progress", "threshold": 1.0}, {"passed": 2, "not_applicable": 3}, True),
        ({"type": "min_pass_rate_applicable", "threshold": 0.5}, {"passed": 1, "not_run": 1}, True),
        ({"type": "max_failed", "threshold": 0}, {"passed": 3}, True),
        ({"type": "max_failed", "threshold": 1}, {"failed": 2}, False),
        ({"type": "max_blocked", "threshold": 1}, {"blocked": 1, "passed": 1}, True),
    ],
)
def test_ac_rel_01_rule_evaluation(rule: dict[str, object], counts: dict[str, int], met: bool) -> None:
    assert readiness.evaluate(rule, _inputs(counts)).met is met


def test_d2_undefined_values_are_not_met() -> None:
    nothing = _inputs({})
    for kind in ("min_pass_rate", "min_execution_progress", "max_failed"):
        r = readiness.evaluate({"type": kind, "threshold": 0}, nothing)
        assert (r.met, r.note) == (False, "No runs in scope")
    cov = readiness.evaluate({"type": "min_requirement_coverage", "threshold": 0.9}, _inputs({"passed": 1}))
    assert (cov.met, cov.note) == (False, "No requirements in scope")
    only_na = readiness.evaluate({"type": "min_pass_rate", "threshold": 0.5}, _inputs({"not_applicable": 2}))
    assert only_na.met is False


def test_coverage_and_tag_rules() -> None:
    i = _inputs({"passed": 1}, cov=(10, 9, 7), tags={"smoke": {"passed": 2, "skipped": 1}})
    assert readiness.evaluate({"type": "min_requirement_coverage", "threshold": 0.9}, i).met is True
    assert readiness.evaluate({"type": "min_requirements_verified", "threshold": 0.8}, i).met is False
    smoke = readiness.evaluate({"type": "tag_fully_executed", "threshold": 0, "params": {"tag": "smoke"}}, i)
    assert (smoke.met, smoke.actual.numerator, smoke.actual.denominator) == (False, 2, 3)  # type: ignore[union-attr]
    missing = readiness.evaluate({"type": "tag_fully_executed", "threshold": 0, "params": {"tag": "ui"}}, i)
    assert (missing.met, missing.note) == (False, "No runs of cases tagged ui")


def test_snapshot_json_is_complete() -> None:
    r = readiness.Readiness(
        ready=False,
        rules=[readiness.evaluate({"type": "max_failed", "threshold": 0}, _inputs({"failed": 1}))],
        uses_defaults=True,
        summary=ExecutionSummary.from_counts({"failed": 1}),
        coverage=RequirementCoverage.from_counts(
            total=0, covered=0, passed=0, failed=0, blocked=0, not_run=0
        ),
        evaluated_at=datetime(2026, 11, 6, tzinfo=UTC),
        plans=[],
    )
    j = readiness.as_json(r)
    assert j["rules"][0] == {
        "type": "max_failed", "threshold": 0.0, "params": {}, "actual": None, "count": 1, "met": False,
        "note": None, "plan": None,
    }  # fmt: skip
    assert j["summary"]["pass_rate"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert j["coverage"]["coverage"]["value"] is None


def test_repository_metrics_ignore_archived_cases() -> None:
    m = RepositoryMetrics.from_counts(
        by_status={"approved": 3, "draft": 1, "archived": 5},
        by_type={"functional": 4},
        by_automation={"automated": 1, "manual": 3},
        folders=2,
        plans_by_status={"active": 1},
    )
    assert (m.total_cases, m.approved.value, m.automation_coverage.numerator) == (4, 0.75, 1)


@pytest.mark.parametrize("value", ["=1+1", "+1", "-2", "@SUM(A1)", "\tx", "\rx"])
def test_ac_rpt_05_formula_cells_are_prefixed(value: str) -> None:
    assert exports.safe(value) == "'" + value
    out = exports.write_csv([Column("v", "V")], [{"v": value}]).decode("utf-8-sig")
    assert ("'" + value) in out


def test_plain_values_pass_through() -> None:
    assert exports.safe("Login works") == "Login works"
    assert exports.safe(-2) == -2, "numbers are not text"
