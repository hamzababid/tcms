"""Test repository and cases (docs/08 §15.3: TCMS-030…045; BR-01/02/13/14/15/16/17/18/28; AC-TD-01…22)."""

from __future__ import annotations

import io
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from tcms.core import ids
from tcms.core.permissions import ROLE_PERMISSIONS, RoleCode
from tcms.platform.jobs.worker import run_one
from tests.world import ApiClient, OrgHandle, World

pytestmark = pytest.mark.integration


def _rows(world: World, sql: str, **params: Any) -> list[Any]:
    with world.factory() as s:
        return list(s.execute(text(sql), params).all())


def _content(title: str = "Login with valid password", steps: int = 2, **extra: Any) -> dict[str, Any]:
    return {
        "format": "steps",
        "title": title,
        "steps": [{"action": f"Step {i}", "expected_result": f"Result {i}"} for i in range(1, steps + 1)],
        **extra,
    }


class Space:
    """An org with one project, an admin client and a root folder."""

    def __init__(self, world: World, key: str = "SPARK") -> None:
        self.world = world
        self.org: OrgHandle = world.org()
        self.pid = world.project(self.org, key)
        self.admin: ApiClient = world.login(self.org.admin)
        self.folder = self.post_folder("Authentication")["id"]

    def url(self, suffix: str) -> str:
        return f"/api/v1/projects/{self.pid}{suffix}"

    def post_folder(self, name: str, parent: str | None = None, client: ApiClient | None = None) -> Any:
        r = (client or self.admin).post(self.url("/folders"), json={"name": name, "parent_id": parent})
        assert r.status_code == 201, r.text
        return r.json()

    def post_case(self, client: ApiClient | None = None, folder: str | None = None, **content: Any) -> Any:
        r = (client or self.admin).post(
            self.url("/test-cases"), json={"folder_id": folder or self.folder, "content": _content(**content)}
        )
        assert r.status_code == 201, r.text
        return r.json()["case"]

    def tree(self, **params: Any) -> dict[str, Any]:
        return {f["name"]: f for f in self.admin.get(self.url("/folders"), params=params).json()}

    def settings(self, **values: Any) -> None:
        p = self.admin.get(self.url("")).json()
        r = self.admin.patch(self.url(""), json={"settings": values, "row_version": p["row_version"]})
        assert r.status_code == 200, r.text


@pytest.fixture
def space(world: World) -> Space:
    return Space(world)


# -- folders --------------------------------------------------------------------------------------


def test_tcms_030_nested_folders_and_move_update_counts(space: Space) -> None:
    """FR-TD-001: counts include descendants and follow a move."""
    web = space.post_folder("Web", space.folder)
    space.post_folder("Mobile", space.folder)
    other = space.post_folder("Billing")["id"]
    space.post_case(folder=web["id"])
    space.post_case(folder=web["id"])
    space.post_case()
    tree = space.tree()
    assert (tree["Authentication"]["case_count"], tree["Authentication"]["total_count"]) == (1, 3)
    assert tree["Web"]["depth"] == 2
    assert tree["Web"]["parent_id"] == space.folder

    r = space.admin.post(
        f"/api/v1/folders/{web['id']}/move", json={"parent_id": other, "row_version": web["row_version"]}
    )
    assert r.status_code == 200, r.text
    tree = space.tree()
    assert tree["Authentication"]["total_count"] == 1
    assert tree["Billing"]["total_count"] == 2
    assert tree["Web"]["parent_id"] == other


def test_br_15_folder_names_unique_among_siblings(space: Space) -> None:
    r = space.admin.post(space.url("/folders"), json={"name": "authentication"})
    assert (r.status_code, r.json()["code"]) == (409, "name_taken"), r.text
    assert space.admin.post(space.url("/folders"), json={"name": "a/b"}).status_code == 422


def test_tcms_031_folder_cycle_and_depth(space: Space) -> None:
    """AC-TD-01 (cycle) and AC-TD-02 (depth 11)."""
    a = space.tree()["Authentication"]
    b = space.post_folder("B", space.folder)
    r = space.admin.post(
        f"/api/v1/folders/{space.folder}/move", json={"parent_id": b["id"], "row_version": a["row_version"]}
    )
    assert (r.status_code, r.json()["code"]) == (422, "folder_cycle")

    parent = space.folder
    for depth in range(2, 11):  # Authentication is depth 1 → build down to depth 10
        parent = space.post_folder(f"L{depth}", parent)["id"]
    r = space.admin.post(space.url("/folders"), json={"name": "L11", "parent_id": parent})
    assert (r.status_code, r.json()["code"]) == (422, "folder_too_deep")

    lone = space.post_folder("Lone")
    space.post_folder("Sub", lone["id"])
    r = space.admin.post(
        f"/api/v1/folders/{lone['id']}/move", json={"parent_id": parent, "row_version": lone["row_version"]}
    )
    assert (r.status_code, r.json()["code"]) == (422, "folder_too_deep"), "the whole subtree is checked"


def test_br_15_delete_folder_only_when_empty(space: Space) -> None:
    """AC-TD-03: an archived case still blocks deletion; so does a subfolder."""
    f = space.post_folder("Temp")
    case = space.post_case(folder=f["id"])
    assert space.admin.post(f"/api/v1/test-cases/{case['id']}/archive", json={}).status_code == 200
    r = space.admin.delete(f"/api/v1/folders/{f['id']}")
    assert (r.status_code, r.json()["code"]) == (409, "folder_not_empty")

    parent = space.post_folder("Parent")
    space.post_folder("Child", parent["id"])
    assert space.admin.delete(f"/api/v1/folders/{parent['id']}").json()["code"] == "folder_not_empty"

    empty = space.post_folder("Empty")
    assert space.admin.delete(f"/api/v1/folders/{empty['id']}").status_code == 204
    assert "Empty" not in space.tree(include_archived=True)


def test_folder_archive_hides_subtree(space: Space) -> None:
    child = space.post_folder("Child", space.folder)
    assert space.admin.post(f"/api/v1/folders/{space.folder}/archive").status_code == 200
    assert {"Authentication", "Child"}.isdisjoint(space.tree())
    tree = space.tree(include_archived=True)
    assert tree["Authentication"]["archived"]
    assert tree["Child"]["id"] == child["id"]
    assert space.admin.post(f"/api/v1/folders/{space.folder}/restore").status_code == 200
    assert {"Authentication", "Child"} <= set(space.tree())


# -- create and version ---------------------------------------------------------------------------


def test_br_16_tcms_033_create_steps_case_allocates_key_and_v1(space: Space) -> None:
    """FR-TD-002: version 1, sequential key, approved when approval is off (docs/02 §5.4)."""
    first = space.post_case()
    second = space.post_case(title="Second case")
    assert (first["key"], second["key"]) == ("SPARK-TC-1", "SPARK-TC-2")
    assert first["latest_version_no"] == 1
    assert first["version"]["version_no"] == 1
    assert first["status"] == "approved"
    assert first["approved_version_no"] == 1
    assert first["version"]["approval"]["mode"] == "auto"
    assert [st["position"] for st in first["version"]["steps"]] == [1, 2]
    assert first["owner"]["id"] == str(space.org.admin.id)

    moved_to = space.post_folder("Elsewhere")["id"]
    r = space.admin.patch(
        f"/api/v1/test-cases/{first['id']}", json={"folder_id": moved_to, "row_version": first["row_version"]}
    )
    assert r.json()["key"] == "SPARK-TC-1", "keys never change on move"
    space.admin.delete(f"/api/v1/test-cases/{second['id']}")
    assert space.post_case(title="Third")["key"] == "SPARK-TC-3", "keys are never reused"


def test_create_case_validation(space: Space) -> None:
    bad = space.admin.post(
        space.url("/test-cases"),
        json={"folder_id": space.folder, "content": {"format": "steps", "title": "ok title", "steps": []}},
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "validation_error"
    text_case = space.admin.post(
        space.url("/test-cases"),
        json={
            "folder_id": space.folder,
            "content": {"format": "text", "title": "Text case", "text_body": "Do it"},
        },
    )
    assert text_case.status_code == 201, text_case.text
    assert text_case.json()["case"]["version"]["steps"] == []
    space.post_case(title="Login with valid password")
    dup = space.post_case(title="Login with valid password")
    assert "title_exists" in dup["warnings"]


def test_br_01_tcms_034_metadata_edit_does_not_version(space: Space) -> None:
    """AC-TD-10: priority change → no new version, audit records old/new."""
    case = space.post_case()
    r = space.admin.patch(
        f"/api/v1/test-cases/{case['id']}", json={"priority": "high", "row_version": case["row_version"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["latest_version_no"] == 1
    assert r.json()["priority"] == "high"
    events = _rows(
        space.world,
        "SELECT changes FROM audit_events WHERE entity_id = :c AND action = 'test_case.updated'",
        c=case["id"],
    )
    assert events
    assert events[-1][0]["priority"] == ["medium", "high"]


@pytest.mark.br("BR-02")
def test_br_01_tcms_034_content_edit_creates_version(space: Space) -> None:
    """AC-TD-11: step 2 change → v2 exists, v1 unchanged."""
    case = space.post_case()
    content = _content()
    content["steps"][1]["expected_result"] = "Dashboard shown"
    r = space.admin.put(
        f"/api/v1/test-cases/{case['id']}/content",
        json={"content": content, "change_note": "Clarify result", "row_version": case["row_version"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version_created"] is True
    assert body["case"]["latest_version_no"] == 2
    assert body["case"]["version"]["steps"][1]["expected_result"] == "Dashboard shown"
    v1 = space.admin.get(f"/api/v1/test-cases/{case['id']}/versions/1").json()
    assert v1["steps"][1]["expected_result"] == "Result 2"
    assert body["case"]["version"]["steps"][1]["id"] != v1["steps"][1]["id"], "steps belong to a version"
    versions = space.admin.get(f"/api/v1/test-cases/{case['id']}/versions").json()
    assert [(v["version_no"], v["is_latest"]) for v in versions] == [(2, True), (1, False)]
    assert versions[0]["change_note"] == "Clarify result"


def test_tcms_035_identical_save_creates_no_version(space: Space) -> None:
    """AC-TD-13: normalized (trimmed, \\n line endings) identical content → version_created false."""
    case = space.post_case(description="Line one\nLine two")
    same = _content(description="\nLine one  \r\nLine two\n\n")
    r = space.admin.put(
        f"/api/v1/test-cases/{case['id']}/content", json={"content": same, "row_version": case["row_version"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["version_created"] is False
    assert r.json()["case"]["latest_version_no"] == 1


def test_br_25_stale_content_save_conflicts(space: Space) -> None:
    """TCMS-047 (API half): a save with an old row_version gets 409 stale_row_version."""
    case = space.post_case()
    space.admin.patch(
        f"/api/v1/test-cases/{case['id']}", json={"priority": "low", "row_version": case["row_version"]}
    )
    r = space.admin.put(
        f"/api/v1/test-cases/{case['id']}/content",
        json={"content": _content("Changed"), "row_version": case["row_version"]},
    )
    assert (r.status_code, r.json()["code"]) == (409, "stale_row_version"), r.text


def test_tcms_036_compare_versions(space: Space) -> None:
    """AC-TD-12: field diffs and steps aligned by position."""
    case = space.post_case(steps=3)
    content = _content(title="Login with a valid password", steps=3)
    content["steps"][1]["action"] = "Type the password"
    content["steps"].pop()
    space.admin.put(
        f"/api/v1/test-cases/{case['id']}/content",
        json={"content": content, "row_version": case["row_version"]},
    )
    diff = space.admin.get(f"/api/v1/test-cases/{case['id']}/compare", params={"from": 1, "to": 2}).json()
    fields = {f["field"]: f for f in diff["fields"]}
    assert fields["title"]["changed"]
    assert not fields["description"]["changed"]
    assert [s["change"] for s in diff["steps"]] == ["unchanged", "changed", "removed"]
    assert (
        space.admin.get(f"/api/v1/test-cases/{case['id']}/compare", params={"from": 1, "to": 9}).status_code
        == 404
    )


def test_tcms_037_restore_earlier_version(space: Space) -> None:
    """FR-TD-005: restoring v1 creates v3 with v1's content and note."""
    case = space.post_case()
    r = space.admin.put(
        f"/api/v1/test-cases/{case['id']}/content",
        json={"content": _content("Renamed"), "row_version": case["row_version"]},
    )
    rv = r.json()["case"]["row_version"]
    r = space.admin.post(
        f"/api/v1/test-cases/{case['id']}/restore-version", json={"version_no": 1, "row_version": rv}
    )
    assert r.status_code == 200, r.text
    restored = r.json()["case"]
    assert restored["latest_version_no"] == 3
    assert restored["title"] == "Login with valid password"
    assert restored["version"]["change_note"] == "Restored from v1"


# -- approval workflow ----------------------------------------------------------------------------


def _team(space: Space) -> dict[str, ApiClient]:
    team = space.world.team(space.org, space.pid)
    space.users = team  # type: ignore[attr-defined]
    return {role: space.world.login(u) for role, u in team.items()}


def test_br_17_tcms_038_approval_workflow(space: Space) -> None:
    """AC-TD-20 (new version → draft, approved_version kept) and AC-TD-22 (return comment + notification)."""
    clients = _team(space)
    space.settings(approval_required=True)
    author, lead = clients["qa_engineer"], clients["qa_lead"]
    case = space.post_case(client=author)
    assert (case["status"], case["approved_version_no"]) == ("draft", None)

    assert author.post(f"/api/v1/test-cases/{case['id']}/submit", json={}).json()["status"] == "in_review"
    r = lead.post(f"/api/v1/test-cases/{case['id']}/return", json={"comment": "Add the lockout step"})
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    comments = author.get(
        "/api/v1/comments", params={"entity_type": "test_case", "entity_id": case["id"]}
    ).json()
    assert any("Add the lockout step" in (c["body"] or "") for c in comments)
    tester_id = space.users["qa_engineer"].id  # type: ignore[attr-defined]
    notes = _rows(
        space.world,
        "SELECT type FROM notifications WHERE user_id = :u AND entity_id = :c",
        u=tester_id,
        c=case["id"],
    )
    assert ("test_case.returned",) in notes

    author.post(f"/api/v1/test-cases/{case['id']}/submit", json={})
    rv = author.get(f"/api/v1/test-cases/{case['id']}").json()["row_version"]
    r = lead.post(f"/api/v1/test-cases/{case['id']}/approve", json={"row_version": rv})
    assert r.status_code == 200, r.text
    approved = r.json()
    assert (approved["status"], approved["approved_version_no"]) == ("approved", 1)
    assert approved["version"]["approval"]["mode"] == "manual"

    r = author.put(
        f"/api/v1/test-cases/{case['id']}/content",
        json={"content": _content("v2 title"), "row_version": approved["row_version"]},
    )
    after = r.json()["case"]
    assert (after["status"], after["latest_version_no"], after["approved_version_no"]) == ("draft", 2, 1)


def test_br_18_tcms_039_self_approval_blocked(space: Space) -> None:
    """AC-TD-21."""
    clients = _team(space)
    space.settings(approval_required=True)
    lead = clients["qa_lead"]
    case = space.post_case(client=lead)
    lead.post(f"/api/v1/test-cases/{case['id']}/submit", json={})
    rv = lead.get(f"/api/v1/test-cases/{case['id']}").json()["row_version"]
    r = lead.post(f"/api/v1/test-cases/{case['id']}/approve", json={"row_version": rv})
    assert (r.status_code, r.json()["code"]) == (403, "self_approval_not_allowed")

    space.settings(allow_self_approval=True)
    rv = lead.get(f"/api/v1/test-cases/{case['id']}").json()["row_version"]
    assert lead.post(f"/api/v1/test-cases/{case['id']}/approve", json={"row_version": rv}).status_code == 200


def test_tcms_040_enabling_approval_grandfathers_and_disabling_auto_approves(space: Space) -> None:
    """docs/02 §5.4: on → existing cases stay approved; off → draft/in_review are approved at latest."""
    old = space.post_case()
    space.settings(approval_required=True)
    assert space.admin.get(f"/api/v1/test-cases/{old['id']}").json()["status"] == "approved"
    new = space.post_case(title="Draft case")
    assert new["status"] == "draft"
    space.settings(approval_required=False)
    back = space.admin.get(f"/api/v1/test-cases/{new['id']}").json()
    assert (back["status"], back["approved_version_no"]) == ("approved", 1)


# -- lifecycle ------------------------------------------------------------------------------------


def test_br_13_tcms_041_deprecate_archive_restore(space: Space) -> None:
    case = space.post_case()
    cid = case["id"]
    assert space.admin.post(f"/api/v1/test-cases/{cid}/deprecate", json={}).json()["status"] == "deprecated"
    assert space.admin.post(f"/api/v1/test-cases/{cid}/restore", json={}).json()["status"] == "approved"
    assert (
        space.admin.post(f"/api/v1/test-cases/{cid}/archive", json={"reason": "obsolete"}).json()["status"]
        == "archived"
    )

    listed = {c["id"] for c in space.admin.get(space.url("/test-cases")).json()["items"]}
    assert cid not in listed, "archived cases are hidden by default"
    with_archived = space.admin.get(space.url("/test-cases"), params={"include_archived": "true"}).json()[
        "items"
    ]
    assert cid in {c["id"] for c in with_archived}
    rv = space.admin.get(f"/api/v1/test-cases/{cid}").json()["row_version"]
    r = space.admin.put(
        f"/api/v1/test-cases/{cid}/content", json={"content": _content("x y z"), "row_version": rv}
    )
    assert (r.status_code, r.json()["code"]) == (409, "case_archived")
    assert space.admin.post(f"/api/v1/test-cases/{cid}/restore", json={}).json()["status"] == "approved"
    assert space.tree()["Authentication"]["case_count"] == 1


def test_br_14_tcms_042_hard_delete_only_never_run(space: Space, world: World, owner_engine: Engine) -> None:
    never = space.post_case()
    r = space.admin.delete(f"/api/v1/test-cases/{never['id']}")
    assert r.status_code == 204
    assert space.admin.get(f"/api/v1/test-cases/{never['id']}").status_code == 404
    assert _rows(
        world,
        "SELECT 1 FROM audit_events WHERE entity_id = :c AND action = 'test_case.deleted'",
        c=never["id"],
    )

    ran = space.post_case(title="Was in a cycle")
    env = space.admin.get(space.url("/environments")).json()[0]["id"]
    with owner_engine.begin() as conn:  # cycles arrive in M3; a minimal run row stands in for one
        cycle = ids.new_id()
        conn.execute(
            text(
                "INSERT INTO test_cycles (id, organization_id, project_id, key_num, key, name, environment_id, owner_id)"
                " VALUES (:id, :o, :p, 1, 'SPARK-CY-1', 'Cycle one', :e, :u)"
            ),
            {"id": cycle, "o": space.org.id, "p": space.pid, "e": env, "u": space.org.admin.id},
        )
        conn.execute(
            text(
                "INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position)"
                " VALUES (:id, :o, :p, :c, :tc, :v, 1)"
            ),
            {
                "id": ids.new_id(),
                "o": space.org.id,
                "p": space.pid,
                "c": cycle,
                "tc": ran["id"],
                "v": ran["version"]["id"],
            },
        )
    r = space.admin.delete(f"/api/v1/test-cases/{ran['id']}")
    assert (r.status_code, r.json()["code"]) == (409, "case_has_runs")
    runs = space.admin.get(f"/api/v1/test-cases/{ran['id']}/executions").json()
    assert [(x["cycle_key"], x["version_no"], x["status"]) for x in runs] == [("SPARK-CY-1", 1, "not_run")]


def test_delete_requires_testcase_delete(space: Space) -> None:
    clients = _team(space)
    case = space.post_case()
    r = clients["qa_engineer"].delete(f"/api/v1/test-cases/{case['id']}")
    assert (r.status_code, r.json()["code"]) == (403, "permission_denied")


# -- bulk, duplicate, links, tags, resolve --------------------------------------------------------


def test_bulk_small_runs_inline_with_shared_bulk_id(space: Space) -> None:
    cases = [space.post_case(title=f"Case {i}") for i in range(3)]
    r = space.admin.post(
        space.url("/test-cases/bulk"),
        json={
            "action": "set_priority",
            "case_ids": [c["id"] for c in cases],
            "params": {"value": "critical"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 3
    assert body["skipped"] == []
    events = _rows(
        space.world,
        "SELECT entity_id FROM audit_events WHERE context->>'bulk_operation_id' = :b",
        b=body["bulk_operation_id"],
    )
    assert len(events) == 3
    filtered = space.admin.get(space.url("/test-cases"), params={"priority": "critical"}).json()
    assert filtered["total"] == 3


def test_bulk_by_filter_and_skips(space: Space) -> None:
    a = space.post_case(title="One")
    space.post_case(title="Two")
    space.admin.post(f"/api/v1/test-cases/{a['id']}/archive", json={})
    r = space.admin.post(
        space.url("/test-cases/bulk"),
        json={"action": "deprecate", "filter": {"include_archived": "true"}, "params": {}},
    )
    body = r.json()
    assert body["updated"] == 1
    assert [s["code"] for s in body["skipped"]] == ["invalid_status"]
    r = space.admin.post(space.url("/test-cases/bulk"), json={"action": "deprecate", "params": {}})
    assert r.status_code == 422, "case_ids or filter is required"


@pytest.mark.usefixtures("clean_jobs")
def test_tcms_043_bulk_move_300_runs_as_job(space: Space, world: World) -> None:
    """FR-TD-010: > 200 cases → 202 + job; every case gets its own audit event with the bulk id."""
    target = space.post_folder("Target")["id"]
    case_ids = [str(world.case(space.org, space.pid, UUID(space.folder))[0]) for _ in range(300)]
    r = space.admin.post(
        space.url("/test-cases/bulk"),
        json={"action": "move", "case_ids": case_ids, "params": {"folder_id": target}},
    )
    assert r.status_code == 202, r.text
    bulk_id = r.json()["bulk_operation_id"]
    assert r.json()["job_id"]
    while run_one(world.factory, "test-worker"):
        pass
    assert space.tree()["Target"]["case_count"] == 300
    events = _rows(
        world, "SELECT count(*) FROM audit_events WHERE context->>'bulk_operation_id' = :b", b=bulk_id
    )
    assert events[0][0] == 300


def test_tcms_044_duplicate_case(space: Space) -> None:
    """FR-TD-009: new key, v1, link duplicated_from, 'Copy of ' prefix in the same folder."""
    case = space.post_case()
    r = space.admin.post(f"/api/v1/test-cases/{case['id']}/duplicate", json={})
    assert r.status_code == 201, r.text
    copy = r.json()["case"]
    assert copy["key"] == "SPARK-TC-2"
    assert copy["latest_version_no"] == 1
    assert copy["title"] == "Copy of Login with valid password"
    assert [(lk["key"], lk["direction"]) for lk in copy["links"]] == [("SPARK-TC-1", "duplicated_from")]
    other = space.post_folder("Other")["id"]
    moved = space.admin.post(f"/api/v1/test-cases/{case['id']}/duplicate", json={"folder_id": other}).json()[
        "case"
    ]
    assert moved["title"] == "Login with valid password"


def test_related_links(space: Space) -> None:
    a, b = space.post_case(title="Case A"), space.post_case(title="Case B")
    r = space.admin.post(f"/api/v1/test-cases/{a['id']}/links", json={"target_case_id": b["id"]})
    assert r.status_code == 200
    assert [lk["key"] for lk in r.json()["links"]] == [b["key"]]
    assert [lk["key"] for lk in space.admin.get(f"/api/v1/test-cases/{b['id']}").json()["links"]] == [
        a["key"]
    ]
    assert (
        space.admin.post(f"/api/v1/test-cases/{a['id']}/links", json={"target_case_id": a["id"]}).status_code
        == 422
    )
    r = space.admin.request("DELETE", f"/api/v1/test-cases/{a['id']}/links", json={"target_case_id": b["id"]})
    assert r.status_code == 200
    assert r.json()["links"] == []


def test_tags_system_and_custom(space: Space) -> None:
    case = space.post_case()
    space.admin.patch(
        f"/api/v1/test-cases/{case['id']}",
        json={"tags": ["smoke", "login-flow"], "row_version": case["row_version"]},
    )
    tags = {t["name"]: t for t in space.admin.get(space.url("/tags")).json()}
    assert {"smoke", "sanity", "regression", "login-flow"} <= set(tags)
    assert tags["smoke"]["is_system"]
    assert tags["smoke"]["usage"] == 1
    assert space.admin.delete(f"/api/v1/tags/{tags['smoke']['id']}").status_code == 409
    assert space.admin.post(space.url("/tags"), json={"name": "Bad Tag"}).status_code == 422
    assert space.admin.get(space.url("/test-cases"), params={"tag": "login-flow"}).json()["total"] == 1


def test_resolve_key_and_search(space: Space) -> None:
    case = space.post_case(title="Reset password by email")
    for key in ("SPARK-TC-1", "TC-1", "1"):
        r = space.admin.get(space.url("/resolve"), params={"key": key})
        assert r.json() == {"entity_type": "test_case", "id": case["id"], "key": "SPARK-TC-1"}, key
    assert space.admin.get(space.url("/resolve"), params={"key": "TC-99"}).status_code == 404
    found = space.admin.get(space.url("/test-cases"), params={"q": "password"}).json()["items"]
    assert [c["key"] for c in found] == ["SPARK-TC-1"]


def test_case_history_lists_audit(space: Space) -> None:
    case = space.post_case()
    space.admin.patch(
        f"/api/v1/test-cases/{case['id']}", json={"priority": "low", "row_version": case["row_version"]}
    )
    actions = [
        e["action"] for e in space.admin.get(f"/api/v1/test-cases/{case['id']}/history").json()["items"]
    ]
    assert {"test_case.created", "test_case.updated"} <= set(actions)


def test_non_member_gets_404(space: Space, world: World) -> None:
    case = space.post_case()
    outsider = world.login(world.user(space.org, "Outsider"))
    assert outsider.get(f"/api/v1/test-cases/{case['id']}").status_code == 404
    other = world.login(world.org("Other").admin)
    assert other.get(f"/api/v1/test-cases/{case['id']}").status_code == 404


def test_idempotency_key_replays_create(space: Space) -> None:
    """docs/06 §2.8."""
    body = {"folder_id": space.folder, "content": _content("Idempotent case")}
    headers = {"Idempotency-Key": "create-1"}
    first = space.admin.post(space.url("/test-cases"), json=body, headers=headers)
    again = space.admin.post(space.url("/test-cases"), json=body, headers=headers)
    assert first.status_code == again.status_code == 201
    assert again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["case"]["id"] == first.json()["case"]["id"]
    assert space.admin.get(space.url("/test-cases")).json()["total"] == 1
    changed = space.admin.post(
        space.url("/test-cases"), json={**body, "content": _content("Other")}, headers=headers
    )
    assert (changed.status_code, changed.json()["code"]) == (422, "idempotency_key_reused")


# -- attachments and comments ---------------------------------------------------------------------

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def _upload(
    client: ApiClient, entity_type: str, entity_id: str, name: str = "shot.png", data: bytes = PNG
) -> Any:
    return client.post(
        "/api/v1/attachments",
        data={"entity_type": entity_type, "entity_id": entity_id},
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
    )


def test_attachments_upload_download_unlink(space: Space) -> None:
    case = space.post_case()
    r = _upload(space.admin, "test_case", case["id"], "../evil<name>.png")
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["content_type"] == "image/png", "type is sniffed, not trusted"
    assert att["file_name"] == "evil_name_.png"
    content = space.admin.get(att["url"])
    assert content.status_code == 200
    assert content.content == PNG
    assert content.headers["content-disposition"].startswith("inline")
    assert "sandbox" in content.headers["content-security-policy"]
    assert (
        space.admin.get(att["url"], params={"download": "true"})
        .headers["content-disposition"]
        .startswith("attachment")
    )
    assert space.admin.get(f"/api/v1/test-cases/{case['id']}").json()["counts"]["attachments"] == 1

    r = space.admin.delete(f"/api/v1/attachments/{att['id']}/links/test_case/{case['id']}")
    assert r.status_code == 204
    assert space.admin.get(f"/api/v1/attachments/{att['id']}").status_code == 404


def test_attachment_permissions(space: Space) -> None:
    clients = _team(space)
    case = space.post_case()
    assert _upload(clients["viewer"], "test_case", case["id"]).status_code == 403
    att = _upload(clients["qa_engineer"], "test_case", case["id"]).json()
    assert clients["viewer"].get(att["url"]).status_code == 200
    r = clients["viewer"].delete(f"/api/v1/attachments/{att['id']}/links/test_case/{case['id']}")
    assert r.status_code == 403


def test_br_28_tcms_045_step_attachments_carry_forward_and_lock_when_approved(space: Space) -> None:
    """§5.3: step attachments are re-linked to the same-position step; BR-28: approved versions keep them."""
    clients = _team(space)
    space.settings(approval_required=True)
    author = clients["qa_engineer"]
    case = space.post_case(client=author)
    step1 = case["version"]["steps"][0]["id"]
    att = _upload(author, "test_case_step", step1).json()

    content = _content()
    content["steps"][1]["action"] = "Changed step 2"
    r = author.put(
        f"/api/v1/test-cases/{case['id']}/content",
        json={"content": content, "row_version": case["row_version"]},
    )
    new_steps = r.json()["case"]["version"]["steps"]
    assert [a["id"] for a in new_steps[0]["attachments"]] == [att["id"]]

    author.post(f"/api/v1/test-cases/{case['id']}/submit", json={})
    rv = author.get(f"/api/v1/test-cases/{case['id']}").json()["row_version"]
    assert (
        clients["qa_lead"]
        .post(f"/api/v1/test-cases/{case['id']}/approve", json={"row_version": rv})
        .status_code
        == 200
    )
    r = author.delete(f"/api/v1/attachments/{att['id']}/links/test_case_step/{new_steps[0]['id']}")
    assert (r.status_code, r.json()["code"]) == (409, "immutable_record")


def test_comments_mentions_edit_window(space: Space) -> None:
    clients = _team(space)
    case = space.post_case()
    tester = space.users["qa_engineer"]  # type: ignore[attr-defined]
    body = f"Please check @[Tester](user:{tester.id}) and @[Nobody](user:{ids.new_id()})"
    r = clients["qa_lead"].post(
        "/api/v1/comments", json={"entity_type": "test_case", "entity_id": case["id"], "body": body}
    )
    assert r.status_code == 201, r.text
    comment = r.json()
    assert comment["mentions"] == [str(tester.id)], "only project members are mentioned"
    notes = _rows(space.world, "SELECT type FROM notifications WHERE user_id = :u", u=tester.id)
    assert ("comment.mentioned",) in notes

    assert (
        clients["qa_engineer"].patch(f"/api/v1/comments/{comment['id']}", json={"body": "hijack"}).status_code
        == 403
    )
    edited = clients["qa_lead"].patch(f"/api/v1/comments/{comment['id']}", json={"body": "Edited"}).json()
    assert edited["body"] == "Edited"
    assert edited["edited_at"]
    assert clients["qa_lead"].delete(f"/api/v1/comments/{comment['id']}").status_code == 204
    listed = (
        clients["viewer"]
        .get("/api/v1/comments", params={"entity_type": "test_case", "entity_id": case["id"]})
        .json()
    )
    assert [(c["deleted"], c["body"]) for c in listed] == [(True, None)]
    viewer_may = "comment.create" in ROLE_PERMISSIONS[RoleCode.viewer]
    r = clients["viewer"].post(
        "/api/v1/comments", json={"entity_type": "test_case", "entity_id": case["id"], "body": "hi"}
    )
    assert r.status_code == (201 if viewer_may else 403)


def test_us_060_automation_keys_unique_per_project(space: Space, world: World) -> None:
    """FR-TD-014: keys are editable metadata, unique within the project (not across projects)."""
    a, b = space.post_case(title="Case A"), space.post_case(title="Case B")
    r = space.admin.patch(
        f"/api/v1/test-cases/{a['id']}",
        json={
            "automation_status": "automated",
            "automation_keys": ["auth.login_ok"],
            "row_version": a["row_version"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["automation_keys"] == ["auth.login_ok"]
    r = space.admin.patch(
        f"/api/v1/test-cases/{b['id']}",
        json={"automation_keys": ["auth.login_ok"], "row_version": b["row_version"]},
    )
    assert (r.status_code, r.json()["code"]) == (409, "automation_key_taken"), r.text
    other = Space(world, "OTHER")
    c = other.post_case()
    r = other.admin.patch(
        f"/api/v1/test-cases/{c['id']}",
        json={"automation_keys": ["auth.login_ok"], "row_version": c["row_version"]},
    )
    assert r.status_code == 200, r.text
