"""M3 E07 — test plans (US-070…074). API tests for FR-PLN-001…006, BR-13, BR-16.

Acceptance: TCMS-050 (create with exit rules and risks), TCMS-051 (add cases with exclusions report).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.world import ApiClient, OrgHandle, World

pytestmark = pytest.mark.integration


class Space:
    """An org with one project, an admin client, a folder and a couple of cases."""

    def __init__(self, world: World, key: str = "SPARK") -> None:
        self.world = world
        self.org: OrgHandle = world.org()
        self.pid = world.project(self.org, key)
        self.admin: ApiClient = world.login(self.org.admin)
        self.folder = world.folder(self.org, self.pid, "Auth")

    def url(self, suffix: str = "") -> str:
        return f"/api/v1/projects/{self.pid}{suffix}"

    def case(self, title: str | None = None) -> tuple[UUID, str]:
        return self.world.case(self.org, self.pid, self.folder, title)

    def create_plan(self, **overrides: Any) -> dict[str, Any]:
        body = {"name": "Regression plan", "type": "regression", **overrides}
        r = self.admin.post(self.url("/test-plans"), json=body)
        assert r.status_code == 201, r.text
        return r.json()


# -- TCMS-050: create with exit rules and risks (FR-PLN-001/005) ----------------------------------


def test_us_070_create_plan_with_exit_rules_and_risks(world: World) -> None:
    """TCMS-050: a plan is saved with structured exit rules and risks (FR-PLN-001, FR-PLN-005)."""
    sp = Space(world)
    rel = sp.admin.post(sp.url("/releases"), json={"name": "v1"}).json()
    env_id = sp.admin.get(sp.url("/environments")).json()[0]["id"]
    plan = sp.create_plan(
        name="SPARK regression",
        type="regression",
        release_id=rel["id"],
        objectives="Cover the regression suite",
        environment_ids=[env_id],
        exit_rules=[
            {"type": "min_execution_progress", "threshold": 1.0},
            {"type": "max_failed", "threshold": 0},
        ],
        risks=[{"description": "Flaky payment gateway", "impact": "high", "mitigation": "Retry"}],
        start_date="2026-11-01",
        end_date="2026-11-30",
    )
    assert plan["key"].endswith("-PL-1")  # BR-16
    assert plan["status"] == "draft"
    assert plan["exit_rules"] == [
        {"type": "min_execution_progress", "threshold": 1.0},
        {"type": "max_failed", "threshold": 0},
    ]
    assert plan["risks"][0]["impact"] == "high"
    assert plan["environment_ids"] == [env_id]
    # audit recorded
    with world.factory() as s:
        actions = [
            a[0]
            for a in s.execute(
                text("SELECT action FROM audit_events WHERE entity_id = :id ORDER BY occurred_at"),
                {"id": plan["id"]},
            ).all()
        ]
    assert "plan.created" in actions


def test_us_070_validation(world: World) -> None:
    sp = Space(world)
    # name too short
    assert sp.admin.post(sp.url("/test-plans"), json={"name": "ab", "type": "regression"}).status_code == 422
    # end before start
    bad = sp.admin.post(
        sp.url("/test-plans"),
        json={"name": "Bad dates", "type": "smoke", "start_date": "2026-11-30", "end_date": "2026-11-01"},
    )
    assert bad.status_code == 422
    # too many risks
    many = [{"description": f"r{i}", "impact": "low"} for i in range(51)]
    assert (
        sp.admin.post(
            sp.url("/test-plans"), json={"name": "Many risks", "type": "smoke", "risks": many}
        ).status_code
        == 422
    )
    # duplicate name
    sp.create_plan(name="Dupe")
    assert (
        sp.admin.post(sp.url("/test-plans"), json={"name": "dupe", "type": "smoke"}).json()["code"]
        == "name_taken"
    )


def test_us_070_patch_plan_audits_changes(world: World) -> None:
    sp = Space(world)
    plan = sp.create_plan(name="Editable")
    r = sp.admin.patch(
        f"/api/v1/test-plans/{plan['id']}",
        json={"name": "Renamed", "objectives": "New objective", "row_version": plan["row_version"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["row_version"] == plan["row_version"] + 1


def test_us_070_status_lifecycle(world: World) -> None:
    """Plan status machine: draft → active → completed, step back allowed; bad jumps → 422; archive guarded."""
    sp = Space(world)
    plan = sp.create_plan(name="Lifecycle")
    assert plan["status"] == "draft"
    assert set(plan["allowed_transitions"]) == {"active"}

    def patch(status: str, rv: int) -> Any:
        return sp.admin.patch(f"/api/v1/test-plans/{plan['id']}", json={"status": status, "row_version": rv})

    # draft → completed is not allowed (must go through active)
    bad = patch("completed", plan["row_version"])
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_transition"
    # draft → active
    active = patch("active", plan["row_version"])
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    assert set(active.json()["allowed_transitions"]) == {"draft", "completed"}
    # active → completed
    done = patch("completed", active.json()["row_version"])
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    # completed → active (step back)
    back = patch("active", done.json()["row_version"])
    assert back.status_code == 200
    assert back.json()["status"] == "active"
    # cannot set archived via PATCH (use the archive action)
    arch = patch("archived", back.json()["row_version"])
    assert arch.status_code == 422
    assert arch.json()["code"] == "invalid_transition"


# -- TCMS-051: add cases with exclusions report (FR-PLN-002, BR-13) -------------------------------


def test_br_13_us_071_add_cases_reports_exclusions(world: World) -> None:
    """TCMS-051 / BR-13: added/skipped counts are correct; archived cases are excluded with reasons."""
    sp = Space(world)
    plan = sp.create_plan(name="Selection plan")
    c1, _k1 = sp.case("Case one")
    c2, _k2 = sp.case("Case two")
    c3, k3 = sp.case("Archived case")
    # archive c3 (BR-13: cannot be added)
    assert sp.admin.post(f"/api/v1/test-cases/{c3}/archive", json={}).status_code == 200

    r = sp.admin.post(
        f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1), str(c2), str(c3)]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 2
    skipped = {x["key"]: x["reason"] for x in body["skipped"]}
    assert skipped == {k3: "archived"}

    # adding c1 again is skipped as already_in_plan
    again = sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]}).json()
    assert again["added"] == 0
    assert again["skipped"][0]["reason"] == "already_in_plan"


def test_us_071_add_by_folder_and_remove(world: World) -> None:
    sp = Space(world)
    plan = sp.create_plan(name="Folder plan")
    c1, _ = sp.case("Case A")
    sp.case("Case B")
    r = sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"folder_ids": [str(sp.folder)]}).json()
    assert r["added"] == 2
    listed = sp.admin.get(f"/api/v1/test-plans/{plan['id']}/cases").json()
    assert listed["total"] == 2
    # remove one
    rem = sp.admin.request(
        "DELETE", f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]}
    ).json()
    assert rem["count"] == 1
    assert sp.admin.get(f"/api/v1/test-plans/{plan['id']}/cases").json()["total"] == 1


def test_us_071_saved_view_rejected_until_m6(world: World) -> None:
    """Q2: saved_view_id is accepted by the schema but refused with 422 until M6."""
    sp = Space(world)
    plan = sp.create_plan(name="SV plan")
    r = sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"saved_view_id": str(uuid4())})
    assert r.status_code == 422, r.text


# US-072 (plan requirement references, ADR-024): tests/api/test_requirements.py::test_us_072_plan_requirements_link_and_unlink


# -- US-073: clone (FR-PLN-006) -------------------------------------------------------------------


def test_us_073_clone_copies_everything_except_cycles(world: World) -> None:
    sp = Space(world)
    plan = sp.create_plan(name="Original", objectives="Keep me")
    c1, _ = sp.case("Case A")
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]})
    r = sp.admin.post(f"/api/v1/test-plans/{plan['id']}/clone", json={})
    assert r.status_code == 201, r.text
    clone = r.json()
    assert clone["name"] == "Copy of Original"
    assert clone["status"] == "draft"
    assert clone["objectives"] == "Keep me"
    assert clone["id"] != plan["id"]
    assert sp.admin.get(f"/api/v1/test-plans/{clone['id']}/cases").json()["total"] == 1


# -- US-074: plan cases with per-cycle results ----------------------------------------------------


def test_us_074_plan_cases_list(world: World) -> None:
    sp = Space(world)
    plan = sp.create_plan(name="View plan")
    c1, k1 = sp.case("Case one")
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]})
    listed = sp.admin.get(f"/api/v1/test-plans/{plan['id']}/cases").json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["key"] == k1
    assert item["results"] == []  # no cycles yet


# -- archive --------------------------------------------------------------------------------------


def test_us_070_archive_plan_is_read_only(world: World) -> None:
    sp = Space(world)
    plan = sp.create_plan(name="To archive")
    assert sp.admin.post(f"/api/v1/test-plans/{plan['id']}/archive").json()["archived"] is True
    # editing an archived plan is refused
    r = sp.admin.patch(
        f"/api/v1/test-plans/{plan['id']}", json={"name": "Nope", "row_version": plan["row_version"] + 1}
    )
    assert r.status_code == 409
    # archived plans are hidden from the default list
    assert all(p["name"] != "To archive" for p in sp.admin.get(sp.url("/test-plans")).json()["items"])


# -- exit rules, people, cycles of a plan ---------------------------------------------------------


def test_us_070_exit_rules_are_validated_against_the_rule_types(world: World) -> None:
    """FR-PLN-005 / docs/02 §11.4: rule types, percentage 0–1, counts, required params."""
    sp = Space(world)
    for bad in (
        [{"type": "pass_rate_above", "threshold": 0.9}],
        [{"type": "min_pass_rate", "threshold": 95}],
        [{"type": "max_blocked", "threshold": 1.5}],
        [{"type": "max_failed", "threshold": -1}],
        [{"type": "tag_fully_executed", "threshold": 1}],
    ):
        r = sp.admin.post(sp.url("/test-plans"), json={"name": "Rules", "type": "smoke", "exit_rules": bad})
        assert r.status_code == 422, (bad, r.text)
    ok = sp.create_plan(
        name="Good rules",
        exit_rules=[
            {"type": "min_pass_rate_applicable", "threshold": 0.95},
            {"type": "max_blocked", "threshold": 2},
            {"type": "tag_fully_executed", "threshold": 1, "params": {"tag": "smoke"}},
        ],
    )
    assert [r["type"] for r in ok["exit_rules"]] == [
        "min_pass_rate_applicable",
        "max_blocked",
        "tag_fully_executed",
    ]


def test_us_070_owner_and_members_must_be_project_members(world: World) -> None:
    sp = Space(world)
    outsider = world.user(sp.org, "Outsider")
    r = sp.admin.post(
        sp.url("/test-plans"), json={"name": "People", "type": "smoke", "member_ids": [str(outsider.id)]}
    )
    assert r.status_code == 422
    world.member(sp.org, sp.pid, outsider, "qa_engineer")
    assert sp.create_plan(name="People ok", member_ids=[str(outsider.id)])["member_ids"] == [str(outsider.id)]


def test_us_074_plan_cases_show_results_of_the_plans_cycles_only(world: World) -> None:
    """docs/02 §6.2: per case, its result in each cycle created from the plan (not unrelated cycles)."""
    sp = Space(world)
    c1, _ = sp.case("Planned case")
    plan = sp.create_plan(name="Results plan")
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]})
    env_id = sp.admin.get(sp.url("/environments")).json()[0]["id"]
    from_plan = sp.admin.post(
        sp.url("/cycles"),
        json={
            "name": "Plan cycle",
            "environment_id": env_id,
            "plan_id": plan["id"],
            "selection": {"from_plan": True},
        },
    ).json()["cycle"]
    sp.admin.post(
        sp.url("/cycles"),
        json={"name": "Unrelated cycle", "environment_id": env_id, "selection": {"case_ids": [str(c1)]}},
    )
    item = sp.admin.get(f"/api/v1/test-plans/{plan['id']}/cases").json()["items"][0]
    assert item["results"] == [
        {"cycle_id": from_plan["id"], "cycle_key": from_plan["key"], "status": "not_run"}
    ]
    assert item["priority"] == "medium"
    detail = sp.admin.get(f"/api/v1/test-plans/{plan['id']}", params={"include": "cycles,cases"}).json()
    assert [c["key"] for c in detail["cycles"]] == [from_plan["key"]]
    assert detail["cycles"][0]["total"] == 1
    assert detail["case_ids"] == [str(c1)]
    assert sp.admin.get(f"/api/v1/test-plans/{plan['id']}", params={"include": "nope"}).status_code == 400
