"""The code role map equals the table in docs/02 §3.2 (independent oracle transcribed from the spec)."""

from __future__ import annotations

from tcms.core.permissions import (
    CATALOG,
    ORG_ADMIN_PERMISSIONS,
    PROJECT_PERMISSIONS,
    RESERVED_P2,
    ROLE_PERMISSIONS,
    RoleCode,
)

# Columns: QA Manager, QA Lead, QA Engineer, Developer, PM/BA, Viewer (docs/02 §3.2, ✓ = 1).
SPEC_TABLE = """
project.view              1 1 1 1 1 1
project.configure         1 0 0 0 0 0
project.members.manage    1 0 0 0 0 0
project.audit.view        1 0 0 0 0 0
folder.manage             1 1 0 0 0 0
testcase.create           1 1 1 0 0 0
testcase.edit             1 1 1 0 0 0
testcase.approve          1 1 0 0 0 0
testcase.archive          1 1 0 0 0 0
testcase.delete           1 0 0 0 0 0
plan.manage               1 1 0 0 0 0
cycle.manage              1 1 0 0 0 0
cycle.reopen              1 0 0 0 0 0
run.execute               1 1 1 0 0 0
defect.create             1 1 1 1 0 0
defect.edit               1 1 1 1 0 0
defect.transition.any     1 1 0 0 0 0
defect.transition.dev     0 0 0 1 0 0
defect.transition.verify  0 0 1 0 0 0
requirement.manage        1 0 0 0 1 0
requirement.link          1 1 1 0 1 0
release.manage            1 0 0 0 0 0
data.export               1 1 1 1 1 1
comment.create            1 1 1 1 1 0
"""
ORDER = [
    RoleCode.qa_manager,
    RoleCode.qa_lead,
    RoleCode.qa_engineer,
    RoleCode.developer,
    RoleCode.pm_ba,
    RoleCode.viewer,
]


def _spec() -> dict[RoleCode, set[str]]:
    out: dict[RoleCode, set[str]] = {r: set() for r in ORDER}
    for line in SPEC_TABLE.strip().splitlines():
        perm, *flags = line.split()
        for role, flag in zip(ORDER, flags, strict=True):
            if flag == "1":
                out[role].add(perm)
    return out


def test_role_map_matches_functional_spec_table() -> None:
    assert {r: set(p) for r, p in ROLE_PERMISSIONS.items()} == _spec()


def test_spec_table_covers_every_project_permission() -> None:
    perms = {line.split()[0] for line in SPEC_TABLE.strip().splitlines()}
    assert perms == PROJECT_PERMISSIONS


def test_roles_grant_only_project_permissions() -> None:
    for perms in ROLE_PERMISSIONS.values():
        assert perms <= PROJECT_PERMISSIONS


def test_org_admin_holds_everything_except_reserved_phase_2() -> None:
    assert frozenset(CATALOG) - RESERVED_P2 == ORG_ADMIN_PERMISSIONS
    assert not (ORG_ADMIN_PERMISSIONS & RESERVED_P2)
