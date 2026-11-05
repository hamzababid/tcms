"""ExecutionSummary (docs/02 §11.2, docs/06 §5.7): formulas and undefined rates (BR-24)."""

from __future__ import annotations

from tcms.reporting.metrics import ExecutionSummary, Rate


def test_br_24_summary_matches_the_docs_example() -> None:
    """docs/06 §5.7 example: 250 runs, 5 N/A, 180/20/5/4/6/30."""
    s = ExecutionSummary.from_counts(
        {
            "passed": 180,
            "failed": 20,
            "blocked": 5,
            "skipped": 4,
            "in_progress": 6,
            "not_run": 30,
            "not_applicable": 5,
        },
        needs_retest=3,
    )
    assert (s.total, s.applicable, s.executed) == (250, 245, 205)
    assert s.execution_progress == Rate(205, 245, 205 / 245)
    assert s.pass_rate == Rate(180, 205, 180 / 205)
    assert s.pass_rate_applicable == Rate(180, 245, 180 / 245)
    assert s.failure_rate == Rate(20, 205, 20 / 205)
    assert s.blocked_rate == Rate(5, 245, 5 / 245)
    assert s.needs_retest == 3


def test_br_24_rates_are_undefined_when_the_denominator_is_zero() -> None:
    empty = ExecutionSummary.from_counts({})
    assert empty.total == 0
    assert empty.execution_progress.value is None
    assert empty.pass_rate.value is None
    not_run = ExecutionSummary.from_counts({"not_run": 12})
    assert not_run.execution_progress == Rate(0, 12, 0.0)
    assert not_run.pass_rate == Rate(0, 0, None)  # nothing executed: "—", never 0%


def test_skipped_and_in_progress_are_not_executed() -> None:
    s = ExecutionSummary.from_counts({"skipped": 2, "in_progress": 3, "passed": 1})
    assert s.executed == 1
    assert s.pass_rate == Rate(1, 1, 1.0)
