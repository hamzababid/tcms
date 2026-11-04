"""Permission catalog and default role map (docs/02 §3.1, §3.2).

This is the code source of truth. `docs/schema/02_seed_system.sql` seeds the same map into the
database; `tests/integration/test_role_permissions_match_seed.py` asserts they are identical.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Scope(StrEnum):
    org = "org"
    project = "project"


# permission -> scope. Phase 2 permissions are reserved (not granted to anyone in the MVP).
CATALOG: Final[dict[str, Scope]] = {
    "org.manage": Scope.org,
    "org.users.manage": Scope.org,
    "org.roles.manage": Scope.org,  # P2
    "org.integrations.manage": Scope.org,  # P2
    "org.audit.view": Scope.org,
    "org.reports.view": Scope.org,
    "project.create": Scope.org,
    "project.view": Scope.project,
    "project.configure": Scope.project,
    "project.members.manage": Scope.project,
    "project.audit.view": Scope.project,
    "folder.manage": Scope.project,
    "testcase.create": Scope.project,
    "testcase.edit": Scope.project,
    "testcase.approve": Scope.project,
    "testcase.archive": Scope.project,
    "testcase.delete": Scope.project,
    "plan.manage": Scope.project,
    "cycle.manage": Scope.project,
    "cycle.reopen": Scope.project,
    "run.execute": Scope.project,
    "defect.create": Scope.project,
    "defect.edit": Scope.project,
    "defect.transition.any": Scope.project,
    "defect.transition.dev": Scope.project,
    "defect.transition.verify": Scope.project,
    "requirement.manage": Scope.project,
    "requirement.link": Scope.project,
    "release.manage": Scope.project,
    "data.export": Scope.project,
    "comment.create": Scope.project,
}

RESERVED_P2: Final[frozenset[str]] = frozenset({"org.roles.manage", "org.integrations.manage"})

ORG_PERMISSIONS: Final[frozenset[str]] = frozenset(p for p, s in CATALOG.items() if s is Scope.org)
PROJECT_PERMISSIONS: Final[frozenset[str]] = frozenset(p for p, s in CATALOG.items() if s is Scope.project)


class RoleCode(StrEnum):
    qa_manager = "qa_manager"
    qa_lead = "qa_lead"
    qa_engineer = "qa_engineer"
    developer = "developer"
    pm_ba = "pm_ba"
    viewer = "viewer"


_ALL = PROJECT_PERMISSIONS
_VIEW = {"project.view", "data.export"}

ROLE_PERMISSIONS: Final[dict[RoleCode, frozenset[str]]] = {
    RoleCode.qa_manager: frozenset(_ALL - {"defect.transition.dev", "defect.transition.verify"}),
    RoleCode.qa_lead: frozenset(
        _VIEW
        | {
            "folder.manage",
            "testcase.create",
            "testcase.edit",
            "testcase.approve",
            "testcase.archive",
            "plan.manage",
            "cycle.manage",
            "run.execute",
            "defect.create",
            "defect.edit",
            "defect.transition.any",
            "requirement.link",
            "comment.create",
        }
    ),
    RoleCode.qa_engineer: frozenset(
        _VIEW
        | {
            "testcase.create",
            "testcase.edit",
            "run.execute",
            "defect.create",
            "defect.edit",
            "defect.transition.verify",
            "requirement.link",
            "comment.create",
        }
    ),
    RoleCode.developer: frozenset(
        _VIEW | {"defect.create", "defect.edit", "defect.transition.dev", "comment.create"}
    ),
    RoleCode.pm_ba: frozenset(_VIEW | {"requirement.manage", "requirement.link", "comment.create"}),
    RoleCode.viewer: frozenset(_VIEW),
}

# Fixed IDs of the seeded system roles (02_seed_system.sql).
SYSTEM_ROLE_IDS: Final[dict[RoleCode, str]] = {
    RoleCode.qa_manager: "00000000-0000-7000-8000-000000000001",
    RoleCode.qa_lead: "00000000-0000-7000-8000-000000000002",
    RoleCode.qa_engineer: "00000000-0000-7000-8000-000000000003",
    RoleCode.developer: "00000000-0000-7000-8000-000000000004",
    RoleCode.pm_ba: "00000000-0000-7000-8000-000000000005",
    RoleCode.viewer: "00000000-0000-7000-8000-000000000006",
}

# Org Admin: every permission except reserved Phase 2 ones (docs/02 §3.2).
ORG_ADMIN_PERMISSIONS: Final[frozenset[str]] = frozenset(CATALOG) - RESERVED_P2

# Token scopes intersect permissions (docs/02 §3.4): a `read` token may only view.
READ_ONLY_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {"project.view", "project.audit.view", "org.audit.view", "org.reports.view"}
)
