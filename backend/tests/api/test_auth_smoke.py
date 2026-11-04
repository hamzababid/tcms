"""M1 smoke: invitation → sign-in (TCMS-001 API part), admin MFA sign-in, project creation (TCMS-020)."""

from __future__ import annotations

import pytest

from tests.world import World

pytestmark = pytest.mark.integration


def test_member_signs_in_with_secure_cookies(world: World) -> None:
    """AC-AUTH-01."""
    org = world.org()
    user = world.user(org, "Sana")
    c = world.client()
    r = c.post("/api/v1/auth/login", json={"email": user.email, "password": user.password})
    assert r.status_code == 200, r.text
    assert r.json() == {"mfa_required": False, "mfa_enrollment_required": False}
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("tcms_session="))
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
    assert c.get("/api/v1/auth/me").json()["user"]["email"] == user.email


def test_admin_signs_in_with_totp_and_creates_project(world: World) -> None:
    org = world.org()
    c = world.login(org.admin)
    r = c.post("/api/v1/projects", json={"key": "spark", "name": "SPARK"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["key"] == "SPARK"
    envs = {e["name"] for e in c.get(f"/api/v1/projects/{pid}/environments").json()}
    assert envs == {"QA", "Staging"}
    dup = c.post("/api/v1/projects", json={"key": "Spark", "name": "Other"})
    assert dup.status_code == 409 and dup.json()["code"] == "project_key_taken"  # AC-WS-01


def test_unknown_email_and_wrong_password_answer_identically(world: World) -> None:
    """AC-AUTH-02 (body/status)."""
    org = world.org()
    user = world.user(org, "Bilal")
    c = world.client()
    a = c.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong-password-123"})
    b = c.post("/api/v1/auth/login", json={"email": "nobody@nowhere.test", "password": "wrong-password-123"})
    strip = lambda r: {k: v for k, v in r.json().items() if k not in ("request_id",)}  # noqa: E731
    assert a.status_code == b.status_code == 401
    assert strip(a) == strip(b)
