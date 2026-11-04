"""Seed steps for local development and E2E (docs/04 §2, docs/08 §3). Written through services only.

Credentials are documented in docs/ops/local-setup.md. They are for local machines only; the dev TOTP
secret is refused in production (`enroll_mfa_with_secret`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from tcms.core.config import get_settings
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.db import app_engine, session_factory
from tcms.core.enums import ReleaseStatus
from tcms.core.permissions import RoleCode
from tcms.core.uow import unit_of_work
from tcms.identity import service as identity
from tcms.seed import step
from tcms.workspace import queries as workspace_queries
from tcms.workspace import service as workspace

SEED_PASSWORD = "Passw0rd!Passw0rd"  # noqa: S105 — documented local seed credential
DEV_TOTP_SECRET = "ASSAYLOCALDEVTOTPSECRETONLY23456"  # noqa: S105 — documented local-only MFA secret
ORG_SLUG = "acme"


@dataclass(frozen=True)
class Person:
    name: str
    email: str
    role: RoleCode


TEAM = (
    Person("Ayesha Raza", "ayesha@acme.test", RoleCode.qa_manager),
    Person("Bilal Khan", "bilal@acme.test", RoleCode.qa_lead),
    Person("Sana Malik", "sana@acme.test", RoleCode.qa_engineer),
    Person("Omar Farooq", "omar@acme.test", RoleCode.developer),
    Person("Hira Siddiqui", "hira@acme.test", RoleCode.pm_ba),
    Person("Faisal Ahmed", "faisal@acme.test", RoleCode.viewer),
)
ADMIN = Person("Zain Ali", "zain@acme.test", RoleCode.qa_manager)
META = RequestMeta("seed")


def _ctx(
    org_id: UUID, user_id: UUID, *, project_id: UUID | None = None, perms: frozenset[str] = frozenset()
) -> AccessContext:
    return AccessContext.for_principal(
        Principal(user_id, org_id, True, display_name=ADMIN.name),
        META,
        project_id=project_id,
        permissions=perms,
    )


def _project(
    factory: object, org_id: UUID, admin_id: UUID, key: str, name: str, users: dict[str, UUID]
) -> str:
    with unit_of_work(factory) as uow:  # type: ignore[arg-type]
        policy = workspace_queries.org_policy(uow.session, org_id)
        p = workspace.create_project(
            uow,
            _ctx(org_id, admin_id, perms=frozenset({"project.create"})),
            key=key,
            name=name,
            description=None,
            policy=policy,
        )
        pctx = _ctx(
            org_id,
            admin_id,
            project_id=p.id,
            perms=frozenset({"project.members.manage", "project.configure", "release.manage"}),
        )
        pctx.project_status = "active"
        for person in TEAM:
            identity.add_member(uow, pctx, user_id=users[person.email], role_code=person.role.value)
        for env in ("Dev", "UAT"):
            workspace.create_environment(uow, pctx, name=env, description=None)
        current = workspace.create_release(
            uow,
            pctx,
            name=f"{key} v2.5",
            description="Regression and release validation",
            start_date=date(2026, 11, 3),
            target_date=date(2026, 11, 14),
        )
        workspace.update_release(
            uow, pctx, current.id, row_version=current.row_version, fields={"status": ReleaseStatus.active}
        )
        workspace.create_release(
            uow,
            pctx,
            name=f"{key} v2.6",
            description=None,
            start_date=date(2026, 12, 1),
            target_date=date(2026, 12, 19),
        )
    return key


def _seed(profile: str) -> str:
    settings = get_settings()
    factory = session_factory(app_engine(settings))
    with factory() as s:
        if workspace_queries.organization_by_slug(s, ORG_SLUG) is not None:
            return "organization 'acme' already exists — nothing to do"
    with unit_of_work(factory) as uow:
        org = workspace.create_organization(uow, name="ACME Energy", slug=ORG_SLUG)
        invites = {
            ADMIN.email: identity.bootstrap_admin_invitation(
                uow, settings, organization_id=org.id, email=ADMIN.email
            )
        }
        org_id = org.id
    users: dict[str, UUID] = {}
    for person in (ADMIN, *TEAM):
        with unit_of_work(factory) as uow:
            if person is not ADMIN:
                ctx = _ctx(org_id, users[ADMIN.email], perms=frozenset({"org.users.manage"}))
                invites[person.email] = identity.create_invitation(uow, settings, ctx, email=person.email)
        token = invites[person.email].accept_url.rsplit("/", 1)[1]
        with unit_of_work(factory) as uow:
            accepted = identity.accept_invitation(
                uow,
                token=token,
                display_name=person.name,
                password=SEED_PASSWORD,
                time_zone="Asia/Karachi",
                meta=META,
                policy_for=lambda o: workspace_queries.org_policy(uow.session, o),
            )
        users[person.email] = accepted.user_id
    with unit_of_work(factory) as uow:
        identity.enroll_mfa_with_secret(uow, settings, _ctx(org_id, users[ADMIN.email]), DEV_TOTP_SECRET)
    keys = [_project(factory, org_id, users[ADMIN.email], "SPARK", "SPARK Platform", users)]
    if profile == "e2e":
        keys.append(_project(factory, org_id, users[ADMIN.email], "HELIOS", "HELIOS Analytics", users))
    return f"ACME Energy with {len(users)} users and projects {', '.join(keys)}"


@step("organization, users and projects", profiles=("dev", "e2e"))
def seed_workspace(profile: str) -> str:
    return _seed(profile)
