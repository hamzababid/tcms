"""Pure test design rules (docs/02 §5). Branch coverage gate: ≥ 95%."""

from __future__ import annotations

from itertools import product

import pytest

from tcms.core.enums import CaseFormat
from tcms.core.enums import CaseStatus as CS
from tcms.testdesign import rules
from tcms.testdesign.rules import Content, StepContent


def steps(*actions: str) -> tuple[StepContent, ...]:
    return tuple(StepContent(a, f"expect {a}") for a in actions)


BASE = Content(
    CaseFormat.steps,
    "Login with valid credentials",
    preconditions="User exists",
    steps=steps("Open", "Sign in"),
)


def test_normalize_md() -> None:
    assert rules.normalize_md(None) is None
    assert rules.normalize_md("  \n\n") is None
    assert rules.normalize_md("\r\n\nline one  \r\nline two\t\n\n") == "line one\nline two"
    assert rules.normalize_md("a\rb") == "a\nb"


def test_br_01_hash_ignores_formatting_noise() -> None:
    """AC-TD-13: identical content (after normalization) has the same hash, so no new version."""
    noisy = Content(
        CaseFormat.steps,
        "  Login with valid credentials ",
        preconditions="User exists  \r\n",
        steps=(StepContent("Open\n", "expect Open"), StepContent("Sign in", "expect Sign in  ")),
    )
    assert rules.content_hash(rules.normalize_content(noisy)) == rules.content_hash(
        rules.normalize_content(BASE)
    )


def test_br_01_hash_changes_with_any_content_field() -> None:
    from dataclasses import replace

    h = rules.content_hash(BASE)
    variants = [
        replace(BASE, title="Login with valid credentials!"),
        replace(BASE, description="d"),
        replace(BASE, test_data="t"),
        replace(BASE, expected_result="e"),
        replace(BASE, postconditions="p"),
        replace(BASE, steps=steps("Open", "Sign in", "Check")),
        replace(BASE, steps=(StepContent("Open", "different"), BASE.steps[1])),
        replace(BASE, steps=(StepContent("Open", "expect Open", data="x"), BASE.steps[1])),
        replace(BASE, format=CaseFormat.text, text_body="do it", steps=()),
    ]
    assert len({rules.content_hash(v) for v in variants} | {h}) == len(variants) + 1


def test_text_format_discards_steps() -> None:
    c = rules.normalize_content(
        Content(CaseFormat.text, "Free text", text_body="Do the thing", steps=steps("x"))
    )
    assert c.steps == ()
    assert rules.content_problems(c) == []


@pytest.mark.parametrize(
    ("content", "fields"),
    [
        (Content(CaseFormat.steps, "ab", steps=steps("a")), {"content.title"}),
        (Content(CaseFormat.steps, "Valid title"), {"content.steps"}),
        (Content(CaseFormat.text, "Valid title"), {"content.text_body"}),
        (Content(CaseFormat.steps, "Valid title", steps=(StepContent(""),)), {"content.steps[0].action"}),
        (
            Content(CaseFormat.steps, "Valid title", steps=(StepContent("a" * 5001),)),
            {"content.steps[0].action"},
        ),
        (
            Content(CaseFormat.steps, "Valid title", steps=(StepContent("a", "e" * 5001),)),
            {"content.steps[0].expected_result"},
        ),
        (
            Content(CaseFormat.steps, "Valid title", steps=(StepContent("a", None, "d" * 2001),)),
            {"content.steps[0].data"},
        ),
        (
            Content(CaseFormat.steps, "Valid title", steps=steps(*[str(i) for i in range(101)])),
            {"content.steps"},
        ),
        (
            Content(CaseFormat.steps, "Valid title", description="x" * 20_001, steps=steps("a")),
            {"content.description"},
        ),
        (BASE, set()),
    ],
)
def test_content_validation(content: Content, fields: set[str]) -> None:
    assert {p.field for p in rules.content_problems(content)} == fields


def test_status_for_new_case() -> None:
    assert rules.status_for_new_case(False) == rules.VersionOutcome(CS.approved, True)
    assert rules.status_for_new_case(True) == rules.VersionOutcome(CS.draft, False)


@pytest.mark.parametrize(
    ("current", "approval", "status", "auto"),
    [
        (CS.approved, False, CS.approved, True),
        (CS.deprecated, False, CS.deprecated, True),
        (CS.approved, True, CS.draft, False),  # AC-TD-20
        (CS.deprecated, True, CS.draft, False),
        (CS.draft, True, CS.draft, False),
        (CS.in_review, True, CS.in_review, False),  # reviewer sees the newest version
    ],
)
def test_br_17_status_after_new_version(current: CS, approval: bool, status: CS, auto: bool) -> None:
    assert rules.status_after_new_version(current, approval) == rules.VersionOutcome(status, auto)


ALLOWED = {
    ("submit", CS.draft, True),
    ("approve", CS.in_review, True),
    ("return", CS.in_review, True),
    *{("deprecate", CS.approved, a) for a in (True, False)},
    *{("archive", s, a) for s in CS if s is not CS.archived for a in (True, False)},
    *{("restore", s, a) for s in (CS.deprecated, CS.archived) for a in (True, False)},
}


def test_transition_matrix() -> None:
    for action, status, approval in product(
        ["submit", "approve", "return", "deprecate", "archive", "restore"], CS, (True, False)
    ):
        expected = (action, status, approval) in ALLOWED
        assert rules.transition_allowed(action, status, approval_required=approval) is expected, (
            action,
            status,
            approval,
        )  # type: ignore[arg-type]


def test_restore_status() -> None:
    assert rules.status_after_restore(approval_required=False, latest_is_approved=False) is CS.approved
    assert rules.status_after_restore(approval_required=True, latest_is_approved=True) is CS.approved
    assert rules.status_after_restore(approval_required=True, latest_is_approved=False) is CS.draft


def test_br_18_self_approval() -> None:
    assert rules.self_approval_blocked(author_id=1, approver_id=1, allow_self_approval=False)
    assert not rules.self_approval_blocked(author_id=1, approver_id=1, allow_self_approval=True)
    assert not rules.self_approval_blocked(author_id=1, approver_id=2, allow_self_approval=False)


def test_us_067_approval_toggle() -> None:
    assert rules.status_when_approval_toggled(CS.approved, now_required=True) == (
        CS.approved,
        False,
    )  # grandfathered
    assert rules.status_when_approval_toggled(CS.draft, now_required=False) == (CS.approved, True)
    assert rules.status_when_approval_toggled(CS.in_review, now_required=False) == (CS.approved, True)
    assert rules.status_when_approval_toggled(CS.deprecated, now_required=False) == (CS.deprecated, False)


def test_folder_names_and_paths() -> None:
    assert rules.folder_name_problem("Login") is None
    assert rules.folder_name_problem("") is not None
    assert rules.folder_name_problem("x" * 121) is not None
    assert rules.folder_name_problem("a/b") is not None
    assert rules.child_path(None, "f1") == "/f1/"
    assert rules.child_path("/f1/", "f2") == "/f1/f2/"


def test_folder_move_rules() -> None:
    """AC-TD-01 (cycle) and AC-TD-02 (depth of the whole subtree)."""
    a = {"source_path": "/a/", "source_depth": 1, "subtree_max_depth": 2}
    assert rules.move_problem(**a, target_path="/a/b/", target_depth=2) == "cycle"
    assert rules.move_problem(**a, target_path="/a/", target_depth=1) == "cycle"
    assert rules.move_problem(**a, target_path="/x/", target_depth=1) is None
    assert rules.move_problem(**a, target_path=None, target_depth=0) is None
    assert rules.move_problem(**a, target_path="/x/y/", target_depth=8) is None  # depths 9 and 10
    assert rules.move_problem(**a, target_path="/x/y/", target_depth=9) == "too_deep"  # would reach 11


def test_tags_keys_and_titles() -> None:
    assert rules.tag_problems(["smoke", "api-v2", "a.b_c"]) == []
    assert {p.code for p in rules.tag_problems(["Bad Tag"])} == {"invalid_tag"}
    assert {p.code for p in rules.tag_problems([f"t{i}" for i in range(21)])} == {"too_many"}
    assert rules.automation_key_problems(["a.b"]) == []
    assert {p.code for p in rules.automation_key_problems(["", "x" * 501])} == {"invalid_length"}
    assert {p.code for p in rules.automation_key_problems(["a", "a"])} == {"duplicate"}
    assert rules.duplicate_title("Login", same_folder=True) == "Copy of Login"
    assert rules.duplicate_title("Login", same_folder=False) == "Login"
    assert len(rules.duplicate_title("x" * 255, same_folder=True)) == 255
    assert rules.ordered_pair("b", "a") == ("a", "b")
    assert rules.ordered_pair("a", "b") == ("a", "b")


def test_compare_aligns_steps_by_position() -> None:
    """AC-TD-12."""
    from dataclasses import replace

    newer = replace(
        BASE,
        title="Login (valid)",
        steps=(BASE.steps[0], StepContent("Sign in", "changed"), StepContent("Check")),
    )
    fields, step_diffs = rules.compare(BASE, newer)
    assert {f.field for f in fields if f.changed} == {"title"}
    assert [s.change for s in step_diffs] == ["unchanged", "changed", "added"]
    _, back = rules.compare(newer, BASE)
    assert [s.change for s in back] == ["unchanged", "changed", "removed"]
