"""Authentication and access (docs/08 §15.1: TCMS-002…011, 014; docs/02 §3 AC-AUTH-*)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pyotp
import pytest
from sqlalchemy import text

from tcms.core import clock
from tcms.main import create_app
from tests.world import PASSWORD, ApiClient, World, make_settings

pytestmark = pytest.mark.integration


def _audit(world: World, action: str, entity_id: object) -> int:
    with world.factory() as s:
        return int(
            s.execute(
                text("SELECT count(*) FROM audit_events WHERE action = :a AND entity_id = :e"),
                {"a": action, "e": entity_id},
            ).scalar_one()
        )


def _last_email(world: World, to: str) -> dict[str, Any]:
    with world.factory() as s:
        payload = s.execute(
            text(
                "SELECT payload FROM jobs WHERE type = 'email.send' AND payload->>'to' = :to ORDER BY created_at DESC LIMIT 1"
            ),
            {"to": to},
        ).scalar_one()
    return dict(payload)


def _login(c: ApiClient, email: str, password: str = PASSWORD) -> Any:
    return c.post("/api/v1/auth/login", json={"email": email, "password": password})


# -- TCMS-002 / AC-AUTH-02 ------------------------------------------------------------------------


def test_tcms_002_unknown_email_and_wrong_password_take_similar_time(world: World) -> None:
    """Timing within 50 ms on average: both paths run one Argon2 verification and similar queries."""
    import statistics
    import time

    org = world.org()
    user = world.user(org, "Timing")
    c = world.client()
    _login(c, "warmup@nowhere.test", "x" * 12)
    known: list[float] = []
    unknown: list[float] = []
    for _ in range(8):  # interleaved so load and warm-up affect both equally
        for email, bucket in ((user.email, known), ("ghost@nowhere.test", unknown)):
            start = time.perf_counter()
            assert _login(c, email, "not-the-password-1").status_code == 401
            bucket.append(time.perf_counter() - start)
    assert abs(statistics.median(known) - statistics.median(unknown)) < 0.05


# -- TCMS-003 / AC-AUTH-03 ------------------------------------------------------------------------


def test_tcms_003_account_locks_after_ten_failures(world: World) -> None:
    org = world.org()
    user = world.user(org, "Locked")
    c = world.client()
    for _ in range(10):
        assert _login(c, user.email, "wrong-password-xyz").status_code == 401
    r = _login(c, user.email)
    assert r.status_code == 423
    assert r.json()["code"] == "account_locked"
    assert "Try again in" in r.json()["detail"]
    assert _audit(world, "auth.locked", user.id) == 1
    assert _audit(world, "auth.login_failed", user.id) >= 10
    # Wrong password while locked stays generic (no lock disclosure without a valid password).
    assert _login(c, user.email, "wrong-password-xyz").json()["code"] == "invalid_credentials"
    with clock.frozen(clock.now() + timedelta(minutes=16)):
        assert _login(c, user.email).status_code == 200


# -- TCMS-004 / AC-AUTH-04 ------------------------------------------------------------------------


def test_tcms_004_org_admin_must_enrol_mfa_before_anything_else(world: World) -> None:
    org = world.org()
    admin = world.user(org, "NewAdmin", is_org_admin=True)
    c = world.client()
    r = _login(c, admin.email)
    assert r.json() == {"mfa_required": False, "mfa_enrollment_required": True}
    assert c.get("/api/v1/auth/me").status_code == 200
    blocked = c.get("/api/v1/projects")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "mfa_enrollment_required"
    assert (
        c.post(
            "/api/v1/auth/password/change", json={"current_password": PASSWORD, "new_password": "x" * 20}
        ).status_code
        == 403
    )
    setup = c.post("/api/v1/auth/mfa/setup").json()
    enable = c.post(
        "/api/v1/auth/mfa/enable",
        json={"setup_token": setup["setup_token"], "code": pyotp.TOTP(setup["secret"]).now()},
    )
    assert enable.status_code == 200, enable.text
    assert len(enable.json()["recovery_codes"]) == 10
    assert c.get("/api/v1/projects").status_code == 200
    assert _audit(world, "auth.mfa_enrolled", admin.id) == 1


def test_mfa_policy_for_all_users(world: World) -> None:
    org = world.org()
    user = world.user(org, "Policy")
    admin = world.login(org.admin)
    rv = admin.get("/api/v1/organization").json()["row_version"]
    r = admin.patch(
        "/api/v1/organization", json={"settings": {"mfa_required_for_all": True}, "row_version": rv}
    )
    assert r.status_code == 200, r.text
    c = world.client()
    assert _login(c, user.email).json()["mfa_enrollment_required"] is True
    assert c.get("/api/v1/projects").json()["code"] == "mfa_enrollment_required"


# -- TCMS-005 / TCMS-006 / AC-AUTH-05 -------------------------------------------------------------


def _enrol(c: ApiClient) -> tuple[str, list[str]]:
    setup = c.post("/api/v1/auth/mfa/setup").json()
    r = c.post(
        "/api/v1/auth/mfa/enable",
        json={"setup_token": setup["setup_token"], "code": pyotp.TOTP(setup["secret"]).now()},
    )
    assert r.status_code == 200, r.text
    return setup["secret"], r.json()["recovery_codes"]


def test_tcms_005_totp_sign_in_and_replay_rejected(world: World) -> None:
    org = world.org()
    user = world.user(org, "Totp")
    secret, _ = _enrol(world.login(user))
    at = clock.now() + timedelta(seconds=90)  # a step not used during enrolment
    with clock.frozen(at):
        code = pyotp.TOTP(secret).at(at)
        c = world.client()
        assert _login(c, user.email).json()["mfa_required"] is True
        assert c.get("/api/v1/auth/me").json()["code"] == "mfa_required"
        assert c.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 204
        assert c.get("/api/v1/auth/me").status_code == 200
        replay = world.client()
        _login(replay, user.email)
        r = replay.post("/api/v1/auth/mfa/verify", json={"code": code})
        assert r.status_code == 401
        assert r.json()["code"] == "invalid_mfa_code"


def test_tcms_006_recovery_code_works_once(world: World) -> None:
    org = world.org()
    user = world.user(org, "Recovery")
    _, codes = _enrol(world.login(user))
    c = world.client()
    _login(c, user.email)
    assert c.post("/api/v1/auth/mfa/verify", json={"recovery_code": codes[0]}).status_code == 204
    again = world.client()
    _login(again, user.email)
    r = again.post("/api/v1/auth/mfa/verify", json={"recovery_code": codes[0]})
    assert r.json()["code"] == "invalid_mfa_code"


def test_five_mfa_failures_invalidate_pending_sign_in(world: World) -> None:
    org = world.org()
    c = world.client()
    _login(c, org.admin.email)
    for _ in range(4):
        assert c.post("/api/v1/auth/mfa/verify", json={"code": "000000"}).json()["code"] == "invalid_mfa_code"
    assert c.post("/api/v1/auth/mfa/verify", json={"code": "000000"}).json()["code"] == "session_expired"
    assert (
        c.post("/api/v1/auth/mfa/verify", json={"code": org.admin.code()}).json()["code"] == "session_expired"
    )


# -- TCMS-007 / AC-AUTH-07 ------------------------------------------------------------------------


def test_tcms_007_password_reset_single_use_and_revokes_sessions(world: World) -> None:
    org = world.org()
    user = world.user(org, "Reset")
    old = world.login(user)
    anon = world.client()
    assert anon.post("/api/v1/auth/password/forgot", json={"email": user.email}).status_code == 202
    assert anon.post("/api/v1/auth/password/forgot", json={"email": "ghost@nowhere.test"}).status_code == 202
    token = _last_email(world, user.email)["context"]["url"].rsplit("/", 1)[1]
    new_password = "Fresh-Passphrase-42"
    r = anon.post("/api/v1/auth/password/reset", json={"token": token, "new_password": new_password})
    assert r.status_code == 204, r.text
    assert old.get("/api/v1/auth/me").json()["code"] == "session_expired"
    reuse = anon.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "Another-Pass-777"}
    )
    assert reuse.json()["code"] == "token_invalid"
    assert _login(world.client(), user.email, new_password).status_code == 200


def test_reset_link_expires_after_60_minutes(world: World) -> None:
    org = world.org()
    user = world.user(org, "Expire")
    anon = world.client()
    anon.post("/api/v1/auth/password/forgot", json={"email": user.email})
    token = _last_email(world, user.email)["context"]["url"].rsplit("/", 1)[1]
    with clock.frozen(clock.now() + timedelta(minutes=61)):
        r = anon.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": "Fresh-Passphrase-42"}
        )
    assert r.json()["code"] == "token_invalid"


def test_password_policy_enforced(world: World) -> None:
    org = world.org()
    c = world.login(world.user(org, "Weak"))
    r = c.post(
        "/api/v1/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "passwordpassword"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "password_policy"
    assert r.json()["errors"][0]["code"] == "too_common"


def test_password_change_revokes_other_sessions(world: World) -> None:
    org = world.org()
    user = world.user(org, "Changer")
    other, current = world.login(user), world.login(user)
    r = current.post(
        "/api/v1/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "Brand-New-Secret-9"},
    )
    assert r.status_code == 204, r.text
    assert current.get("/api/v1/auth/me").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401


# -- TCMS-008 -------------------------------------------------------------------------------------


def test_tcms_008_invitation_acceptance_creates_member_with_role(world: World) -> None:
    org = world.org()
    pid = world.project(org, "INV")
    admin = world.login(org.admin)
    r = admin.post(
        "/api/v1/organization/invitations",
        json={"email": "new.tester@acme.test", "project_id": str(pid), "role_code": "qa_engineer"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["accept_url"].rsplit("/", 1)[1]
    assert "accept_url" not in admin.get("/api/v1/organization/invitations").json()[0]
    anon = world.client()
    info = anon.get(f"/api/v1/auth/invitations/{token}").json()
    assert info["email"] == "new.tester@acme.test"
    assert info["project"]["key"] == "INV"
    acc = anon.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"display_name": "New Tester", "password": "Long-Enough-Pass-1", "time_zone": "Asia/Karachi"},
    )
    assert acc.status_code == 200, acc.text
    me = anon.get("/api/v1/auth/me").json()
    assert me["memberships"][0]["role"]["code"] == "qa_engineer"
    assert me["time_zone"] == "Asia/Karachi"
    assert (
        anon.post(
            f"/api/v1/auth/invitations/{token}/accept",
            json={"display_name": "X", "password": "Long-Enough-Pass-1"},
        ).json()["code"]
        == "token_invalid"
    )
    assert _last_email(world, "new.tester@acme.test")["template"] == "invitation"


def test_invitation_expires_after_7_days(world: World) -> None:
    org = world.org()
    admin = world.login(org.admin)
    token = (
        admin.post("/api/v1/organization/invitations", json={"email": "late@acme.test"})
        .json()["accept_url"]
        .rsplit("/", 1)[1]
    )
    with clock.frozen(clock.now() + timedelta(days=7, minutes=1)):
        assert world.client().get(f"/api/v1/auth/invitations/{token}").json()["code"] == "token_invalid"


def test_inviting_an_existing_user_is_rejected(world: World) -> None:
    org = world.org()
    user = world.user(org, "Existing")
    r = world.login(org.admin).post("/api/v1/organization/invitations", json={"email": user.email})
    assert r.status_code == 409
    assert r.json()["code"] == "user_exists"


# -- TCMS-009 / AC-AUTH-06 ------------------------------------------------------------------------


def test_tcms_009_idle_session_expires(world: World) -> None:
    org = world.org()
    c = world.login(world.user(org, "Idle"))
    with clock.frozen(clock.now() + timedelta(minutes=29)):
        assert c.get("/api/v1/auth/me").status_code == 200  # activity resets the idle timer
    with clock.frozen(clock.now() + timedelta(minutes=29 + 31)):
        r = c.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == "session_expired"


def test_absolute_session_expiry(world: World) -> None:
    org = world.org()
    c = world.login(world.user(org, "Absolute"))
    start = clock.now()
    for minutes in range(20, 12 * 60, 20):
        with clock.frozen(start + timedelta(minutes=minutes)):
            assert c.get("/api/v1/auth/me").status_code == 200
    with clock.frozen(start + timedelta(hours=12, minutes=1)):
        assert c.get("/api/v1/auth/me").json()["code"] == "session_expired"


def test_logout_and_session_revocation(world: World) -> None:
    org = world.org()
    user = world.user(org, "Sessions")
    a, b = world.login(user), world.login(user)
    sessions = a.get("/api/v1/me/sessions").json()
    assert len(sessions) == 3  # invitation acceptance signed the user in too
    assert sum(s["current"] for s in sessions) == 1
    for other in (s for s in sessions if not s["current"]):
        assert a.delete(f"/api/v1/me/sessions/{other['id']}").status_code == 204
    assert b.get("/api/v1/auth/me").status_code == 401
    assert a.post("/api/v1/auth/logout").status_code == 204
    assert a.get("/api/v1/auth/me").status_code == 401


# -- TCMS-010 -------------------------------------------------------------------------------------


def test_tcms_010_read_token_cannot_write(world: World) -> None:
    org = world.org()
    pid = world.project(org, "TOK")
    user = world.user(org, "Tokens")
    world.member(org, pid, user, "qa_manager")
    c = world.login(user)
    created = c.post("/api/v1/me/api-tokens", json={"name": "ci", "scope": "read", "expires_in_days": 30})
    assert created.status_code == 201, created.text
    secret = created.json()["token"]
    assert secret.startswith("tcms_")
    assert len(secret) == 45
    assert "token" not in c.get("/api/v1/me/api-tokens").json()[0]
    bearer = world.client()
    h = {"Authorization": f"Bearer {secret}"}
    assert bearer.get(f"/api/v1/projects/{pid}", headers=h).status_code == 200
    r = bearer.post(f"/api/v1/projects/{pid}/environments", json={"name": "UAT"}, headers=h)
    assert r.status_code == 403
    assert r.json()["code"] == "token_scope_insufficient"
    rw = c.post("/api/v1/me/api-tokens", json={"name": "rw", "scope": "read_write"}).json()["token"]
    r = bearer.post(
        f"/api/v1/projects/{pid}/environments",
        json={"name": "UAT"},
        headers={"Authorization": f"Bearer {rw}"},
    )
    assert r.status_code == 201, r.text  # bearer requests need no CSRF header
    token_id = created.json()["id"]
    assert c.delete(f"/api/v1/me/api-tokens/{token_id}").status_code == 204
    assert bearer.get(f"/api/v1/projects/{pid}", headers=h).status_code == 401


def test_project_restricted_token(world: World) -> None:
    org = world.org()
    p1, p2 = world.project(org, "PONE"), world.project(org, "PTWO")
    user = world.user(org, "Restricted")
    world.member(org, p1, user, "viewer")
    world.member(org, p2, user, "viewer")
    c = world.login(user)
    secret = c.post(
        "/api/v1/me/api-tokens", json={"name": "p1", "scope": "read", "project_id": str(p1)}
    ).json()["token"]
    h = {"Authorization": f"Bearer {secret}"}
    b = world.client()
    assert b.get(f"/api/v1/projects/{p1}", headers=h).status_code == 200
    assert b.get(f"/api/v1/projects/{p2}", headers=h).status_code == 404
    assert [p["key"] for p in b.get("/api/v1/projects", headers=h).json()] == ["PONE"]


# -- TCMS-011 -------------------------------------------------------------------------------------


def test_tcms_011_deactivated_user_sessions_and_tokens_revoked(world: World) -> None:
    org = world.org()
    user = world.user(org, "Leaver")
    c = world.login(user)
    secret = c.post("/api/v1/me/api-tokens", json={"name": "t", "scope": "read"}).json()["token"]
    admin = world.login(org.admin)
    assert admin.post(f"/api/v1/organization/members/{user.id}/deactivate").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401
    assert (
        world.client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {secret}"}).status_code
        == 401
    )
    assert _login(world.client(), user.email).json()["code"] == "invalid_credentials"
    assert _audit(world, "user.deactivated", user.id) == 1
    assert admin.post(f"/api/v1/organization/members/{user.id}/reactivate").status_code == 204
    assert _login(world.client(), user.email).status_code == 200


def test_last_org_admin_is_protected(world: World) -> None:
    org = world.org()
    admin = world.login(org.admin)
    r = admin.patch(f"/api/v1/organization/members/{org.admin.id}", json={"is_org_admin": False})
    assert r.json()["code"] == "last_org_admin"
    assert (
        admin.post(f"/api/v1/organization/members/{org.admin.id}/deactivate").json()["code"]
        == "cannot_deactivate_self"
    )


def test_admin_resets_user_mfa(world: World) -> None:
    org = world.org()
    user = world.user(org, "Lostphone")
    _enrol(world.login(user))
    admin = world.login(org.admin)
    assert (
        admin.post(
            f"/api/v1/organization/members/{user.id}/reset-mfa", json={"reason": "lost phone"}
        ).status_code
        == 204
    )
    assert _login(world.client(), user.email).json()["mfa_required"] is False
    assert _audit(world, "auth.mfa_reset", user.id) == 1


# -- TCMS-014 -------------------------------------------------------------------------------------


def test_tcms_014_csrf_header_required_for_cookie_writes(world: World) -> None:
    org = world.org()
    c = world.login(world.user(org, "Csrf"))
    r = c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"
    plain = c.cookies.get("tcms_csrf")
    assert plain


def test_cross_origin_login_rejected(world: World) -> None:
    org = world.org()
    user = world.user(org, "Origin")
    r = world.client().post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
        headers={"Origin": "https://evil.test"},
    )
    assert r.status_code == 403


def test_auth_rate_limit(m1_settings: Any) -> None:
    """20/min per IP in production; lowered here to 3."""
    settings = make_settings(m1_settings, rate_limit_auth_per_min=3)
    app = create_app(settings)
    with app.state.tcms.session_factory() as s:
        s.execute(text("DELETE FROM auth_rate_limits"))
        s.commit()
    c = ApiClient(app, base_url="https://testserver")
    codes = [c.post("/api/v1/auth/password/forgot", json={"email": "x@y.test"}).status_code for _ in range(4)]
    assert codes[:3] == [202, 202, 202]
    assert codes[3] == 429
    r = c.post("/api/v1/auth/password/forgot", json={"email": "x@y.test"})
    assert int(r.headers["Retry-After"]) >= 1
