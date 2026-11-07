"""Import mapping, value normalisation and the import plan (docs/02 §15.1; M8 D4, D6)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from tcms.imports import fields as F
from tcms.imports.cases import Context, Options, build_plan, folder_path


def test_automap_uses_labels_and_synonyms_once() -> None:
    m = F.automap("test_case", ["Test Case ID", "Name", "Expected", "Expected Result", "Steps", "Notes"])
    assert m == {
        "Test Case ID": "key", "Name": "title", "Expected": "step_expected", "Expected Result": "",
        "Steps": "step_action", "Notes": "",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        ("priority", "High", "high"),
        ("priority", "P1", "high"),
        ("priority", "Blocker", "critical"),
        ("type", "End to end", "end_to_end"),
        ("automation_status", "To be automated", "to_be_automated"),
        ("priority", "Sometimes", None),
    ],
)
def test_choice(field: str, raw: str, expected: str | None) -> None:
    choices = {f.key: f.choices for f in F.CASE_FIELDS}[field]
    assert F.choice(field, raw, choices) == expected


def test_value_map_wins() -> None:
    assert F.choice("priority", "Sev-A", ("critical", "high"), {"Sev-A": "critical"}) == "critical"


def test_numbered_cells() -> None:
    assert F.split_numbered("1. Open\n2) Click save\n3. Check") == ["Open", "Click save", "Check"]
    assert F.split_numbered("Just one step") == ["Just one step"]
    assert F.split_numbered("") == []
    assert F.join_numbered(["a", None]) == "1. a\n2."


def test_folder_path() -> None:
    assert folder_path(" Web / Auth /Login ") == ("Web", "Auth", "Login")


def _ctx() -> Context:
    return Context(
        existing={}, folders={("suite",): uuid4()}, archived_folders=set(), members={}, importer=uuid4()
    )


def test_rows_group_into_cases_and_steps() -> None:
    header = ["Title", "Step", "Expected", "Folder"]
    rows = [
        ["Login", "Open", "Shown", "Suite"],
        ["", "Type", "", ""],
        ["", "", "", ""],
        ["Logout", "Click out", "Gone", "Suite/New"],
    ]
    plan = build_plan(header, rows, F.automap("test_case", header), {}, Options(), _ctx())
    assert [c.action for c in plan.cases] == ["create", "create"]
    assert [len(c.content.steps) for c in plan.cases if c.content] == [2, 1]
    assert plan.folders_to_create == [("Suite", "New")]


def test_file_level_problems() -> None:
    plan = build_plan(["Notes"], [["x"]], {"Notes": ""}, {}, Options(), _ctx())
    assert [p.code for p in plan.file_problems] == ["field_required"]
    orphan = build_plan(
        ["Title", "Step"], [["", "Lonely"]], {"Title": "title", "Step": "step_action"}, {}, Options(), _ctx()
    )
    assert [p.code for p in orphan.file_problems] == ["step_without_case"]


def test_case_level_problems() -> None:
    header = ["Key", "Title", "Step", "Folder", "Minutes"]
    m = {
        "Key": "key",
        "Title": "title",
        "Step": "step_action",
        "Folder": "folder",
        "Minutes": "estimated_minutes",
    }
    rows = [
        ["X-1", "Fine title", "Do", "Suite", "5"],
        ["X-1", "Again", "Do", "Suite", ""],
        ["", "No", "Do", "Suite", ""],
        ["", "Too long minutes", "Do", "Suite", "2000"],
        ["", "Deep", "Do", "/".join(f"L{i}" for i in range(11)), ""],
    ]
    plan = build_plan(header, rows, m, {}, Options(), _ctx())
    codes = [[p.code for p in c.problems] for c in plan.cases]
    assert codes[0] == []
    assert codes[1] == ["duplicate_key"]
    assert codes[2] == ["invalid_length"], "title shorter than 3"
    assert codes[3] == ["invalid_value"]
    assert codes[4] == ["folder_too_deep"]
    assert [w.code for w in plan.cases[0].warnings] == ["unknown_key"]
    assert not plan.committable(skip_error_rows=False)
    assert plan.committable(skip_error_rows=True)
