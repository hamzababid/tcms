"""M8c hardening (NFR-SEC-09, docs/06 §2.10, §4.14; L9, L36): response headers, the general rate limit,
the OpenAPI schema behind sign-in in production, and the project-name race."""

from __future__ import annotations

from typing import Any

import pytest

from tcms.api.security import FixedWindowLimiter
from tcms.core.config import Settings
from tests.world import ApiClient, World, make_settings

pytestmark = pytest.mark.integration


def _app(settings: Settings, **overrides: Any) -> Any:
    from tcms.main import create_app

    return create_app(make_settings(settings, **overrides))


def test_api_responses_carry_security_headers(world: World) -> None:
    r = world.client().get("/api/v1/health/live")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert r.headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in r.headers  # local: Caddy adds HSTS in production
    # Errors too (problem+json comes from the exception handlers, outside the routes).
    missing = world.client().get("/api/v1/projects")
    assert missing.status_code == 401
    assert missing.headers["X-Frame-Options"] == "DENY"


def test_fixed_window_limiter_counts_per_caller_and_resets() -> None:
    now = [100.0]
    limiter = FixedWindowLimiter(2, clock=lambda: now[0])
    assert limiter.hit("a") == (True, 1, 60)
    assert limiter.hit("a")[0:2] == (True, 0)
    allowed, remaining, reset = limiter.hit("a")
    assert (allowed, remaining) == (False, 0)
    assert reset == 60
    assert limiter.hit("b")[0] is True  # another caller has its own budget
    now[0] += 45
    assert limiter.hit("a")[2] == 15
    now[0] += 15
    assert limiter.hit("a") == (True, 1, 60)  # a new window


def test_l9_general_rate_limit_answers_429_with_headers(m1_settings: Settings) -> None:
    app = _app(m1_settings, rate_limit_per_min=3)
    client = ApiClient(app, base_url="https://testserver")
    codes = [client.get("/api/v1/projects").status_code for _ in range(3)]
    assert codes == [401, 401, 401]
    first = client.get("/api/v1/projects")
    assert first.status_code == 429
    assert first.json()["code"] == "rate_limited"
    assert first.headers["RateLimit-Limit"] == "3"
    assert first.headers["RateLimit-Remaining"] == "0"
    assert 1 <= int(first.headers["Retry-After"]) <= 60
    # Health checks are never limited (load balancers poll them).
    assert client.get("/api/v1/health/live").status_code == 200


def test_rate_limit_keys_signed_in_callers_by_session(world: World, m1_settings: Settings) -> None:
    app = _app(m1_settings, rate_limit_per_min=4)
    org = world.org("Session limit org")
    user = world.user(org, "Session")
    client = ApiClient(app, base_url="https://testserver")
    assert (
        client.post("/api/v1/auth/login", json={"email": user.email, "password": user.password}).status_code
        == 200
    )
    statuses = [client.get("/api/v1/projects").status_code for _ in range(5)]
    assert statuses[:4] == [200, 200, 200, 200]
    assert statuses[4] == 429
    # Another caller from the same address is unaffected.
    assert ApiClient(app, base_url="https://testserver").get("/api/v1/projects").status_code == 401


def test_made_up_credentials_do_not_get_fresh_buckets(world: World, m1_settings: Settings) -> None:
    """ASVS 2.4.1: a new random token per request would otherwise be a new caller each time."""
    app = _app(m1_settings, rate_limit_per_min=3)
    client = ApiClient(app, base_url="https://testserver")
    codes = [
        client.get("/api/v1/projects", headers={"Authorization": f"Bearer made-up-{i}"}).status_code
        for i in range(5)
    ]
    assert codes == [401, 401, 401, 429, 429]
    blocked = client.get("/api/v1/projects", headers={"Authorization": "Bearer made-up-9"})
    assert blocked.json()["code"] == "rate_limited"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    # A valid session from the same address still works: only rejected credentials are counted.
    org = world.org("Rejected limit org")
    user = world.user(org, "Valid")
    signed = ApiClient(app, base_url="https://testserver")
    assert (
        signed.post("/api/v1/auth/login", json={"email": user.email, "password": user.password}).status_code
        == 200
    )
    assert signed.get("/api/v1/projects").status_code == 200


def test_nul_characters_in_text_are_a_422_not_a_500(world: World) -> None:
    """Found by the M8c authenticated ZAP scan: PostgreSQL text cannot hold NUL (0x00)."""
    client = world.client()
    for path in ("/api/v1/auth/login", "/api/v1/auth/password/forgot"):
        r = client.post(path, json={"email": "'\"\x00<script>alert(1);</script>", "password": "x"})
        assert r.status_code == 422, (path, r.text)
        assert r.json()["code"] == "validation_error"
    org = world.org("NUL org")
    admin = world.login(org.admin)
    r = admin.post("/api/v1/projects", json={"key": "NULX", "name": "Bad\x00name"})
    assert r.status_code == 422, r.text
    assert "NUL" in r.json()["detail"]


def test_openapi_needs_sign_in_in_production(world: World, m1_settings: Settings) -> None:
    app = _app(m1_settings, tcms_env="production")
    anonymous = ApiClient(app, base_url="https://testserver")
    r = anonymous.get("/api/v1/openapi.json")
    assert r.status_code == 401
    assert anonymous.get("/api/v1/docs").status_code == 404
    assert r.headers["Strict-Transport-Security"].startswith("max-age=31536000")
    org = world.org("Prod org")
    user = world.user(org, "Reader")
    signed = ApiClient(app, base_url="https://testserver")
    assert (
        signed.post("/api/v1/auth/login", json={"email": user.email, "password": user.password}).status_code
        == 200
    )
    schema = signed.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert "/api/v1/projects" in schema.json()["paths"]
    assert "/api/v1/openapi.json" not in schema.json()["paths"]


def test_l36_project_name_race_returns_409_not_500(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from tcms.workspace import repository

    org = world.org("Race org")
    admin = world.login(org.admin)
    assert admin.post("/api/v1/projects", json={"key": "RACEA", "name": "Race"}).status_code == 201
    # The other request passed the checks before the first one committed: skip them to reach the insert.
    monkeypatch.setattr(repository, "active_project_named", lambda *a, **k: None)
    monkeypatch.setattr(repository, "project_by_key", lambda *a, **k: None)
    same_name = admin.post("/api/v1/projects", json={"key": "RACEB", "name": "race"})
    assert same_name.status_code == 409, same_name.text
    assert same_name.json()["code"] == "name_taken"
    same_key = admin.post("/api/v1/projects", json={"key": "RACEA", "name": "Another"})
    assert same_key.status_code == 409
    assert same_key.json()["code"] == "project_key_taken"
