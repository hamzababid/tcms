"""Authorization matrix (docs/08 §7, TCMS-012): every route, its permission, and a probe request.

Kinds:
- `public`: no authentication.
- `auth`: any signed-in user (including own-profile routes).
- `org:<perm>`: organization permission.
- `project:<perm>`: permission in the probe project; non-members and other organizations get 404.

Each probe builds the request for a given caller. Authorized callers must not get 401/403/404; probes are
chosen so that, after the permission check, the request fails a harmless business rule or is a no-op.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tests.world import OrgHandle, UserHandle, World


@dataclass
class Fixture:
    world: World
    org: OrgHandle
    project_id: UUID
    team: dict[str, UserHandle]
    env_id: UUID
    release_id: UUID
    release_row_version: int


Request = tuple[str, str, dict[str, Any] | None]
Probe = Callable[[Fixture], Request]


@dataclass(frozen=True)
class Entry:
    kind: str
    probe: Probe | None = None  # None: covered by dedicated tests (public/auth flows)


def _throwaway_member(f: Fixture) -> UUID:
    u = f.world.user(f.org, "Throwaway")
    f.world.member(f.org, f.project_id, u, "viewer")
    return u.id


def _throwaway_user(f: Fixture) -> UUID:
    return f.world.user(f.org, "Target").id


def _invitation(f: Fixture) -> UUID:
    from tcms.core.uow import unit_of_work
    from tcms.identity import service as identity

    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(f.org.id, f.org.admin.id, is_admin=True, perms=frozenset({"org.users.manage"}))
        inv = identity.create_invitation(
            uow, f.world.settings, ctx, email=f"pending-{UUID(int=0).hex[:4]}{id(f)}@x.test"
        )
    return inv.invitation.id


P = "/api/v1/projects/{project_id}"

MATRIX: dict[tuple[str, str], Entry] = {
    # health and meta
    ("GET", "/api/v1/health/live"): Entry("public"),
    ("GET", "/api/v1/health/ready"): Entry("public"),
    ("GET", "/api/v1/meta/enums"): Entry("auth", lambda f: ("GET", "/api/v1/meta/enums", None)),
    ("GET", "/api/v1/meta/permissions"): Entry("auth", lambda f: ("GET", "/api/v1/meta/permissions", None)),
    # auth flows (dedicated tests in test_auth.py)
    ("POST", "/api/v1/auth/login"): Entry("public"),
    ("POST", "/api/v1/auth/mfa/verify"): Entry("public"),
    ("POST", "/api/v1/auth/password/forgot"): Entry("public"),
    ("POST", "/api/v1/auth/password/reset"): Entry("public"),
    ("GET", "/api/v1/auth/invitations/{token}"): Entry("public"),
    ("POST", "/api/v1/auth/invitations/{token}/accept"): Entry("public"),
    ("POST", "/api/v1/auth/logout"): Entry("auth"),
    ("GET", "/api/v1/auth/me"): Entry("auth", lambda f: ("GET", "/api/v1/auth/me", None)),
    ("PATCH", "/api/v1/auth/me"): Entry("auth", lambda f: ("PATCH", "/api/v1/auth/me", {})),
    ("POST", "/api/v1/auth/password/change"): Entry("auth"),
    ("POST", "/api/v1/auth/mfa/setup"): Entry("auth"),
    ("POST", "/api/v1/auth/mfa/enable"): Entry("auth"),
    ("POST", "/api/v1/auth/mfa/disable"): Entry("auth"),
    ("POST", "/api/v1/auth/mfa/recovery-codes"): Entry("auth"),
    ("GET", "/api/v1/me/sessions"): Entry("auth", lambda f: ("GET", "/api/v1/me/sessions", None)),
    ("DELETE", "/api/v1/me/sessions/{session_id}"): Entry("auth"),
    ("GET", "/api/v1/me/api-tokens"): Entry("auth", lambda f: ("GET", "/api/v1/me/api-tokens", None)),
    ("POST", "/api/v1/me/api-tokens"): Entry("auth"),
    ("DELETE", "/api/v1/me/api-tokens/{token_id}"): Entry("auth"),
    # organization
    ("GET", "/api/v1/organization"): Entry("auth", lambda f: ("GET", "/api/v1/organization", None)),
    ("PATCH", "/api/v1/organization"): Entry(
        "org:org.manage", lambda f: ("PATCH", "/api/v1/organization", {"name": "x", "row_version": 0})
    ),
    ("GET", "/api/v1/organization/members"): Entry(
        "org:org.users.manage", lambda f: ("GET", "/api/v1/organization/members", None)
    ),
    ("POST", "/api/v1/organization/members/{user_id}/deactivate"): Entry(
        "org:org.users.manage",
        lambda f: ("POST", f"/api/v1/organization/members/{f.org.admin.id}/deactivate", None),
    ),
    ("POST", "/api/v1/organization/members/{user_id}/reactivate"): Entry(
        "org:org.users.manage",
        lambda f: ("POST", f"/api/v1/organization/members/{f.org.admin.id}/reactivate", None),
    ),
    ("POST", "/api/v1/organization/members/{user_id}/reset-mfa"): Entry(
        "org:org.users.manage",
        lambda f: (
            "POST",
            f"/api/v1/organization/members/{_throwaway_user(f)}/reset-mfa",
            {"reason": "probe"},
        ),
    ),
    ("POST", "/api/v1/organization/members/{user_id}/revoke-sessions"): Entry(
        "org:org.users.manage",
        lambda f: ("POST", f"/api/v1/organization/members/{_throwaway_user(f)}/revoke-sessions", None),
    ),
    ("PATCH", "/api/v1/organization/members/{user_id}"): Entry(
        "org:org.users.manage",
        lambda f: ("PATCH", f"/api/v1/organization/members/{f.org.admin.id}", {"is_org_admin": True}),
    ),
    ("GET", "/api/v1/organization/invitations"): Entry(
        "org:org.users.manage", lambda f: ("GET", "/api/v1/organization/invitations", None)
    ),
    ("POST", "/api/v1/organization/invitations"): Entry(
        "org:org.users.manage",
        lambda f: ("POST", "/api/v1/organization/invitations", {"email": f.org.admin.email}),
    ),
    ("DELETE", "/api/v1/organization/invitations/{invitation_id}"): Entry(
        "org:org.users.manage",
        lambda f: ("DELETE", f"/api/v1/organization/invitations/{_invitation(f)}", None),
    ),
    ("GET", "/api/v1/organization/roles"): Entry(
        "auth", lambda f: ("GET", "/api/v1/organization/roles", None)
    ),
    # projects
    ("GET", "/api/v1/projects"): Entry("auth", lambda f: ("GET", "/api/v1/projects", None)),
    ("POST", "/api/v1/projects"): Entry(
        "org:project.create", lambda f: ("POST", "/api/v1/projects", {"key": "x!", "name": "Probe"})
    ),
    ("GET", P): Entry("project:project.view", lambda f: ("GET", P.format(project_id=f.project_id), None)),
    ("PATCH", P): Entry(
        "project:project.configure",
        lambda f: ("PATCH", P.format(project_id=f.project_id), {"name": "x", "row_version": 0}),
    ),
    ("POST", P + "/archive"): Entry(
        "project:project.configure",
        lambda f: ("POST", P.format(project_id=f.project_id) + "/archive", {"confirm_key": "NO"}),
    ),
    ("POST", P + "/restore"): Entry(
        "project:project.configure", lambda f: ("POST", P.format(project_id=f.project_id) + "/restore", None)
    ),
    ("GET", P + "/activity"): Entry(
        "project:project.view", lambda f: ("GET", P.format(project_id=f.project_id) + "/activity", None)
    ),
    ("GET", P + "/members"): Entry(
        "project:project.view", lambda f: ("GET", P.format(project_id=f.project_id) + "/members", None)
    ),
    ("POST", P + "/members"): Entry(
        "project:project.members.manage",
        lambda f: (
            "POST",
            P.format(project_id=f.project_id) + "/members",
            {"user_id": str(f.team["viewer"].id)},
        ),
    ),
    ("PATCH", P + "/members/{user_id}"): Entry(
        "project:project.members.manage",
        lambda f: (
            "PATCH",
            P.format(project_id=f.project_id) + f"/members/{f.team['viewer'].id}",
            {"role_code": "viewer"},
        ),
    ),
    ("DELETE", P + "/members/{user_id}"): Entry(
        "project:project.members.manage",
        lambda f: ("DELETE", P.format(project_id=f.project_id) + f"/members/{_throwaway_member(f)}", None),
    ),
    ("GET", P + "/environments"): Entry(
        "project:project.view", lambda f: ("GET", P.format(project_id=f.project_id) + "/environments", None)
    ),
    ("POST", P + "/environments"): Entry(
        "project:project.configure",
        lambda f: ("POST", P.format(project_id=f.project_id) + "/environments", {"name": "QA"}),
    ),
    ("PATCH", "/api/v1/environments/{environment_id}"): Entry(
        "project:project.configure",
        lambda f: ("PATCH", f"/api/v1/environments/{f.env_id}", {"name": "x", "row_version": 0}),
    ),
    ("POST", "/api/v1/environments/{environment_id}/archive"): Entry(
        "project:project.configure", lambda f: ("POST", f"/api/v1/environments/{f.env_id}/restore", None)
    ),
    ("POST", "/api/v1/environments/{environment_id}/restore"): Entry(
        "project:project.configure", lambda f: ("POST", f"/api/v1/environments/{f.env_id}/restore", None)
    ),
    ("GET", P + "/releases"): Entry(
        "project:project.view", lambda f: ("GET", P.format(project_id=f.project_id) + "/releases", None)
    ),
    ("POST", P + "/releases"): Entry(
        "project:release.manage",
        lambda f: ("POST", P.format(project_id=f.project_id) + "/releases", {"name": "R1"}),
    ),
    ("GET", "/api/v1/releases/{release_id}"): Entry(
        "project:project.view", lambda f: ("GET", f"/api/v1/releases/{f.release_id}", None)
    ),
    ("PATCH", "/api/v1/releases/{release_id}"): Entry(
        "project:release.manage",
        lambda f: ("PATCH", f"/api/v1/releases/{f.release_id}", {"name": "x", "row_version": 0}),
    ),
    ("GET", "/api/v1/audit-events/entity/{entity_type}/{entity_id}"): Entry(
        "project:project.view", lambda f: ("GET", f"/api/v1/audit-events/entity/release/{f.release_id}", None)
    ),
}
