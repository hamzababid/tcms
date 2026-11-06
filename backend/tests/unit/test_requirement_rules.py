"""Requirement-reference rules (docs/02 §10.5, BR-23, ADR-024): status per release, paste parsing, order."""

from __future__ import annotations

import pytest

from tcms.core.references import natural_key, parse_many
from tcms.reporting.metrics import RequirementCoverage
from tcms.requirements import rules


@pytest.mark.br("BR-23")
@pytest.mark.parametrize(
    ("results", "status"),
    [
        ([], "not_covered"),  # AC-REQ-03 (only archived cases → no linked cases)
        (["passed", None], "not_run"),  # AC-REQ-01
        (["passed", "failed"], "failed"),  # AC-REQ-02
        (["blocked", "failed"], "failed"),
        (["blocked", None], "blocked"),
        (["passed", "skipped"], "not_run"),
        (["passed"], "passed"),  # AC-REQ-04: the later passing retest is the latest result
        (["passed", "passed"], "passed"),
    ],
)
def test_br_23_status_in_release(results: list[str | None], status: str) -> None:
    assert rules.status_in_release(results) == status


def test_coverage_counts_and_rates() -> None:
    counts = rules.coverage_counts(["passed", "failed", "not_covered", "not_run", "passed", "blocked"])
    assert (counts.total, counts.covered, counts.not_covered) == (6, 5, 1)
    assert (counts.passed, counts.failed, counts.blocked, counts.not_run) == (2, 1, 1, 1)
    cov = RequirementCoverage.from_counts(total=6, covered=5, passed=2, failed=1, blocked=1, not_run=1)
    assert (cov.coverage.numerator, cov.coverage.denominator) == (5, 6)
    assert cov.verified.value == pytest.approx(2 / 6)
    empty = RequirementCoverage.from_counts(total=0, covered=0, passed=0, failed=0, blocked=0, not_run=0)
    assert empty.coverage.value is None  # BR-24: no denominator, no rate


def test_paste_many() -> None:
    assert parse_many("SPK-120, spk-120;SPK-121\n  AB#7  ") == ["SPK-120", "SPK-121", "AB#7"]
    refs, problems = rules.paste_problems("SPK-1 SPK-2")
    assert (refs, problems) == (["SPK-1", "SPK-2"], [])
    assert rules.paste_problems("  ,  ")[1][0].code == "field_required"
    assert rules.paste_problems(" ".join(f"R-{i}" for i in range(501)))[1][0].code == "too_many"
    too_long = rules.paste_problems("x" * 101)[1][0]
    assert (too_long.field, too_long.code) == ("references[0]", "invalid_format")


def test_natural_order() -> None:
    refs = ["SPK-10", "SPK-2", "AB-1", "spk-3"]
    assert sorted(refs, key=natural_key) == ["AB-1", "SPK-2", "spk-3", "SPK-10"]


def test_ref_problems() -> None:
    assert rules.ref_problems("SPK-1", "https://x.test/1", "Login") == []
    fields = [p.field for p in rules.ref_problems("SPK 1", "ftp://x", "t" * 300)]
    assert fields == ["reference", "url", "title"]
