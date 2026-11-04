"""Workspace (docs/08 §15.2: TCMS-013, 020…025a; BR-16, BR-25, BR-27, BR-29; US-028, US-161)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tcms.core import clock
from tcms.core.uow import unit_of_work
from tcms.workspace import service as workspace
from tests.world import World

pytestmark = pytest.mark.integration


def _rows(world: World, sql: str, **params: Any) -> list[Any]:
    with world.factory() as s:
        return list(s.execute(text(sql), params).all())


def test_tcms_020_create_project_creator_is_qa_manager(world: World) -> None:
    org = world.org()
    lead = world.user(org, "Ayesha")
    seed = world.project(org, "SEED")
    world.member(org, seed, lead, "qa_manager")  # QA Manager somewhere → may create (docs/02 §3.2)
    c = world.login(lead)
    r = c.post("/api/v1/projects", json={"key": "SPARK", "name": "SPARK Platform", "description": "Energy"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["settings"]["approval_required"] is False
    members = c.get(f"/api/v1/projects/{p['id']}/members").json()
    assert [(m["user"]["id"], m["role"]["code"]) for m in members] == [(str(lead.id), "qa_manager")]
    assert {e["name"] for e in c.get(f"/api/v1/projects/{p['id']}/environments").json()} == {"QA", "Staging"}
    tags = _rows(world, "SELECT name FROM tags WHERE project_id = :p AND is_system ORDER BY name", p=p["id"])
    assert [t[0] for t in tags] == ["regression", "sanity", "smoke"]
    seqs = _rows(
        world, "SELECT entity, next_value FROM key_sequences WHERE project_id = :p ORDER BY entity", p=p["id"]
    )
    assert seqs == [("defect", 1), ("requirement", 1), ("test_case", 1), ("test_cycle", 1), ("test_plan", 1)]
    assert c.get(f"/api/v1/projects/{p['id']}").json()["counts"] == {
        "members": 1,
        "environments": 2,
        "releases": 0,
    }


def test_project_create_requires_permission(world: World) -> None:
    org = world.org()
    c = world.login(world.user(org, "Nobody"))
    r = c.post("/api/v1/projects", json={"key": "NOPE", "name": "Nope"})
    assert r.status_code == 403
    assert r.json()["required_permission"] == "project.create"


@pytest.mark.parametrize("key", ["S", "1SPARK", "SPARK_X", "TOOLONGKEY1", "SP ARK"])
def test_br_27_project_key_format(world: World, key: str) -> None:
    """TCMS-021: invalid → 422."""
    org = world.org()
    r = world.login(org.admin).post("/api/v1/projects", json={"key": key, "name": f"P {key}"})
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "key"


def test_tcms_021_key_unique_case_insensitive_and_name_unique(world: World) -> None:
    org = world.org()
    c = world.login(org.admin)
    assert c.post("/api/v1/projects", json={"key": "SPARK", "name": "One"}).status_code == 201
    assert (
        c.post("/api/v1/projects", json={"key": "spark", "name": "Two"}).json()["code"] == "project_key_taken"
    )
    assert c.post("/api/v1/projects", json={"key": "OTHER", "name": "one"}).json()["code"] == "name_taken"
    other = world.org("Other org")
    assert (
        world.login(other.admin).post("/api/v1/projects", json={"key": "SPARK", "name": "One"}).status_code
        == 201
    )


def test_tcms_022_archived_project_is_read_only(world: World) -> None:
    """AC-WS-02."""
    org = world.org()
    pid = world.project(org, "ARCH")
    c = world.login(org.admin)
    assert (
        c.post(f"/api/v1/projects/{pid}/archive", json={"confirm_key": "WRONG"}).json()["code"]
        == "confirmation_mismatch"
    )
    r = c.post(f"/api/v1/projects/{pid}/archive", json={"confirm_key": "arch"})
    assert r.status_code == 200
    assert r.json()["status"] == "archived"
    for method, url, body in [
        ("post", f"/api/v1/projects/{pid}/environments", {"name": "UAT"}),
        ("patch", f"/api/v1/projects/{pid}", {"name": "X", "row_version": r.json()["row_version"]}),
        ("post", f"/api/v1/projects/{pid}/releases", {"name": "v1"}),
    ]:
        resp = getattr(c, method)(url, json=body)
        assert resp.status_code == 409, url
        assert resp.json()["code"] == "project_archived"
    assert c.get(f"/api/v1/projects/{pid}").status_code == 200  # reads still work
    assert c.post(f"/api/v1/projects/{pid}/restore").json()["status"] == "active"


def test_br_29_new_member_defaults_to_viewer(world: World) -> None:
    org = world.org()
    pid = world.project(org, "MEM")
    user = world.user(org, "Faisal")
    c = world.login(org.admin)
    r = c.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(user.id)})
    assert r.status_code == 201, r.text
    assert r.json()["role"]["code"] == "viewer"
    assert (
        c.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(user.id)}).json()["code"]
        == "already_member"
    )
    assert (
        c.patch(f"/api/v1/projects/{pid}/members/{user.id}", json={"role_code": "qa_lead"}).json()["role"][
            "code"
        ]
        == "qa_lead"
    )
    assert c.delete(f"/api/v1/projects/{pid}/members/{user.id}").status_code == 204
    actions = [
        r[0]
        for r in _rows(
            world,
            "SELECT action FROM audit_events WHERE project_id = :p AND entity_type = 'membership' ORDER BY occurred_at",
            p=pid,
        )
    ]
    assert actions[-3:] == ["membership.granted", "membership.changed", "membership.revoked"]


def test_last_qa_manager_cannot_be_removed_or_demoted(world: World) -> None:
    org = world.org()
    pid = world.project(org, "LAST")
    c = world.login(org.admin)
    assert c.delete(f"/api/v1/projects/{pid}/members/{org.admin.id}").json()["code"] == "last_qa_manager"
    r = c.patch(f"/api/v1/projects/{pid}/members/{org.admin.id}", json={"role_code": "viewer"})
    assert r.json()["code"] == "last_qa_manager"


def test_tcms_024_release_status_transitions(world: World) -> None:
    org = world.org()
    pid = world.project(org, "REL")
    c = world.login(org.admin)
    r = c.post(
        f"/api/v1/projects/{pid}/releases",
        json={"name": "SPARK v2.5", "start_date": "2026-11-03", "target_date": "2026-11-14"},
    )
    assert r.status_code == 201, r.text
    rel = r.json()
    assert rel["status"] == "planned"
    assert rel["allowed_transitions"] == ["active", "archived"]

    def move(to: str) -> Any:
        nonlocal rel
        resp = c.patch(
            f"/api/v1/releases/{rel['id']}", json={"status": to, "row_version": rel["row_version"]}
        )
        if resp.status_code == 200:
            rel = resp.json()
        return resp

    assert move("released").json()["code"] == "invalid_transition"
    assert move("active").status_code == 200
    assert move("released").json()["released_at"] is not None
    assert move("active").status_code == 200  # hotfix
    assert move("archived").status_code == 200
    assert move("active").json()["code"] == "invalid_transition"
    bad = c.post(
        f"/api/v1/projects/{pid}/releases",
        json={"name": "v3", "start_date": "2026-11-10", "target_date": "2026-11-01"},
    )
    assert bad.status_code == 422
    assert (
        c.post(f"/api/v1/projects/{pid}/releases", json={"name": "spark V2.5"}).json()["code"] == "name_taken"
    )


def test_tcms_025a_archived_environment_hidden_from_pickers(world: World) -> None:
    """AC-WS-03 (environment part; the cycle-creation 422 is verified in M3)."""
    org = world.org()
    pid = world.project(org, "ENV")
    c = world.login(org.admin)
    qa = next(e for e in c.get(f"/api/v1/projects/{pid}/environments").json() if e["name"] == "QA")
    assert c.post(f"/api/v1/environments/{qa['id']}/archive").json()["archived"] is True
    assert [e["name"] for e in c.get(f"/api/v1/projects/{pid}/environments").json()] == ["Staging"]
    all_envs = c.get(f"/api/v1/projects/{pid}/environments", params={"include_archived": "true"}).json()
    assert {e["name"] for e in all_envs} == {"QA", "Staging"}
    assert c.post(f"/api/v1/environments/{qa['id']}/restore").json()["archived"] is False
    assert c.post(f"/api/v1/projects/{pid}/environments", json={"name": "qa"}).json()["code"] == "name_taken"


def test_br_25_stale_row_version(world: World) -> None:
    org = world.org()
    pid = world.project(org, "ROW")
    c = world.login(org.admin)
    current = c.get(f"/api/v1/projects/{pid}")
    rv = current.json()["row_version"]
    assert current.headers["etag"] == f'"{rv}"'
    assert c.patch(f"/api/v1/projects/{pid}", json={"name": "Renamed"}).status_code == 428
    assert c.patch(f"/api/v1/projects/{pid}", json={"name": "Renamed", "row_version": rv}).status_code == 200
    stale = c.patch(f"/api/v1/projects/{pid}", json={"name": "Again", "row_version": rv})
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_row_version"
    assert (
        c.patch(
            f"/api/v1/projects/{pid}", json={"name": "Again"}, headers={"If-Match": f'"{rv + 1}"'}
        ).status_code
        == 200
    )


def test_project_settings_validation_and_audit(world: World) -> None:
    """US-023; attachment limit capped by the org value (review K9)."""
    org = world.org()
    pid = world.project(org, "SET")
    c = world.login(org.admin)
    rv = c.get(f"/api/v1/projects/{pid}").json()["row_version"]
    bad = c.patch(
        f"/api/v1/projects/{pid}",
        json={"settings": {"attachment_max_mb": 26, "report_module_depth": 6}, "row_version": rv},
    )
    assert bad.status_code == 422
    assert {e["field"] for e in bad.json()["errors"]} == {
        "settings.attachment_max_mb",
        "settings.report_module_depth",
    }
    ok = c.patch(
        f"/api/v1/projects/{pid}",
        json={"settings": {"approval_required": True, "attachment_max_mb": 10}, "row_version": rv},
    )
    assert ok.status_code == 200
    assert ok.json()["settings"]["approval_required"] is True
    changes = _rows(
        world,
        "SELECT changes FROM audit_events WHERE entity_id = :p AND action = 'project.settings_changed'",
        p=pid,
    )
    assert changes[0][0] == {"approval_required": [False, True], "attachment_max_mb": [25, 10]}


def test_organization_settings_validation(world: World) -> None:
    """US-021: ranges from docs/02 §4.1; audit organization.updated."""
    org = world.org()
    c = world.login(org.admin)
    rv = c.get("/api/v1/organization").json()["row_version"]
    bad = c.patch("/api/v1/organization", json={"settings": {"session_idle_minutes": 5}, "row_version": rv})
    assert bad.status_code == 422
    ok = c.patch("/api/v1/organization", json={"settings": {"session_idle_minutes": 60}, "row_version": rv})
    assert ok.json()["settings"]["session_idle_minutes"] == 60
    member = world.login(world.user(org, "Plain"))
    assert member.get("/api/v1/organization").json()["settings"] is None
    assert member.patch("/api/v1/organization", json={"name": "X", "row_version": 2}).status_code == 403


def test_tcms_013_cross_tenant_and_non_member_access_is_404(world: World) -> None:
    acme, other = world.org("ACME"), world.org("Other")
    pid = world.project(acme, "SPARK")
    foreign = world.project(other, "SPARK")
    c = world.login(acme.admin)
    env_id = c.get(f"/api/v1/projects/{pid}/environments").json()[0]["id"]
    rel_id = c.post(f"/api/v1/projects/{pid}/releases", json={"name": "v1"}).json()["id"]
    outsider = world.login(other.admin)  # admin of another org
    stranger = world.login(world.user(acme, "Stranger"))  # same org, not a member
    for client in (outsider, stranger):
        for url in (
            f"/api/v1/projects/{pid}",
            f"/api/v1/projects/{pid}/members",
            f"/api/v1/releases/{rel_id}",
            f"/api/v1/projects/{pid}/activity",
            f"/api/v1/audit-events/entity/release/{rel_id}",
        ):
            assert client.get(url).status_code == 404, url
        assert (
            client.patch(f"/api/v1/environments/{env_id}", json={"name": "x", "row_version": 1}).status_code
            == 404
        )
    assert [p["id"] for p in outsider.get("/api/v1/projects").json()] == [str(foreign)]
    assert stranger.get("/api/v1/projects").json() == []


def test_org_admin_sees_every_project_and_access_is_audited_once_per_session(world: World) -> None:
    """docs/02 §3.2 + review Q1: `project.admin_accessed` once per session per project."""
    org = world.org()
    manager = world.user(org, "Manager")
    seed = world.project(org, "SEED")
    world.member(org, seed, manager, "qa_manager")
    pid = world.login(manager).post("/api/v1/projects", json={"key": "OWN", "name": "Own"}).json()["id"]
    admin = world.login(org.admin)
    for _ in range(3):
        assert admin.get(f"/api/v1/projects/{pid}").status_code == 200
    with clock.frozen(clock.now() + timedelta(seconds=31)):  # next TOTP step: a new session
        world.login(org.admin).get(f"/api/v1/projects/{pid}")
    rows = _rows(
        world,
        "SELECT count(*) FROM audit_events WHERE action = 'project.admin_accessed' AND entity_id = :p",
        p=pid,
    )
    assert rows[0][0] == 2


def test_us_028_activity_feed(world: World) -> None:
    org = world.org()
    pid = world.project(org, "ACT")
    c = world.login(org.admin)
    c.post(f"/api/v1/projects/{pid}/environments", json={"name": "UAT"})
    c.post(f"/api/v1/projects/{pid}/releases", json={"name": "v2.5"})
    feed = c.get(f"/api/v1/projects/{pid}/activity").json()
    assert feed["total"] >= 4
    assert feed["items"][0]["action"] == "release.created"
    assert feed["items"][0]["summary"] == "Admin created release v2.5"
    envs = c.get(f"/api/v1/projects/{pid}/activity", params={"entity_type": "environment"}).json()
    assert {i["action"] for i in envs["items"]} == {"environment.created"}
    viewer = world.user(org, "Watcher")
    world.member(org, pid, viewer, "viewer")
    assert world.login(viewer).get(f"/api/v1/projects/{pid}/activity").status_code == 200


def test_us_161_record_history(world: World) -> None:
    org = world.org()
    pid = world.project(org, "HIS")
    c = world.login(org.admin)
    rel = c.post(f"/api/v1/projects/{pid}/releases", json={"name": "v1"}).json()
    c.patch(f"/api/v1/releases/{rel['id']}", json={"name": "v1.0", "row_version": rel["row_version"]})
    hist = c.get(f"/api/v1/audit-events/entity/release/{rel['id']}").json()
    assert [i["action"] for i in hist["items"]] == ["release.updated", "release.created"]
    assert hist["items"][0]["changes"] == {"name": ["v1", "v1.0"]}


def test_br_16_human_keys_are_sequential_and_never_reused(world: World) -> None:
    org = world.org()
    pid = world.project(org, "KEY")
    ctx = world.ctx(org.id, org.admin.id, is_admin=True, project_id=pid)
    with unit_of_work(world.factory) as uow:
        keys = [workspace.allocate_key(uow, ctx, "test_case")[1] for _ in range(3)]
        assert workspace.allocate_key(uow, ctx, "defect")[1] == "KEY-D-1"
    assert keys == ["KEY-TC-1", "KEY-TC-2", "KEY-TC-3"]
    with pytest.raises(RuntimeError), unit_of_work(world.factory) as uow:
        workspace.allocate_key(uow, ctx, "test_case")
        raise RuntimeError("rollback")
    with unit_of_work(world.factory) as uow:
        # A rolled-back allocation may leave a gap; a committed key is never handed out twice.
        assert workspace.allocate_key(uow, ctx, "test_case")[1] not in keys
