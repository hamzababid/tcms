"""Pure requirement-reference rules (docs/02 §10; ADR-024; BR-23).

Requirements live in the team's tool; Assay stores references, links them to cases and computes coverage
per release from the linked cases' latest results.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from tcms.core.errors import FieldError
from tcms.core.references import parse_many, reference_problem, title_problem, url_problem

MAX_PASTE: Final = 500

Status = Literal["not_covered", "failed", "blocked", "not_run", "passed"]
STATUSES: Final[tuple[Status, ...]] = ("not_covered", "failed", "blocked", "not_run", "passed")


def ref_problems(reference: str, url: str | None, title: str | None) -> list[FieldError]:
    return [p for p in (reference_problem(reference), url_problem(url), title_problem(title)) if p]


def paste_problems(text: str) -> tuple[list[str], list[FieldError]]:
    """ "Paste many" (D11): the references in order, or the first invalid one."""
    refs = parse_many(text)
    if not refs:
        return [], [FieldError("references", "field_required", "Enter one or more references")]
    if len(refs) > MAX_PASTE:
        return [], [FieldError("references", "too_many", f"At most {MAX_PASTE} at once")]
    for i, ref in enumerate(refs):
        problem = reference_problem(ref, f"references[{i}]")
        if problem:
            return [], [problem]
    return refs, []


def status_in_release(case_results: Sequence[str | None]) -> Status:
    """docs/02 §10.5 for one reference: `case_results` holds, for each linked non-archived case, the status
    of its latest final non-N/A attempt in the release (None when it has none)."""
    if not case_results:
        return "not_covered"
    if "failed" in case_results:
        return "failed"
    if "blocked" in case_results:
        return "blocked"
    if any(r is None or r == "skipped" for r in case_results):
        return "not_run"
    return "passed"


@dataclass(frozen=True)
class CoverageCounts:
    total: int
    covered: int
    not_covered: int
    passed: int
    failed: int
    blocked: int
    not_run: int


def coverage_counts(statuses: Iterable[Status]) -> CoverageCounts:
    by = dict.fromkeys(STATUSES, 0)
    for st in statuses:
        by[st] += 1
    total = sum(by.values())
    return CoverageCounts(
        total=total,
        covered=total - by["not_covered"],
        not_covered=by["not_covered"],
        passed=by["passed"],
        failed=by["failed"],
        blocked=by["blocked"],
        not_run=by["not_run"],
    )
