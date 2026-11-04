"""Test world builder: organizations, users, projects created through the real services.

Users are created the way production creates them (invitation → acceptance). Org Admins are enrolled in
MFA with a known secret so tests can sign them in with a TOTP code.
"""

from __future__ import annotations

import base64
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tcms.core.config import Settings
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.enums import CaseFormat
from tcms.core.permissions import PROJECT_PERMISSIONS, ROLE_PERMISSIONS, RoleCode
from tcms.core.uow import unit_of_work
from tcms.identity import service as identity
from tcms.testdesign import rules
from tcms.testdesign import service as testdesign
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace

PASSWORD = "Correct-Horse-Battery-9"  # test-only credential


def make_settings(base: Settings, **overrides: Any) -> Settings:
    values = {
        **base.model_dump(),
        "tcms_secret_key": "t" * 48,
        "tcms_encryption_keys": "k1:" + base64.b64encode(b"\x01" * 32).decode(),
        "tcms_base_url": "https://testserver",
        "rate_limit_auth_per_min": 100_000,
        "session_cookie_secure": True,
        **overrides,
    }
    return Settings(**values)


class ApiClient(TestClient):
    """TestClient that echoes the CSRF cookie into X-CSRF-Token on unsafe requests (like the SPA)."""

    def request(self, method: str, url: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            token = self.cookies.get("tcms_csrf")
            if token:
                headers = dict(kwargs.pop("headers", None) or {})
                headers.setdefault("X-CSRF-Token", token)
                kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@dataclass
class UserHandle:
    id: UUID
    email: str
    password: str
    totp_secret: str | None = None

    def code(self) -> str:
        """TOTP for the app clock (follows `clock.frozen`)."""
        from tcms.core import clock

        assert self.totp_secret
        return pyotp.TOTP(self.totp_secret).at(clock.now())


@dataclass
class OrgHandle:
    id: UUID
    slug: str
    admin: UserHandle
    users: dict[str, UserHandle] = field(default_factory=dict)


class World:
    def __init__(self, app: Any, settings: Settings, factory: sessionmaker[Session]) -> None:
        self.app = app
        self.settings = settings
        self.factory = factory

    # -- builders ---------------------------------------------------------------------------------
    def org(self, name: str = "ACME") -> OrgHandle:
        slug = f"o{uuid.uuid4().hex[:12]}"
        admin_email = f"admin-{slug}@acme.test"
        with unit_of_work(self.factory) as uow:
            org = workspace.create_organization(uow, name=name, slug=slug)
            inv = identity.bootstrap_admin_invitation(
                uow, self.settings, organization_id=org.id, email=admin_email
            )
        token = inv.accept_url.rsplit("/", 1)[1]
        admin_id = self._accept(token, "Admin")
        secret = pyotp.random_base32()
        with unit_of_work(self.factory) as uow:
            ctx = self.ctx(org.id, admin_id, is_admin=True)
            identity.enroll_mfa_with_secret(uow, self.settings, ctx, secret)
        return OrgHandle(org.id, slug, UserHandle(admin_id, admin_email, PASSWORD, secret))

    def user(self, org: OrgHandle, name: str, *, is_org_admin: bool = False) -> UserHandle:
        email = f"{name.lower()}-{secrets.token_hex(3)}@{org.slug}.test"
        with unit_of_work(self.factory) as uow:
            ctx = self.ctx(org.id, org.admin.id, is_admin=True, perms=frozenset({"org.users.manage"}))
            inv = identity.create_invitation(uow, self.settings, ctx, email=email, is_org_admin=is_org_admin)
        user_id = self._accept(inv.accept_url.rsplit("/", 1)[1], name)
        handle = UserHandle(user_id, email, PASSWORD)
        org.users[name] = handle
        return handle

    def project(self, org: OrgHandle, key: str = "SPARK", name: str | None = None) -> UUID:
        with unit_of_work(self.factory) as uow:
            ctx = self.ctx(org.id, org.admin.id, is_admin=True, perms=frozenset({"project.create"}))
            p = workspace.create_project(
                uow,
                ctx,
                key=key,
                name=name or f"{key} project",
                description=None,
                policy=workspace_queries.org_policy(uow.session, org.id),
            )
        return p.id

    def member(self, org: OrgHandle, project_id: UUID, user: UserHandle, role: RoleCode | str) -> None:
        with unit_of_work(self.factory) as uow:
            ctx = self.ctx(
                org.id,
                org.admin.id,
                is_admin=True,
                project_id=project_id,
                perms=frozenset({"project.members.manage"}),
            )
            identity.add_member(uow, ctx, user_id=user.id, role_code=str(role))

    def team(self, org: OrgHandle, project_id: UUID) -> dict[str, UserHandle]:
        """One user per system role in the project (08 §3)."""
        out = {}
        for role in RoleCode:
            u = self.user(org, role.value)
            self.member(org, project_id, u, role)
            out[role.value] = u
        return out

    # -- test design ------------------------------------------------------------------------------
    def _project_admin(self, org: OrgHandle, project_id: UUID) -> AccessContext:
        return self.ctx(org.id, org.admin.id, is_admin=True, project_id=project_id, perms=PROJECT_PERMISSIONS)

    def folder(
        self, org: OrgHandle, project_id: UUID, name: str | None = None, parent_id: UUID | None = None
    ) -> UUID:
        with unit_of_work(self.factory) as uow:
            f = testdesign.create_folder(
                uow,
                self._project_admin(org, project_id),
                name=name or f"F-{uuid.uuid4().hex[:8]}",
                parent_id=parent_id,
                description=None,
            )
            return f.id

    def case(
        self, org: OrgHandle, project_id: UUID, folder_id: UUID, title: str | None = None, *, steps: int = 1
    ) -> tuple[UUID, str]:
        """A test case created by the Org Admin through the service; returns (id, key)."""
        with unit_of_work(self.factory) as uow:
            content = rules.Content(
                format=CaseFormat.steps,
                title=title or f"Case {uuid.uuid4().hex[:8]}",
                steps=tuple(rules.StepContent(f"Do {i}", f"See {i}", None) for i in range(1, steps + 1)),
            )
            result = testdesign.create_case(
                uow,
                self._project_admin(org, project_id),
                content=content,
                meta=testdesign.CaseMetadata(folder_id=folder_id),
            )
            return result.case.id, result.case.key

    # -- clients ----------------------------------------------------------------------------------
    def client(self) -> ApiClient:
        return ApiClient(self.app, base_url="https://testserver", raise_server_exceptions=True)

    def login(self, user: UserHandle) -> ApiClient:
        c = self.client()
        r = c.post("/api/v1/auth/login", json={"email": user.email, "password": user.password})
        assert r.status_code == 200, r.text
        if r.json()["mfa_required"]:
            from datetime import timedelta

            from tcms.core import clock

            r = c.post("/api/v1/auth/mfa/verify", json={"code": user.code()})
            step = 1
            while r.status_code == 401 and r.json()["code"] == "invalid_mfa_code" and step <= 3:
                # The code of this 30 s step was already used (replay protection): use a later step.
                with clock.frozen(clock.now() + timedelta(seconds=30 * step)):
                    r = c.post("/api/v1/auth/mfa/verify", json={"code": user.code()})
                step += 1
            assert r.status_code == 204, r.text
        return c

    # -- helpers ----------------------------------------------------------------------------------
    def ctx(
        self,
        org_id: UUID,
        user_id: UUID,
        *,
        is_admin: bool = False,
        project_id: UUID | None = None,
        perms: frozenset[str] = frozenset(),
    ) -> AccessContext:
        p = Principal(user_id, org_id, is_admin, display_name="Test")
        return AccessContext.for_principal(
            p, RequestMeta("req_test"), project_id=project_id, permissions=perms
        )

    def _accept(self, token: str, name: str) -> UUID:
        with unit_of_work(self.factory) as uow:
            accepted = identity.accept_invitation(
                uow,
                token=token,
                display_name=name,
                password=PASSWORD,
                time_zone="UTC",
                meta=RequestMeta("req_test"),
                policy_for=lambda o: workspace_queries.org_policy(uow.session, o),
            )
        return accepted.user_id


ALL_ROLES = [r.value for r in RoleCode]
ROLE_PERMS = {r.value: perms for r, perms in ROLE_PERMISSIONS.items()}
