"""Pure workspace rules (docs/02 §4; BR-16, BR-27). Branch coverage gate: ≥ 95%."""

from __future__ import annotations

from itertools import product
from typing import Any

import pytest

from tcms.core.enums import ReleaseStatus as RS
from tcms.core.policy import OrgPolicy
from tcms.workspace import rules


@pytest.mark.parametrize(
    ("raw", "key", "ok"),
    [
        (" spark ", "SPARK", True),
        ("S", "S", False),
        ("1AB", "1AB", False),
        ("AB_C", "AB_C", False),
        ("A" * 11, "A" * 11, False),
        ("HELIOS2", "HELIOS2", True),
    ],
)
def test_br_27_key_normalisation_and_format(raw: str, key: str, ok: bool) -> None:
    normalized = rules.normalize_project_key(raw)
    assert normalized == key
    assert (rules.project_key_problem(normalized) is None) is ok


def test_br_16_human_key_format() -> None:
    assert rules.human_key("SPARK", "test_case", 1042) == "SPARK-TC-1042"
    assert [rules.human_key("P", e, 1) for e in rules.KEY_ENTITIES] == [
        "P-TC-1",
        "P-PL-1",
        "P-CY-1",
        "P-D-1",
        "P-R-1",
    ]


@pytest.mark.parametrize(
    ("patch", "fields"),
    [
        ({"session_idle_minutes": 14}, {"settings.session_idle_minutes"}),
        ({"session_idle_minutes": 481}, {"settings.session_idle_minutes"}),
        ({"session_idle_minutes": True}, {"settings.session_idle_minutes"}),
        ({"session_absolute_hours": "12"}, {"settings.session_absolute_hours"}),
        ({"default_attachment_max_mb": 101}, {"settings.default_attachment_max_mb"}),
        ({"audit_retention_years": 0}, {"settings.audit_retention_years"}),
        ({"mfa_required_for_all": "yes"}, {"settings.mfa_required_for_all"}),
        ({"unknown": 1}, {"settings.unknown"}),
        ({"session_idle_minutes": 15, "session_absolute_hours": 24, "mfa_required_for_all": True}, set()),
    ],
)
def test_org_settings_validation(patch: dict[str, Any], fields: set[str]) -> None:
    assert {p.field for p in rules.org_settings_problems(patch)} == fields


def test_org_settings_merge_keeps_defaults() -> None:
    merged = rules.merged_org_settings({"session_idle_minutes": 60}, {"audit_retention_years": 5})
    assert merged["session_idle_minutes"] == 60
    assert merged["audit_retention_years"] == 5
    assert merged["qa_managers_can_create_projects"] is True


@pytest.mark.parametrize(
    ("patch", "fields"),
    [
        ({"approval_required": 1}, {"settings.approval_required"}),
        ({"report_module_depth": 0}, {"settings.report_module_depth"}),
        ({"report_module_depth": True}, {"settings.report_module_depth"}),
        ({"attachment_max_mb": 21}, {"settings.attachment_max_mb"}),
        ({"attachment_max_mb": 0}, {"settings.attachment_max_mb"}),
        ({"attachment_max_mb": False}, {"settings.attachment_max_mb"}),
        ({"nope": True}, {"settings.nope"}),
        ({"approval_required": True, "report_module_depth": 5, "attachment_max_mb": 20}, set()),
    ],
)
def test_project_settings_validation_k9(patch: dict[str, Any], fields: set[str]) -> None:
    """Attachment limit is capped by the organization value (review K9); here 20 MB."""
    policy = OrgPolicy(default_attachment_max_mb=20)
    assert {p.field for p in rules.project_settings_problems(patch, policy)} == fields


def test_project_settings_defaults_follow_org() -> None:
    assert rules.default_project_settings(OrgPolicy(default_attachment_max_mb=40))["attachment_max_mb"] == 40
    assert rules.merged_project_settings({"approval_required": True}, {})["allow_self_approval"] is False


ALLOWED = {
    (RS.planned, RS.active),
    (RS.planned, RS.archived),
    (RS.active, RS.released),
    (RS.active, RS.archived),
    (RS.released, RS.active),
    (RS.released, RS.archived),
}


def test_release_transition_matrix() -> None:
    """docs/02 §4.4, all 4 × 4 pairs (TCMS-024)."""
    for a, b in product(RS, RS):
        assert rules.release_transition_allowed(a, b) is ((a, b) in ALLOWED), (a, b)
    assert rules.allowed_release_targets(RS.archived) == frozenset()
