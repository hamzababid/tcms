"""Pure identity rules (docs/02 §3; NFR-SEC-01/03/04). Branch coverage gate: ≥ 95%."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tcms.core.permissions import ORG_ADMIN_PERMISSIONS, PROJECT_PERMISSIONS, READ_ONLY_PERMISSIONS
from tcms.core.policy import OrgPolicy
from tcms.identity import rules
from tcms.identity.rules import MfaGate, SessionState, TokenRestriction

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
POLICY = OrgPolicy()


@pytest.mark.parametrize(
    ("password", "email", "codes"),
    [
        ("short", None, {"too_short"}),
        ("x" * 129, None, {"too_long"}),
        ("sana.malik@acme.test", "Sana.Malik@acme.test", {"equals_email"}),
        ("sana.malik.local", "sana.malik.local@acme.test", {"equals_email"}),
        ("passwordpassword", None, {"too_common"}),
        ("Correct-Horse-Battery-9", "x@y.z", set()),
    ],
)
def test_password_policy(password: str, email: str | None, codes: set[str]) -> None:
    assert {p.code for p in rules.password_problems(password, email)} == codes


@pytest.mark.parametrize(
    ("email", "ok"),
    [
        ("a@b.co", True),
        ("first.last@acme.test", True),
        ("no-at-sign", False),
        ("a@b", False),
        ("a b@c.de", False),
        ("x" * 250 + "@a.bc", False),
    ],
)
def test_email_problem(email: str, ok: bool) -> None:
    assert (rules.email_problem(email) is None) is ok


def test_lockout_rules() -> None:
    assert not rules.should_lock(9)
    assert rules.should_lock(10)
    assert not rules.is_locked(None, NOW)
    assert not rules.is_locked(NOW - timedelta(seconds=1), NOW)
    assert rules.is_locked(NOW + timedelta(minutes=5), NOW)
    assert rules.minutes_left(NOW + timedelta(minutes=14, seconds=10), NOW) == 15
    assert rules.minutes_left(NOW + timedelta(seconds=5), NOW) == 1


def _state(**kw: object) -> SessionState:
    base: dict[str, object] = {
        "revoked_at": None,
        "expires_at": NOW + timedelta(hours=1),
        "last_seen_at": NOW,
        "policy": POLICY,
        "now": NOW,
    }
    return rules.session_state(**{**base, **kw})  # type: ignore[arg-type]


def test_session_state() -> None:
    assert _state() is SessionState.active
    assert _state(revoked_at=NOW) is SessionState.revoked
    assert _state(expires_at=NOW) is SessionState.expired
    assert _state(last_seen_at=NOW - timedelta(minutes=31)) is SessionState.expired
    assert _state(last_seen_at=NOW - timedelta(minutes=30)) is SessionState.active
    assert rules.absolute_expiry(NOW, OrgPolicy(session_absolute_hours=2)) == NOW + timedelta(hours=2)
    assert rules.needs_touch(NOW - timedelta(minutes=1), NOW)
    assert not rules.needs_touch(NOW - timedelta(seconds=59), NOW)


def test_mfa_requirement_and_gate() -> None:
    assert rules.mfa_required(is_org_admin=True, policy=POLICY)
    assert not rules.mfa_required(is_org_admin=False, policy=POLICY)
    assert rules.mfa_required(is_org_admin=False, policy=OrgPolicy(mfa_required_for_all=True))
    assert rules.mfa_gate(enrolled=True, session_verified=False, required=False) is MfaGate.verify
    assert rules.mfa_gate(enrolled=True, session_verified=True, required=True) is MfaGate.ok
    assert rules.mfa_gate(enrolled=False, session_verified=False, required=True) is MfaGate.enroll
    assert rules.mfa_gate(enrolled=False, session_verified=False, required=False) is MfaGate.ok


def test_project_permissions() -> None:
    viewer = frozenset({"project.view", "data.export"})
    assert (
        rules.project_permissions(is_org_admin=True, role_permissions=None, token=None) == PROJECT_PERMISSIONS
    )
    assert rules.project_permissions(is_org_admin=False, role_permissions=viewer, token=None) == viewer
    assert rules.project_permissions(is_org_admin=False, role_permissions=None, token=None) is None
    read = TokenRestriction("read", None)
    assert (
        rules.project_permissions(is_org_admin=True, role_permissions=None, token=read)
        == PROJECT_PERMISSIONS & READ_ONLY_PERMISSIONS
    )
    rw = TokenRestriction("read_write", None)
    assert rules.project_permissions(is_org_admin=False, role_permissions=viewer, token=rw) == viewer


def test_org_permissions() -> None:
    assert rules.org_permissions(
        is_org_admin=True, is_qa_manager_somewhere=False, policy=POLICY, token=None
    ) == (ORG_ADMIN_PERMISSIONS - PROJECT_PERMISSIONS)
    assert rules.org_permissions(
        is_org_admin=False, is_qa_manager_somewhere=True, policy=POLICY, token=None
    ) == {"project.create"}
    off = OrgPolicy(qa_managers_can_create_projects=False)
    assert (
        rules.org_permissions(is_org_admin=False, is_qa_manager_somewhere=True, policy=off, token=None)
        == frozenset()
    )
    assert (
        rules.org_permissions(is_org_admin=False, is_qa_manager_somewhere=False, policy=POLICY, token=None)
        == frozenset()
    )
    read = TokenRestriction("read", None)
    assert rules.org_permissions(
        is_org_admin=True, is_qa_manager_somewhere=False, policy=POLICY, token=read
    ) == {
        "org.audit.view",
        "org.reports.view",
    }


def test_token_expiry() -> None:
    assert rules.token_expiry(NOW, 90) == NOW + timedelta(days=90)
    for days in (0, 366):
        with pytest.raises(ValueError, match="1–365"):
            rules.token_expiry(NOW, days)
