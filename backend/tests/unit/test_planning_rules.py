"""Pure planning rules (docs/02 §6.1–6.3, §11.4). Branch coverage gate: ≥ 95%."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from tcms.core.enums import PlanStatus as PS
from tcms.planning import rules


@pytest.mark.parametrize(
    ("name", "ok"), [("ab", False), (" abc ", True), ("x" * 150, True), ("x" * 151, False)]
)
def test_name_length(name: str, ok: bool) -> None:
    assert (rules.name_problem(name) is None) is ok


@pytest.mark.parametrize(("raw", "out"), [(None, None), ("", None), ("  \r\n ", None), (" a\r\nb ", "a\nb")])
def test_normalize_md(raw: str | None, out: str | None) -> None:
    assert rules.normalize_md(raw) == out


@pytest.mark.parametrize(
    ("start", "end", "ok"),
    [
        (None, None, True),
        (date(2026, 11, 3), None, True),
        (None, date(2026, 11, 3), True),
        (date(2026, 11, 3), date(2026, 11, 14), True),
        (date(2026, 11, 14), date(2026, 11, 3), False),
    ],
)
def test_end_on_or_after_start(start: date | None, end: date | None, ok: bool) -> None:
    assert (rules.date_order_problem(start, end) is None) is ok


RISK = {"description": "Feed unstable", "impact": "high", "mitigation": None}


@pytest.mark.parametrize(
    ("risks", "code"),
    [
        ([], None),
        ([RISK], None),
        ([RISK] * 51, "too_many"),
        ([{**RISK, "impact": "severe"}], "invalid_impact"),
        ([{**RISK, "description": "   "}], "field_required"),
        ([{"impact": "low"}], "field_required"),
    ],
)
def test_risks(risks: list[dict[str, Any]], code: str | None) -> None:
    problem = rules.risks_problem(risks)
    assert (problem.code if problem else None) == code


@pytest.mark.parametrize(
    ("rule_list", "field", "code"),
    [
        ([], None, None),
        ([{"type": "min_execution_progress", "threshold": 1.0}], None, None),
        ([{"type": "min_pass_rate", "threshold": 0}], None, None),
        ([{"type": "max_blocked", "threshold": 3}], None, None),
        ([{"type": "max_failed", "threshold": 0}], None, None),
        ([{"type": "tag_fully_executed", "threshold": 1, "params": {"tag": "smoke"}}], None, None),
        ([{"type": "min_pass_rate", "threshold": 1}] * 21, "exit_rules", "too_many"),
        ([{"type": "nope", "threshold": 1}], "exit_rules[0].type", "invalid_value"),
        ([{"type": "min_pass_rate", "threshold": 95}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "min_pass_rate", "threshold": -0.1}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "min_pass_rate", "threshold": "1"}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "max_blocked", "threshold": 1.5}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "max_blocked", "threshold": -1}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "max_blocked", "threshold": None}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "max_failed", "threshold": 2.5}], "exit_rules[0].threshold", "invalid_range"),
        ([{"type": "max_open_defects", "threshold": 0}], "exit_rules[0].type", "invalid_value"),
        (
            [{"type": "tag_fully_executed", "threshold": 1, "params": {"tag": "  "}}],
            "exit_rules[0].params.tag",
            "field_required",
        ),
        (
            [{"type": "max_blocked", "threshold": 0}, {"type": "tag_fully_executed", "threshold": 1}],
            "exit_rules[1].params.tag",
            "field_required",
        ),
    ],
)
def test_exit_rules(rule_list: list[dict[str, Any]], field: str | None, code: str | None) -> None:
    problem = rules.exit_rules_problem(rule_list)
    assert ((problem.field, problem.code) if problem else (None, None)) == (field, code)


def test_plan_status_machine() -> None:
    """draft → active → completed, one step back while not archived; archived only via archive."""
    allowed = {
        (PS.draft, PS.active),
        (PS.active, PS.draft),
        (PS.active, PS.completed),
        (PS.completed, PS.active),
    }
    for current in PS:
        for target in PS:
            expected = current == target or (current, target) in allowed
            assert rules.plan_transition_allowed(current, target) is expected
        assert rules.allowed_plan_targets(current) == {t for c, t in allowed if c == current}
