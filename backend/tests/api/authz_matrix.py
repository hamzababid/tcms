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

import uuid
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
    folder_id: UUID
    case_id: UUID
    case_key: str


Request = tuple[str, str, dict[str, Any] | None]
Probe = Callable[[Fixture], Request]


@dataclass(frozen=True)
class Entry:
    kind: str
    probe: Probe | None = None  # None: covered by dedicated tests (public/auth flows)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


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


def _folder(f: Fixture) -> UUID:
    return f.world.folder(f.org, f.project_id)


def _case(f: Fixture) -> UUID:
    return f.world.case(f.org, f.project_id, f.folder_id)[0]


def _linked_pair(f: Fixture) -> tuple[UUID, UUID]:
    from tcms.core.enums import CaseLinkType
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.testdesign import service as testdesign

    a, b = _case(f), _case(f)
    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        testdesign.add_link(uow, ctx, a, target_case_id=b, link_type=CaseLinkType.related)
    return a, b


def _tag(f: Fixture) -> UUID:
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.testdesign import service as testdesign

    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        # A fresh name per probe call (id() of a short-lived object can repeat).
        return testdesign.create_tag(uow, ctx, f"t{uuid.uuid4().hex[:12]}").id


def _plan(f: Fixture) -> UUID:
    from tcms.core.enums import PlanType
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.planning import service as planning

    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        plan = planning.create_plan(
            uow, ctx, planning.PlanData(name=f"Plan {uuid.uuid4().hex[:8]}", type=PlanType.regression)
        )
        return plan.id


def _cycle(f: Fixture) -> UUID:
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.execution import service as execution

    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        result = execution.create_cycle(
            uow,
            ctx,
            execution.CycleData(name=f"Cycle {uuid.uuid4().hex[:8]}", environment_id=_as_uuid(f.env_id)),
        )
        return result.cycle.id


def _run(f: Fixture) -> UUID:
    """A cycle with one run; returns the run id."""
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.execution import repository as execution_repo
    from tcms.execution import service as execution

    case_id = _case(f)
    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        result = execution.create_cycle(
            uow,
            ctx,
            execution.CycleData(
                name=f"Cycle {uuid.uuid4().hex[:8]}",
                environment_id=_as_uuid(f.env_id),
                selection=execution.Selection(case_ids=[case_id]),
            ),
        )
        uow.session.flush()
        runs = execution_repo.runs_in_cycle(uow.session, ctx, result.cycle.id)
        return runs[0].id


def _draft(f: Fixture) -> tuple[UUID, UUID]:
    """A fresh run with a draft attempt started by the Org Admin → (result id, step id). Editing it needs
    the executor or cycle.manage (BR-06), so the matrix kind is cycle.manage."""
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.execution import repository as execution_repo
    from tcms.execution import service as execution

    run_id = _run(f)
    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        res = execution.start_attempt(uow, ctx, run_id).result
        step = execution_repo.step_results(uow.session, res.id)[0]
        return res.id, step.step_id


def _remove_run_probe(f: Fixture) -> tuple[str, str, dict[str, Any]]:
    """DELETE a real not-run run of its own cycle (unknown run ids are a 404)."""
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.execution import queries as execution_queries

    run_id = _run(f)
    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        row = execution_queries.run_row(uow.session, ctx, run_id)
        assert row is not None
        cycle_id = row.run.cycle_id
    return ("DELETE", f"/api/v1/cycles/{cycle_id}/runs", {"run_ids": [str(run_id)]})


def _bug_link(f: Fixture, reference: str | None = None) -> tuple[UUID, str, UUID]:
    """A bug link on a fresh draft, made by the Org Admin → (link id, reference, result id). Changing it
    needs its creator or defect.edit, so the matrix kind is defect.edit."""
    from tcms.bugs import service as bugs
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work

    result_id, _ = _draft(f)
    ref = reference or f"PRB-{uuid.uuid4().hex[:6]}"
    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        row = bugs.link_to_result(uow, ctx, result_id, reference=ref, url=None, title=None, step_id=None)
        return row.id, ref, result_id


def _requirement(f: Fixture, *, linked: bool = False) -> UUID:
    """A requirement reference made by the Org Admin (optionally linked to the fixture case)."""
    from tcms.core.permissions import PROJECT_PERMISSIONS
    from tcms.core.uow import unit_of_work
    from tcms.requirements import service as requirements

    with unit_of_work(f.world.factory) as uow:
        ctx = f.world.ctx(
            f.org.id, f.org.admin.id, is_admin=True, project_id=f.project_id, perms=PROJECT_PERMISSIONS
        )
        ref = requirements.ensure_refs(uow, ctx, [f"REQ-{uuid.uuid4().hex[:8]}"]).refs[0]
        if linked:
            requirements.link(uow, ctx, [ref], [_as_uuid(f.case_id)])
        return ref.id


RQ = "/api/v1/requirements/{ref_id}"
P = "/api/v1/projects/{project_id}"
TC = "/api/v1/test-cases/{case_id}"
PL = "/api/v1/test-plans/{plan_id}"
CY = "/api/v1/cycles/{cycle_id}"
RN = "/api/v1/runs/{run_id}"
RS = "/api/v1/results/{result_id}"


def _p(f: Fixture, suffix: str) -> str:
    return P.format(project_id=f.project_id) + suffix


def _tc(f: Fixture, suffix: str = "", case_id: UUID | None = None) -> str:
    return TC.format(case_id=case_id or f.case_id) + suffix


def _content(title: str = "Probe case") -> dict[str, Any]:
    return {"format": "steps", "title": title, "steps": [{"action": "a", "expected_result": "b"}]}


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
    ("GET", P + "/member-candidates"): Entry(
        "project:project.members.manage",
        lambda f: ("GET", P.format(project_id=f.project_id) + "/member-candidates", None),
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
    # folders (M2)
    ("GET", P + "/folders"): Entry("project:project.view", lambda f: ("GET", _p(f, "/folders"), None)),
    ("POST", P + "/folders"): Entry(
        "project:folder.manage", lambda f: ("POST", _p(f, "/folders"), {"name": "Probe folder"})
    ),
    ("PATCH", "/api/v1/folders/{folder_id}"): Entry(
        "project:folder.manage",
        lambda f: ("PATCH", f"/api/v1/folders/{f.folder_id}", {"name": "x", "row_version": 0}),
    ),
    ("POST", "/api/v1/folders/{folder_id}/move"): Entry(
        "project:folder.manage",
        lambda f: ("POST", f"/api/v1/folders/{f.folder_id}/move", {"parent_id": None, "row_version": 0}),
    ),
    ("POST", "/api/v1/folders/{folder_id}/archive"): Entry(
        "project:folder.manage", lambda f: ("POST", f"/api/v1/folders/{_folder(f)}/archive", None)
    ),
    ("POST", "/api/v1/folders/{folder_id}/restore"): Entry(
        "project:folder.manage", lambda f: ("POST", f"/api/v1/folders/{_folder(f)}/restore", None)
    ),
    ("DELETE", "/api/v1/folders/{folder_id}"): Entry(
        "project:folder.manage", lambda f: ("DELETE", f"/api/v1/folders/{_folder(f)}", None)
    ),
    # test cases (M2)
    ("GET", P + "/test-cases"): Entry("project:project.view", lambda f: ("GET", _p(f, "/test-cases"), None)),
    ("POST", P + "/test-cases"): Entry(
        "project:testcase.create",
        lambda f: ("POST", _p(f, "/test-cases"), {"folder_id": str(f.folder_id), "content": _content()}),
    ),
    ("POST", P + "/test-cases/bulk"): Entry(
        "project:testcase.edit",
        lambda f: (
            "POST",
            _p(f, "/test-cases/bulk"),
            {"action": "set_priority", "case_ids": [], "params": {}},
        ),
    ),
    ("GET", P + "/resolve"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, f"/resolve?key={f.case_key}"), None)
    ),
    ("GET", TC): Entry("project:project.view", lambda f: ("GET", _tc(f), None)),
    ("PATCH", TC): Entry(
        "project:testcase.edit", lambda f: ("PATCH", _tc(f), {"priority": "high", "row_version": 0})
    ),
    ("DELETE", TC): Entry("project:testcase.delete", lambda f: ("DELETE", _tc(f, case_id=_case(f)), None)),
    ("PUT", TC + "/content"): Entry(
        "project:testcase.edit",
        lambda f: ("PUT", _tc(f, "/content"), {"content": _content(), "row_version": 0}),
    ),
    ("GET", TC + "/versions"): Entry("project:project.view", lambda f: ("GET", _tc(f, "/versions"), None)),
    ("GET", TC + "/versions/{version_no}"): Entry(
        "project:project.view", lambda f: ("GET", _tc(f, "/versions/1"), None)
    ),
    ("GET", TC + "/compare"): Entry(
        "project:project.view", lambda f: ("GET", _tc(f, "/compare?from=1&to=1"), None)
    ),
    ("POST", TC + "/restore-version"): Entry(
        "project:testcase.edit",
        lambda f: ("POST", _tc(f, "/restore-version"), {"version_no": 1, "row_version": 0}),
    ),
    ("POST", TC + "/submit"): Entry(
        "project:testcase.edit", lambda f: ("POST", _tc(f, "/submit", _case(f)), {})
    ),
    ("POST", TC + "/approve"): Entry(
        "project:testcase.approve", lambda f: ("POST", _tc(f, "/approve"), {"row_version": 0})
    ),
    ("POST", TC + "/return"): Entry(
        "project:testcase.approve", lambda f: ("POST", _tc(f, "/return"), {"comment": "probe"})
    ),
    ("POST", TC + "/deprecate"): Entry(
        "project:testcase.archive", lambda f: ("POST", _tc(f, "/deprecate", _case(f)), {})
    ),
    ("POST", TC + "/archive"): Entry(
        "project:testcase.archive", lambda f: ("POST", _tc(f, "/archive", _case(f)), {})
    ),
    ("POST", TC + "/restore"): Entry(
        "project:testcase.archive", lambda f: ("POST", _tc(f, "/restore", _case(f)), {})
    ),
    ("POST", TC + "/duplicate"): Entry(
        "project:testcase.create", lambda f: ("POST", _tc(f, "/duplicate"), {})
    ),
    ("GET", TC + "/executions"): Entry(
        "project:project.view", lambda f: ("GET", _tc(f, "/executions"), None)
    ),
    ("GET", TC + "/history"): Entry("project:project.view", lambda f: ("GET", _tc(f, "/history"), None)),
    ("POST", TC + "/links"): Entry(
        "project:testcase.edit",
        lambda f: ("POST", _tc(f, "/links", _case(f)), {"target_case_id": str(f.case_id)}),
    ),
    ("DELETE", TC + "/links"): Entry(
        "project:testcase.edit",
        lambda f: (lambda a, b: ("DELETE", _tc(f, "/links", a), {"target_case_id": str(b)}))(
            *_linked_pair(f)
        ),
    ),
    # tags (M2)
    ("GET", P + "/tags"): Entry("project:project.view", lambda f: ("GET", _p(f, "/tags"), None)),
    ("POST", P + "/tags"): Entry(
        "project:testcase.edit", lambda f: ("POST", _p(f, "/tags"), {"name": "probe"})
    ),
    ("DELETE", "/api/v1/tags/{tag_id}"): Entry(
        "project:testcase.edit", lambda f: ("DELETE", f"/api/v1/tags/{_tag(f)}", None)
    ),
    # comments and attachments (M2): author-only edits and multipart uploads have dedicated tests
    ("GET", "/api/v1/comments"): Entry(
        "project:project.view",
        lambda f: ("GET", f"/api/v1/comments?entity_type=test_case&entity_id={f.case_id}", None),
    ),
    ("POST", "/api/v1/comments"): Entry(
        "project:comment.create",
        lambda f: (
            "POST",
            "/api/v1/comments",
            {"entity_type": "test_case", "entity_id": str(f.case_id), "body": "probe"},
        ),
    ),
    ("PATCH", "/api/v1/comments/{comment_id}"): Entry("project:comment.create"),
    ("DELETE", "/api/v1/comments/{comment_id}"): Entry("project:comment.create"),
    ("POST", "/api/v1/attachments"): Entry("project:testcase.edit"),
    ("GET", "/api/v1/attachments/{attachment_id}"): Entry("project:project.view"),
    ("GET", "/api/v1/attachments/{attachment_id}/content"): Entry("project:project.view"),
    ("DELETE", "/api/v1/attachments/{attachment_id}/links/{entity_type}/{entity_id}"): Entry(
        "project:testcase.edit"
    ),
    # test plans (M3 / E07)
    ("GET", P + "/test-plans"): Entry("project:project.view", lambda f: ("GET", _p(f, "/test-plans"), None)),
    ("POST", P + "/test-plans"): Entry(
        "project:plan.manage",
        lambda f: ("POST", _p(f, "/test-plans"), {"name": "Probe plan", "type": "regression"}),
    ),
    ("GET", PL): Entry("project:project.view", lambda f: ("GET", PL.format(plan_id=_plan(f)), None)),
    ("PATCH", PL): Entry(
        "project:plan.manage",
        lambda f: ("PATCH", PL.format(plan_id=_plan(f)), {"name": "Renamed plan", "row_version": 1}),
    ),
    ("GET", PL + "/cases"): Entry(
        "project:project.view", lambda f: ("GET", PL.format(plan_id=_plan(f)) + "/cases", None)
    ),
    ("POST", PL + "/cases"): Entry(
        "project:plan.manage",
        lambda f: ("POST", PL.format(plan_id=_plan(f)) + "/cases", {"case_ids": []}),
    ),
    ("DELETE", PL + "/cases"): Entry(
        "project:plan.manage",
        lambda f: ("DELETE", PL.format(plan_id=_plan(f)) + "/cases", {"case_ids": [str(uuid.uuid4())]}),
    ),
    ("POST", PL + "/requirements"): Entry(
        "project:plan.manage",
        lambda f: (
            "POST",
            PL.format(plan_id=_plan(f)) + "/requirements",
            {"references": f"PRB-{uuid.uuid4().hex[:6]}"},
        ),
    ),
    ("DELETE", PL + "/requirements"): Entry(
        "project:plan.manage",
        lambda f: (
            "DELETE",
            PL.format(plan_id=_plan(f)) + "/requirements",
            {"requirement_ids": [str(uuid.uuid4())]},
        ),
    ),
    ("POST", PL + "/clone"): Entry(
        "project:plan.manage", lambda f: ("POST", PL.format(plan_id=_plan(f)) + "/clone", {})
    ),
    ("POST", PL + "/archive"): Entry(
        "project:plan.manage", lambda f: ("POST", PL.format(plan_id=_plan(f)) + "/archive", None)
    ),
    # cycles and runs (M3 / E08)
    ("GET", P + "/cycles"): Entry("project:project.view", lambda f: ("GET", _p(f, "/cycles"), None)),
    ("POST", P + "/cycles"): Entry(
        "project:cycle.manage",
        lambda f: (
            "POST",
            _p(f, "/cycles"),
            {"name": f"Probe cycle {uuid.uuid4().hex[:8]}", "environment_id": str(f.env_id), "selection": {}},
        ),
    ),
    ("GET", CY): Entry("project:project.view", lambda f: ("GET", CY.format(cycle_id=_cycle(f)), None)),
    ("PATCH", CY): Entry(
        "project:cycle.manage",
        lambda f: ("PATCH", CY.format(cycle_id=_cycle(f)), {"name": "Renamed cycle", "row_version": 1}),
    ),
    ("POST", CY + "/start"): Entry(
        "project:cycle.manage", lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/start", None)
    ),
    ("POST", CY + "/close"): Entry(
        "project:cycle.manage", lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/close", {})
    ),
    ("POST", CY + "/reopen"): Entry(
        "project:cycle.reopen",
        lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/reopen", {"reason": "probe"}),
    ),
    ("POST", CY + "/archive"): Entry(
        "project:cycle.manage", lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/archive", None)
    ),
    ("POST", CY + "/clone"): Entry(
        "project:cycle.manage",
        lambda f: (
            "POST",
            CY.format(cycle_id=_cycle(f)) + "/clone",
            {"name": f"Clone {uuid.uuid4().hex[:8]}"},
        ),
    ),
    ("POST", CY + "/sync-from-plan"): Entry(
        "project:cycle.manage", lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/sync-from-plan", None)
    ),
    ("GET", CY + "/runs"): Entry(
        "project:project.view", lambda f: ("GET", CY.format(cycle_id=_cycle(f)) + "/runs", None)
    ),
    ("POST", CY + "/runs"): Entry(
        "project:cycle.manage", lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/runs", {"case_ids": []})
    ),
    ("DELETE", CY + "/runs"): Entry("project:cycle.manage", lambda f: _remove_run_probe(f)),
    ("POST", CY + "/runs/assign"): Entry(
        "project:cycle.manage",
        lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/runs/assign", {"run_ids": [str(uuid.uuid4())]}),
    ),
    ("POST", CY + "/runs/reorder"): Entry(
        "project:cycle.manage",
        lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/runs/reorder", {"sort_by": "folder"}),
    ),
    ("POST", CY + "/runs/update-versions"): Entry(
        "project:cycle.manage",
        lambda f: ("POST", CY.format(cycle_id=_cycle(f)) + "/runs/update-versions", None),
    ),
    ("GET", RN): Entry(
        "project:project.view", lambda f: ("GET", RN.format(run_id=_run(f)) + "?include=version", None)
    ),
    ("POST", RN + "/claim"): Entry(
        "project:run.execute", lambda f: ("POST", RN.format(run_id=_run(f)) + "/claim", None)
    ),
    ("POST", RN + "/update-version"): Entry(
        "project:cycle.manage", lambda f: ("POST", RN.format(run_id=_run(f)) + "/update-version", None)
    ),
    ("POST", RN + "/replace"): Entry(
        "project:cycle.manage", lambda f: ("POST", RN.format(run_id=_run(f)) + "/replace", None)
    ),
    # result attempts and My Work (M4 / E09)
    ("GET", "/api/v1/me/work"): Entry("auth", lambda f: ("GET", "/api/v1/me/work", None)),
    ("POST", RN + "/results"): Entry(
        "project:run.execute", lambda f: ("POST", RN.format(run_id=_run(f)) + "/results", None)
    ),
    ("GET", RS): Entry("project:project.view", lambda f: ("GET", RS.format(result_id=_draft(f)[0]), None)),
    ("PATCH", RS): Entry(
        "project:cycle.manage",
        lambda f: ("PATCH", RS.format(result_id=_draft(f)[0]), {"comment": "probe"}),
    ),
    ("PATCH", RS + "/steps/{step_id}"): Entry(
        "project:cycle.manage",
        lambda f: (lambda r, st: ("PATCH", RS.format(result_id=r) + f"/steps/{st}", {"status": "passed"}))(
            *_draft(f)
        ),
    ),
    ("POST", RS + "/steps/bulk"): Entry(
        "project:cycle.manage",
        lambda f: (
            "POST",
            RS.format(result_id=_draft(f)[0]) + "/steps/bulk",
            {"status": "passed", "only_not_run": True},
        ),
    ),
    ("POST", RS + "/finalize"): Entry(
        "project:cycle.manage", lambda f: ("POST", RS.format(result_id=_draft(f)[0]) + "/finalize", {})
    ),
    # requirement references, coverage, traceability (M6 / E11, ADR-024)
    ("GET", P + "/requirements"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/requirements"), None)
    ),
    ("POST", P + "/requirements"): Entry(
        "project:requirement.manage",
        lambda f: ("POST", _p(f, "/requirements"), {"references": f"NEW-{uuid.uuid4().hex[:6]}"}),
    ),
    ("POST", P + "/requirements/link-cases"): Entry(
        "project:requirement.link",
        lambda f: (
            "POST",
            _p(f, "/requirements/link-cases"),
            {"references": f"LNK-{uuid.uuid4().hex[:6]}", "test_case_ids": [str(f.case_id)]},
        ),
    ),
    ("GET", RQ): Entry("project:project.view", lambda f: ("GET", RQ.format(ref_id=_requirement(f)), None)),
    ("PATCH", RQ): Entry(
        "project:requirement.manage",
        lambda f: ("PATCH", RQ.format(ref_id=_requirement(f)), {"title": "Probe"}),
    ),
    ("POST", RQ + "/archive"): Entry(
        "project:requirement.manage", lambda f: ("POST", RQ.format(ref_id=_requirement(f)) + "/archive", None)
    ),
    ("POST", RQ + "/restore"): Entry(
        "project:requirement.manage", lambda f: ("POST", RQ.format(ref_id=_requirement(f)) + "/restore", None)
    ),
    ("POST", RQ + "/test-cases"): Entry(
        "project:requirement.link",
        lambda f: (
            "POST",
            RQ.format(ref_id=_requirement(f)) + "/test-cases",
            {"test_case_ids": [str(f.case_id)]},
        ),
    ),
    ("DELETE", RQ + "/test-cases/{case_id}"): Entry(
        "project:requirement.link",
        lambda f: (
            "DELETE",
            RQ.format(ref_id=_requirement(f, linked=True)) + f"/test-cases/{f.case_id}",
            None,
        ),
    ),
    ("GET", TC + "/requirements"): Entry(
        "project:project.view", lambda f: ("GET", _tc(f, "/requirements"), None)
    ),
    ("POST", TC + "/requirements"): Entry(
        "project:requirement.link",
        lambda f: ("POST", _tc(f, "/requirements"), {"references": f"CSE-{uuid.uuid4().hex[:6]}"}),
    ),
    ("GET", P + "/coverage"): Entry("project:project.view", lambda f: ("GET", _p(f, "/coverage"), None)),
    ("GET", P + "/traceability"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/traceability"), None)
    ),
    # reporting, readiness, decisions, exports (M7 / E13)
    ("GET", P + "/release-summaries"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/release-summaries"), None)
    ),
    ("GET", "/api/v1/releases/{release_id}/readiness"): Entry(
        "project:project.view", lambda f: ("GET", f"/api/v1/releases/{f.release_id}/readiness", None)
    ),
    ("GET", "/api/v1/releases/{release_id}/decisions"): Entry(
        "project:project.view", lambda f: ("GET", f"/api/v1/releases/{f.release_id}/decisions", None)
    ),
    ("POST", "/api/v1/releases/{release_id}/decisions"): Entry(
        "project:release.manage",
        lambda f: (
            "POST",
            f"/api/v1/releases/{f.release_id}/decisions",
            {"decision": "go_with_risks", "comment": "x"},
        ),
    ),
    ("GET", PL + "/readiness"): Entry(
        "project:project.view", lambda f: ("GET", PL.format(plan_id=_plan(f)) + "/readiness", None)
    ),
    ("GET", P + "/execution-summary"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/execution-summary"), None)
    ),
    ("GET", P + "/dashboards/manager"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/dashboards/manager"), None)
    ),
    ("GET", P + "/dashboards/quality"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/dashboards/quality"), None)
    ),
    ("POST", P + "/metrics/refresh"): Entry(
        "project:project.view", lambda f: ("POST", _p(f, "/metrics/refresh"), None)
    ),
    ("GET", "/api/v1/organization/dashboard"): Entry(
        "auth", lambda f: ("GET", "/api/v1/organization/dashboard", None)
    ),
    ("GET", P + "/reports/{report}"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/reports/case-inventory"), None)
    ),
    ("POST", P + "/reports/{report}/export"): Entry(
        "project:data.export",
        lambda f: ("POST", _p(f, "/reports/tester-activity/export"), {"format": "csv", "filters": {}}),
    ),
    # Initiator only (any member may start an export): covered by test_ac_rpt_04_large_export_runs_in_the_background.
    ("GET", "/api/v1/data-transfers/{transfer_id}"): Entry("project:project.view"),
    ("GET", "/api/v1/data-transfers/{transfer_id}/download"): Entry("project:project.view"),
    # search and saved views (M6 / E12)
    ("GET", "/api/v1/search"): Entry("auth", lambda f: ("GET", "/api/v1/search?q=probe", None)),
    ("GET", P + "/saved-views"): Entry(
        "project:project.view", lambda f: ("GET", _p(f, "/saved-views"), None)
    ),
    ("POST", P + "/saved-views"): Entry(
        "project:project.view",
        lambda f: (
            "POST",
            _p(f, "/saved-views"),
            {"entity_type": "test_case", "name": f"V {uuid.uuid4().hex[:8]}", "definition": {"filters": {}}},
        ),
    ),
    # Owner-only (any member may own views): covered by test_tcms_120_saved_views_private_shared_and_defaults.
    ("PATCH", "/api/v1/saved-views/{view_id}"): Entry("project:project.view"),
    ("DELETE", "/api/v1/saved-views/{view_id}"): Entry("project:project.view"),
    # bug links (M5 / E10, ADR-023)
    ("POST", RS + "/bug-links"): Entry(
        "project:defect.create",
        lambda f: ("POST", RS.format(result_id=_draft(f)[0]) + "/bug-links", {"reference": "PRB-1"}),
    ),
    ("GET", RS + "/bug-report"): Entry(
        "project:project.view", lambda f: ("GET", RS.format(result_id=_draft(f)[0]) + "/bug-report", None)
    ),
    ("POST", TC + "/bug-links"): Entry(
        "project:defect.create",
        lambda f: ("POST", _tc(f, "/bug-links", _case(f)), {"reference": "PRB-2"}),
    ),
    ("GET", TC + "/bug-links"): Entry("project:project.view", lambda f: ("GET", _tc(f, "/bug-links"), None)),
    ("GET", RN + "/bug-links"): Entry(
        "project:project.view", lambda f: ("GET", RN.format(run_id=_run(f)) + "/bug-links", None)
    ),
    ("GET", CY + "/bug-links"): Entry(
        "project:project.view", lambda f: ("GET", CY.format(cycle_id=_cycle(f)) + "/bug-links", None)
    ),
    ("PATCH", "/api/v1/bug-links/{link_id}"): Entry(
        "project:defect.edit",
        lambda f: ("PATCH", f"/api/v1/bug-links/{_bug_link(f)[0]}", {"title": "probe"}),
    ),
    ("DELETE", "/api/v1/bug-links/{link_id}"): Entry(
        "project:defect.edit", lambda f: ("DELETE", f"/api/v1/bug-links/{_bug_link(f)[0]}", None)
    ),
    ("GET", P + "/bugs"): Entry("project:project.view", lambda f: ("GET", _p(f, "/bugs"), None)),
    ("GET", P + "/bugs/links"): Entry(
        "project:project.view",
        lambda f: ("GET", _p(f, "/bugs/links") + f"?reference={_bug_link(f)[1]}", None),
    ),
    ("POST", P + "/bugs/retest"): Entry(
        "project:cycle.manage",
        lambda f: ("POST", _p(f, "/bugs/retest"), {"reference": _bug_link(f)[1], "dry_run": True}),
    ),
    ("DELETE", RS): Entry(
        "project:cycle.manage", lambda f: ("DELETE", RS.format(result_id=_draft(f)[0]), None)
    ),
}
