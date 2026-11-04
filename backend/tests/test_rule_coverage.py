"""BR traceability gate (docs/08 §4): each BR of a completed milestone has at least one test."""

from __future__ import annotations

import re
from pathlib import Path

from tests.br_manifest import BR_MILESTONE, COMPLETED

TESTS = Path(__file__).resolve().parent
PRD = TESTS.parents[1] / "docs" / "01-PRD.md"


def _covered() -> set[str]:
    found: set[str] = set()
    for path in TESTS.rglob("test_*.py"):
        source = path.read_text(encoding="utf-8")
        found |= {f"BR-{n}" for n in re.findall(r"def test_br_(\d{2})_", source)}
        found |= set(re.findall(r'mark\.br\("(BR-\d{2})"\)', source))
    return found


def test_manifest_lists_every_business_rule_in_the_prd() -> None:
    prd_rules = set(re.findall(r"^\| (BR-\d{2}) \|", PRD.read_text(encoding="utf-8"), flags=re.M))
    assert prd_rules == set(BR_MILESTONE)


def test_every_rule_of_completed_milestones_is_tested() -> None:
    required = {br for br, milestone in BR_MILESTONE.items() if milestone in COMPLETED}
    missing = sorted(required - _covered())
    assert not missing, f"business rules without tests: {missing}"
