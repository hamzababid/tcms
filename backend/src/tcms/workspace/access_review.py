"""Access review (FR-AUD-004, docs/02 §13.3, TCMS-133): one row per user × scope.

Every organization member has an organization row (role "Org admin" or "Member"); each project
membership adds a project row. Deactivated users stay in the review so their past access is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy.orm import Session

from tcms.identity import queries as identity_queries
from tcms.workspace import repository as repo

HEADER: Final = [
    "Email",
    "Name",
    "Active",
    "Org admin",
    "MFA enrolled",
    "Project",
    "Role",
    "Granted by",
    "Granted at",
    "Last sign-in",
]
KINDS: Final = ["text", "text", "text", "text", "text", "text", "text", "text", "datetime", "datetime"]


@dataclass(frozen=True)
class AccessRow:
    user_id: UUID
    email: str
    name: str
    active: bool
    org_admin: bool
    mfa_enrolled: bool
    project_id: UUID | None  # None: the organization row
    project_key: str | None
    project_name: str | None
    role_code: str  # org_admin | org_member | a project role code
    role_name: str
    granted_by: str | None  # display name
    granted_at: datetime | None
    last_sign_in: datetime | None

    def as_cells(self) -> list[object]:
        return [
            self.email,
            self.name,
            "yes" if self.active else "no",
            "yes" if self.org_admin else "no",
            "yes" if self.mfa_enrolled else "no",
            f"{self.project_key} · {self.project_name}" if self.project_key else "(organization)",
            self.role_name,
            self.granted_by or "",
            self.granted_at,
            self.last_sign_in,
        ]


def rows(s: Session, org_id: UUID) -> list[AccessRow]:
    members = identity_queries.org_members(s, org_id)
    memberships = identity_queries.org_memberships(s, org_id)
    projects = {p.id: p for p in repo.projects(s, org_id, ids=None, status=None)}
    granters = {m.granted_by for m in members if m.granted_by} | {
        r.granted_by for rs in memberships.values() for r in rs if r.granted_by
    }
    names = {uid: u.display_name for uid, u in identity_queries.user_refs(s, granters).items()}
    out: list[AccessRow] = []
    for m in members:
        u = m.user
        common = (u.id, u.email, u.display_name, u.is_active, m.is_org_admin, m.mfa_enrolled)
        out.append(
            AccessRow(
                *common,
                project_id=None,
                project_key=None,
                project_name=None,
                role_code="org_admin" if m.is_org_admin else "org_member",
                role_name="Org admin" if m.is_org_admin else "Member",
                granted_by=names.get(m.granted_by) if m.granted_by else None,
                granted_at=m.joined_at,
                last_sign_in=m.last_login_at,
            )
        )
        project_rows = sorted(
            memberships.get(u.id, []),
            key=lambda r: projects[r.project_id].key if r.project_id in projects else "",
        )
        for r in project_rows:
            p = projects.get(r.project_id)
            out.append(
                AccessRow(
                    *common,
                    project_id=r.project_id,
                    project_key=p.key if p else None,
                    project_name=p.name if p else None,
                    role_code=r.role_code,
                    role_name=r.role_name,
                    granted_by=names.get(r.granted_by) if r.granted_by else None,
                    granted_at=r.granted_at,
                    last_sign_in=m.last_login_at,
                )
            )
    return out
