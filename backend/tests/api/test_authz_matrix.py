"""TCMS-012: the authorization matrix holds for every route × caller (docs/08 §7)."""

from __future__ import annotations

from typing import Any

import pytest

from tcms.core.permissions import ROLE_PERMISSIONS, RoleCode
from tests.api.authz_matrix import MATRIX, Entry, Fixture
from tests.world import ApiClient, World

pytestmark = pytest.mark.integration

DENIED = {401, 403, 404}


def test_every_route_is_in_the_matrix(app: Any) -> None:
    routes = {(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops}
    assert routes - set(MATRIX) == set(), "routes missing from tests/api/authz_matrix.py"
    assert set(MATRIX) - routes == set(), "matrix lists routes that do not exist"


@pytest.fixture(scope="module")
def fx(world: World) -> Fixture:
    org = world.org()
    pid = world.project(org, "AUTHZ")
    team = world.team(org, pid)
    admin = world.login(org.admin)
    env_id = admin.get(f"/api/v1/projects/{pid}/environments").json()[0]["id"]
    rel = admin.post(f"/api/v1/projects/{pid}/releases", json={"name": "R1"}).json()
    folder_id = world.folder(org, pid, "Probe root")
    case_id, case_key = world.case(org, pid, folder_id)
    return Fixture(world, org, pid, team, env_id, rel["id"], rel["row_version"], folder_id, case_id, case_key)


@pytest.fixture(scope="module")
def callers(fx: Fixture) -> dict[str, ApiClient]:
    w = fx.world
    out = {role: w.login(user) for role, user in fx.team.items()}
    out["org_admin"] = w.login(fx.org.admin)
    out["non_member"] = w.login(w.user(fx.org, "Outsider"))
    other = w.org("Other org")
    out["other_org_admin"] = w.login(other.admin)
    return out


def _expected_allowed(entry: Entry, caller: str, path: str) -> bool | None:
    """True/False for allowed/denied; None when the expected denial is 404 (not visible)."""
    kind, _, perm = entry.kind.partition(":")
    if kind == "auth":
        return True
    if caller == "org_admin":
        return True
    if caller == "other_org_admin":
        # Admin of another organization: allowed on its own org; anything naming our IDs is invisible.
        return None if kind == "project" or "{" in path else True
    if kind == "org":
        if perm == "project.create":
            return caller == "qa_manager"  # QA Manager in at least one project (docs/02 §3.2)
        return False
    if caller == "non_member":
        return None
    return perm in ROLE_PERMISSIONS[RoleCode(caller)]


CALLERS = [r.value for r in RoleCode] + ["org_admin", "non_member", "other_org_admin"]
PROBED = sorted((k for k, e in MATRIX.items() if e.probe is not None), key=str)


@pytest.mark.parametrize("route", PROBED, ids=lambda r: f"{r[0]} {r[1]}")
def test_route_permissions(route: tuple[str, str], fx: Fixture, callers: dict[str, ApiClient]) -> None:
    entry = MATRIX[route]
    assert entry.probe is not None
    failures = []
    for caller in CALLERS:
        method, url, body = entry.probe(fx)
        response = callers[caller].request(method, url, json=body)
        expected = _expected_allowed(entry, caller, route[1])
        code = response.status_code
        if expected is True and code in DENIED:
            failures.append(f"{caller}: expected allowed, got {code} {response.text[:120]}")
        elif expected is False and code != 403:
            failures.append(f"{caller}: expected 403, got {code}")
        elif expected is None and code != 404:
            failures.append(f"{caller}: expected 404, got {code}")
    assert not failures, "\n".join(failures)
