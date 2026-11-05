"""M3 E08 — cycles and runs (US-080…087). API tests for FR-EXE-001…004/011/012/013, BR-03/04/05/11/12/31.

Acceptance: AC-PLN-01 (TCMS-052), AC-PLN-02 (TCMS-053), TCMS-054/055/056/057/058/059/060, TCMS-025b.
The runner (recording/finalizing attempts) is M4; tests insert result rows directly where a finalized or
draft attempt is needed (close contract, replace run).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from tcms.core import clock, ids
from tcms.platform.jobs.worker import run_one
from tests.world import ApiClient, OrgHandle, World

pytestmark = pytest.mark.integration


class Space:
    """An org with one project, an admin client, a folder and the project's first environment."""

    def __init__(self, world: World, key: str = "SPARK") -> None:
        self.world = world
        self.org: OrgHandle = world.org()
        self.pid = world.project(self.org, key)
        self.admin: ApiClient = world.login(self.org.admin)
        self.folder = world.folder(self.org, self.pid, "Suite")
        self.env_id = self.admin.get(self.purl("/environments")).json()[0]["id"]

    def purl(self, suffix: str = "") -> str:
        return f"/api/v1/projects/{self.pid}{suffix}"

    def case(self, title: str | None = None, folder: UUID | None = None) -> tuple[UUID, str]:
        return self.world.case(self.org, self.pid, folder or self.folder, title)

    def create_cycle(self, **overrides: Any) -> dict[str, Any]:
        """POST /cycles → the response body `{cycle, added, skipped, runs_pending}`."""
        body = {"name": overrides.pop("name", "Regression cycle"), "environment_id": self.env_id, **overrides}
        r = self.admin.post(self.purl("/cycles"), json=body)
        assert r.status_code in (201, 202), r.text
        return r.json()

    def runs(self, cycle_id: str, **params: Any) -> list[dict[str, Any]]:
        r = self.admin.get(f"/api/v1/cycles/{cycle_id}/runs", params={"page_size": 200, **params})
        assert r.status_code == 200, r.text
        return list(r.json()["items"])

    def cycle(self, cycle_id: str) -> dict[str, Any]:
        r = self.admin.get(f"/api/v1/cycles/{cycle_id}")
        assert r.status_code == 200, r.text
        return dict(r.json())

    def member(self, name: str, role: str) -> Any:
        u = self.world.user(self.org, name)
        self.world.member(self.org, self.pid, u, role)
        return u


def _seed_result(sp: Space, run_id: str, *, state: str, status: str = "passed") -> str:
    """Insert an attempt directly (the runner is M4). A final attempt also becomes the run's latest."""
    rid = ids.new_id()
    now = clock.now()
    final = state == "final"
    with sp.world.factory() as s:
        s.execute(
            text(
                "INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, state, "
                "status, source, executed_by, started_at, finished_at, environment_id, skipped_steps) "
                "SELECT :id, :org, :p, :run, coalesce(max(attempt_no), 0) + 1, :state, :status, 'manual', :by, "
                ":now, :fin, :env, 0 FROM test_results WHERE run_id = :run"
            ),
            {
                "id": str(rid),
                "org": str(sp.org.id),
                "p": str(sp.pid),
                "run": run_id,
                "state": state,
                "status": status if final else None,
                "by": str(sp.org.admin.id),
                "now": now,
                "fin": now if final else None,
                "env": sp.env_id,
            },
        )
        s.execute(
            text(
                "UPDATE test_runs SET latest_result_id = :r, status = :st WHERE id = :run"
                if final
                else "UPDATE test_runs SET status = 'in_progress' WHERE id = :run"
            ),
            {"r": str(rid), "st": status, "run": run_id},
        )
        s.commit()
    return str(rid)


def _rows(world: World, sql: str, **params: Any) -> list[Any]:
    with world.factory() as s:
        return list(s.execute(text(sql), params).all())


def _bump_version(sp: Space, case_id: UUID) -> None:
    """Save new content to create the next version (BR-01)."""
    detail = sp.admin.get(f"/api/v1/test-cases/{case_id}").json()
    r = sp.admin.put(
        f"/api/v1/test-cases/{case_id}/content",
        json={
            "content": {
                "format": "steps",
                "title": detail["title"],
                "steps": [{"action": f"Changed {detail['row_version']}", "expected_result": "New"}],
            },
            "row_version": detail["row_version"],
        },
    )
    assert r.status_code == 200, r.text


# -- create (US-080) ------------------------------------------------------------------------------


@pytest.mark.br("BR-12")
def test_br_03_br_12_ac_pln_01_create_cycle_from_plan(world: World) -> None:
    """AC-PLN-01 / TCMS-052: plan cases that are archived or deprecated are skipped with reasons."""
    sp = Space(world)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Reg plan", "type": "regression"}).json()
    good = [sp.case(f"Good {i}") for i in range(3)]
    arch_id, arch_key = sp.case("Archived")
    dep_id, dep_key = sp.case("Deprecated")
    ids_ = [str(c[0]) for c in good] + [str(arch_id), str(dep_id)]
    assert (
        sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": ids_}).json()["added"] == 5
    )
    assert sp.admin.post(f"/api/v1/test-cases/{arch_id}/archive", json={}).status_code == 200
    assert sp.admin.post(f"/api/v1/test-cases/{dep_id}/deprecate", json={}).status_code == 200

    r = sp.admin.post(
        sp.purl("/cycles"),
        json={
            "name": "From plan",
            "environment_id": sp.env_id,
            "plan_id": plan["id"],
            "selection": {"from_plan": True},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["added"] == 3
    assert body["runs_pending"] is False
    assert {x["key"]: x["reason"] for x in body["skipped"]} == {arch_key: "archived", dep_key: "deprecated"}
    cyc = body["cycle"]
    assert cyc["key"].endswith("-CY-1")  # BR-16
    assert cyc["plan"]["key"] == plan["key"]
    assert cyc["environment"]["id"] == sp.env_id
    assert cyc["status"] == "planned"
    # BR-12: adding a case that already has a run is skipped
    again = sp.admin.post(f"/api/v1/cycles/{cyc['id']}/runs", json={"case_ids": [str(good[0][0])]}).json()
    assert again == {"added": 0, "skipped": [{"key": good[0][1], "reason": "already_in_cycle"}]}


def test_br_03_pins_the_approved_version_when_approval_is_enforced(world: World) -> None:
    """BR-03/BR-17: with approval enforced a case without an approved version is skipped."""
    sp = Space(world)
    proj = sp.admin.get(sp.purl("")).json()
    patched = sp.admin.patch(
        sp.purl(""), json={"settings": {"approval_required": True}, "row_version": proj["row_version"]}
    )
    assert patched.status_code == 200, patched.text
    cid, key = sp.case("Needs approval")
    r = sp.create_cycle(name="Approval cycle", selection={"case_ids": [str(cid)]})
    assert r["added"] == 0
    assert r["skipped"] == [{"key": key, "reason": "no_eligible_version"}]


def test_selection_narrows_plan_cases_and_filters_priority(world: World) -> None:
    """docs/07 §5.8: "From plan … filter: Priority / Tag / Folder" narrows the plan's cases."""
    sp = Space(world)
    other = world.folder(sp.org, sp.pid, "Other")
    a, _ = sp.case("In suite A")
    b, _ = sp.case("In other B", folder=other)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Narrow plan", "type": "smoke"}).json()
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(a), str(b)]})
    narrowed = sp.create_cycle(
        name="Narrowed", plan_id=plan["id"], selection={"from_plan": True, "folder_ids": [str(other)]}
    )
    assert narrowed["added"] == 1
    assert [r["test_case"]["id"] for r in sp.runs(narrowed["cycle"]["id"])] == [str(b)]
    # medium is the default priority: a "critical" filter selects nothing
    none = sp.create_cycle(
        name="Critical only", selection={"case_ids": [str(a), str(b)], "priorities": ["critical"]}
    )
    assert none["added"] == 0


def test_runs_are_positioned_in_folder_tree_order_then_key(world: World) -> None:
    """docs/02 §7.1: default order is folder tree order, then case key (not the order of the request)."""
    sp = Space(world)
    second = world.folder(sp.org, sp.pid, "Zeta")  # created after "Suite" → later sibling
    z, _ = sp.case("Case in Zeta", folder=second)
    s1, _ = sp.case("Case one in Suite")
    s2, _ = sp.case("Case two in Suite")
    cyc = sp.create_cycle(name="Ordered", selection={"case_ids": [str(z), str(s2), str(s1)]})
    runs = sp.runs(cyc["cycle"]["id"], sort="position")
    assert [r["test_case"]["id"] for r in runs] == [str(s1), str(s2), str(z)]
    assert [r["position"] for r in runs] == [1, 2, 3]


def test_tcms_025b_archived_environment_is_not_selectable(world: World) -> None:
    """AC-WS-03 / TCMS-025b."""
    sp = Space(world)
    assert sp.admin.post(f"/api/v1/environments/{sp.env_id}/archive").status_code == 200
    r = sp.admin.post(
        sp.purl("/cycles"), json={"name": "Bad env", "environment_id": sp.env_id, "selection": {}}
    )
    assert r.status_code == 422, r.text
    assert r.json()["errors"][0]["field"] == "environment_id"


def test_tcms_054_large_cycle_is_created_in_the_background(world: World, clean_jobs: None) -> None:
    """TCMS-054: over the inline limit → 202 runs_pending, then the job creates the runs. The limit is
    lowered for the test instead of creating 500 cases."""
    from tcms.execution import rules as exec_rules

    sp = Space(world)
    case_ids = [str(sp.case(f"Bulk {i}")[0]) for i in range(3)]
    with world.factory() as s:  # invitation emails queued while building the world
        s.execute(text("DELETE FROM jobs"))
        s.commit()
    original = exec_rules.INLINE_RUN_LIMIT
    exec_rules.INLINE_RUN_LIMIT = 2
    try:
        r = sp.admin.post(
            sp.purl("/cycles"),
            json={"name": "Big cycle", "environment_id": sp.env_id, "selection": {"case_ids": case_ids}},
        )
    finally:
        exec_rules.INLINE_RUN_LIMIT = original
    assert r.status_code == 202, r.text
    assert r.json()["runs_pending"] is True
    cid = r.json()["cycle"]["id"]
    assert sp.cycle(cid)["runs_pending"] is True
    assert run_one(world.factory, "test-worker")
    cyc = sp.cycle(cid)
    assert cyc["runs_pending"] is False
    assert cyc["summary"]["total"] == 3


# -- summary and progress (US-083) ----------------------------------------------------------------


def test_us_083_summary_is_the_execution_summary_with_progress_groups(world: World) -> None:
    """FR-EXE-013 / docs/06 §5.7: rates carry numerator and denominator; groups by assignee and folder."""
    sp = Space(world)
    tester = sp.member("Tester", "qa_engineer")
    other = world.folder(sp.org, sp.pid, "Payments")
    a, _ = sp.case("Passes")
    b, _ = sp.case("Fails")
    c, _ = sp.case("Waits", folder=other)
    cyc = sp.create_cycle(name="Summary", selection={"case_ids": [str(a), str(b), str(c)]})["cycle"]
    runs = {r["test_case"]["id"]: r for r in sp.runs(cyc["id"])}
    _seed_result(sp, runs[str(a)]["id"], state="final", status="passed")
    _seed_result(sp, runs[str(b)]["id"], state="final", status="failed")
    sp.admin.post(
        f"/api/v1/cycles/{cyc['id']}/runs/assign",
        json={"run_ids": [runs[str(c)]["id"]], "assignee_id": str(tester.id)},
    )
    summary = sp.cycle(cyc["id"])
    s = summary["summary"]
    assert (s["total"], s["applicable"], s["executed"], s["passed"], s["failed"], s["not_run"]) == (
        3,
        3,
        2,
        1,
        1,
        1,
    )
    assert s["execution_progress"] == {"numerator": 2, "denominator": 3, "value": pytest.approx(2 / 3)}
    assert s["pass_rate"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    by_folder = {g["name"]: g["summary"]["total"] for g in summary["progress_by_folder"]}
    assert by_folder == {"Suite": 2, "Payments": 1}
    by_assignee = {g["name"]: g["summary"]["total"] for g in summary["progress_by_assignee"]}
    assert by_assignee == {"Tester": 1, "Unassigned": 2}
    listed = sp.admin.get(sp.purl("/cycles")).json()["items"][0]
    assert listed["summary"]["pass_rate"]["value"] == 0.5


def test_empty_cycle_rates_are_undefined(world: World) -> None:
    """BR-24: rates are null when the denominator is 0, never 0 % or 100 %."""
    sp = Space(world)
    s = sp.create_cycle(name="Empty")["cycle"]["summary"]
    assert s["total"] == 0
    assert s["execution_progress"]["value"] is None
    assert s["pass_rate"]["value"] is None


def test_runs_list_filters_and_sorts(world: World) -> None:
    """docs/06 §4.6: status, assignee (me/none), folder, priority, tag, q, include_superseded; sorts."""
    sp = Space(world)
    other = world.folder(sp.org, sp.pid, "API")
    a, ka = sp.case("Login works")
    b, _ = sp.case("Logout works")
    c, _ = sp.case("POST readings", folder=other)
    sp.admin.patch(f"/api/v1/test-cases/{b}", json={"priority": "critical", "row_version": 1})
    sp.admin.patch(f"/api/v1/test-cases/{c}", json={"tags": ["api"], "row_version": 1})
    cid = sp.create_cycle(name="Filters", selection={"case_ids": [str(a), str(b), str(c)]})["cycle"]["id"]
    runs = {r["test_case"]["id"]: r for r in sp.runs(cid)}
    sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign", json={"run_ids": [runs[str(a)]["id"]], "assignee_id": None}
    )
    claimed = sp.admin.post(f"/api/v1/runs/{runs[str(a)]['id']}/claim")
    assert claimed.status_code == 200, claimed.text

    def keys(**params: Any) -> set[str]:
        return {r["test_case"]["id"] for r in sp.runs(cid, **params)}

    assert keys(folder_id=str(other)) == {str(c)}
    assert keys(priority="critical") == {str(b)}
    assert keys(tag="api") == {str(c)}
    assert keys(q=ka) == {str(a)}
    assert keys(q="Logout") == {str(b)}
    assert keys(assignee_id="me") == {str(a)}
    assert keys(assignee_id="none") == {str(b), str(c)}
    assert keys(status="not_run") == {str(a), str(b), str(c)}
    by_priority = [r["test_case"]["id"] for r in sp.runs(cid, sort="priority")]
    assert by_priority[0] == str(b)
    assert sp.admin.get(f"/api/v1/cycles/{cid}/runs", params={"sort": "nope"}).status_code == 400
    assert sp.admin.get(f"/api/v1/cycles/{cid}/runs", params={"colour": "red"}).status_code == 400


# -- add / remove (US-081) ------------------------------------------------------------------------


def test_tcms_057_remove_run_with_results_refused(world: World) -> None:
    sp = Space(world)
    c1, k1 = sp.case("Removable")
    cid = sp.create_cycle(name="Remove cycle", selection={"case_ids": [str(c1)]})["cycle"]["id"]
    run = sp.runs(cid)[0]
    r = sp.admin.request("DELETE", f"/api/v1/cycles/{cid}/runs", json={"run_ids": [run["id"]]})
    assert r.status_code == 200, r.text
    assert r.json() == {"count": 1}
    assert sp.admin.post(f"/api/v1/cycles/{cid}/runs", json={"case_ids": [str(c1)]}).json()["added"] == 1
    run2 = sp.runs(cid)[0]
    _seed_result(sp, run2["id"], state="final")
    bad = sp.admin.request("DELETE", f"/api/v1/cycles/{cid}/runs", json={"run_ids": [run2["id"]]})
    assert bad.status_code == 409
    assert bad.json()["code"] == "run_has_results"
    assert bad.json()["runs"][0]["case_key"] == k1
    # removing a run of another cycle is a 404, not a silent no-op
    other = sp.create_cycle(name="Other cycle")["cycle"]["id"]
    assert (
        sp.admin.request("DELETE", f"/api/v1/cycles/{other}/runs", json={"run_ids": [run2["id"]]}).status_code
        == 404
    )


# -- assignment (US-082) --------------------------------------------------------------------------


def test_tcms_055_bulk_assign_by_folder_notifies_the_assignee(world: World) -> None:
    """TCMS-055: assign every run of a folder through the filter form; the assignee is notified."""
    sp = Space(world)
    tester = sp.member("Tester", "qa_engineer")
    other = world.folder(sp.org, sp.pid, "Checkout")
    a, _ = sp.case("In suite")
    b, _ = sp.case("Checkout one", folder=other)
    c, _ = sp.case("Checkout two", folder=other)
    cid = sp.create_cycle(name="Assign cycle", selection={"case_ids": [str(a), str(b), str(c)]})["cycle"][
        "id"
    ]
    r = sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign",
        json={"filter": {"folder_id": str(other)}, "assignee_id": str(tester.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"count": 2}
    assigned = {x["test_case"]["id"] for x in sp.runs(cid, assignee_id=str(tester.id))}
    assert assigned == {str(b), str(c)}
    notes = _rows(world, "SELECT type, payload FROM notifications WHERE user_id = :u", u=str(tester.id))
    assert [n[0] for n in notes] == ["runs.assigned"]
    assert notes[0][1]["count"] == 2
    # one audit event per run, sharing a bulk id (docs/04 §5.2)
    events = _rows(
        world,
        "SELECT context->>'bulk_operation_id' FROM audit_events WHERE action = 'run.assigned' AND project_id = :p",
        p=str(sp.pid),
    )
    assert len(events) == 2
    assert len({e[0] for e in events}) == 1
    # assignee must hold run.execute; run_ids and filter are exclusive
    viewer = sp.member("Viewer", "viewer")
    bad = sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign",
        json={"filter": {"folder_id": str(other)}, "assignee_id": str(viewer.id)},
    )
    assert bad.status_code == 422
    assert sp.admin.post(f"/api/v1/cycles/{cid}/runs/assign", json={"assignee_id": None}).status_code == 422


def test_tcms_056_claim_a_pool_run(world: World) -> None:
    sp = Space(world)
    tester = sp.member("Tester", "qa_engineer")
    other = sp.member("Other", "qa_engineer")
    c1, _ = sp.case("Claimable")
    cid = sp.create_cycle(name="Pool", selection={"case_ids": [str(c1)]})["cycle"]["id"]
    run = sp.runs(cid)[0]
    tc = world.login(tester)
    claimed = tc.post(f"/api/v1/runs/{run['id']}/claim")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assignee"]["id"] == str(tester.id)
    # someone else cannot take it any more; a viewer cannot claim at all
    assert world.login(other).post(f"/api/v1/runs/{run['id']}/claim").status_code == 409
    viewer = sp.member("Viewer", "viewer")
    assert world.login(viewer).post(f"/api/v1/runs/{run['id']}/claim").status_code == 403


# -- lifecycle (US-084) ---------------------------------------------------------------------------


def test_tcms_058_close_lists_drafts_and_discard_removes_them(world: World) -> None:
    """TCMS-058: close with drafts → 409 listing them; with discard the drafts are deleted and the run
    falls back to its latest final status."""
    sp = Space(world)
    a, ka = sp.case("Has a draft")
    b, _ = sp.case("Has a final and a draft")
    cid = sp.create_cycle(name="Close cycle", selection={"case_ids": [str(a), str(b)]})["cycle"]["id"]
    assert sp.admin.post(f"/api/v1/cycles/{cid}/start").json()["status"] == "active"
    runs = {r["test_case"]["id"]: r for r in sp.runs(cid)}
    draft_a = _seed_result(sp, runs[str(a)]["id"], state="draft")
    _seed_result(sp, runs[str(b)]["id"], state="final", status="failed")
    _seed_result(sp, runs[str(b)]["id"], state="draft")

    r = sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "draft_exists"
    drafts = r.json()["drafts"]
    assert {d["run_id"] for d in drafts} == {runs[str(a)]["id"], runs[str(b)]["id"]}
    assert ka in {d["case_key"] for d in drafts}
    assert sp.cycle(cid)["status"] == "active"

    ok = sp.admin.post(f"/api/v1/cycles/{cid}/close", json={"discard_drafts": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "closed"
    assert ok.json()["closed_by"]["id"] == str(sp.org.admin.id)
    assert (
        _rows(
            world,
            "SELECT count(*) FROM test_results WHERE state = 'draft' AND project_id = :p",
            p=str(sp.pid),
        )[0][0]
        == 0
    )
    statuses = {r["test_case"]["id"]: r["status"] for r in sp.runs(cid)}
    assert statuses == {str(a): "not_run", str(b): "failed"}
    discarded = _rows(world, "SELECT entity_id FROM audit_events WHERE action = 'result.discarded'")
    assert str(draft_a) in {str(d[0]) for d in discarded}


def test_tcms_059_reopen_requires_permission_and_reason(world: World) -> None:
    sp = Space(world)
    cid = sp.create_cycle(name="Reopen cycle")["cycle"]["id"]
    sp.admin.post(f"/api/v1/cycles/{cid}/start")
    sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    lead = world.login(sp.member("Lead", "qa_lead"))  # cycle.manage but not cycle.reopen
    assert lead.post(f"/api/v1/cycles/{cid}/reopen", json={"reason": "retest"}).status_code == 403
    missing = sp.admin.post(f"/api/v1/cycles/{cid}/reopen", json={"reason": "  "})
    assert missing.status_code == 422
    assert missing.json()["code"] == "reason_required"
    ok = sp.admin.post(f"/api/v1/cycles/{cid}/reopen", json={"reason": "More testing"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "active"
    assert ok.json()["closed_at"] is None
    reasons = _rows(
        world,
        "SELECT context->>'reason' FROM audit_events WHERE action = 'cycle.reopened' AND entity_id = :c",
        c=cid,
    )
    assert reasons == [("More testing",)]


@pytest.mark.br("BR-11")
def test_br_11_closed_cycle_blocks_changes(world: World) -> None:
    sp = Space(world)
    tester = sp.member("Tester", "qa_engineer")
    c1, _ = sp.case("Case A")
    c2, _ = sp.case("Case B")
    cid = sp.create_cycle(name="Closed cycle", selection={"case_ids": [str(c1)]})["cycle"]["id"]
    run = sp.runs(cid)[0]
    sp.admin.post(f"/api/v1/cycles/{cid}/start")
    sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    for method, url, body in [
        ("post", f"/api/v1/cycles/{cid}/runs", {"case_ids": [str(c2)]}),
        (
            "post",
            f"/api/v1/cycles/{cid}/runs/assign",
            {"run_ids": [run["id"]], "assignee_id": str(tester.id)},
        ),
        ("delete", f"/api/v1/cycles/{cid}/runs", {"run_ids": [run["id"]]}),
        ("post", f"/api/v1/runs/{run['id']}/claim", None),
        ("post", f"/api/v1/cycles/{cid}/runs/reorder", {"sort_by": "folder"}),
        ("post", f"/api/v1/cycles/{cid}/runs/update-versions", None),
    ]:
        r = sp.admin.request(method.upper(), url, json=body)
        assert r.status_code == 409, f"{method} {url}: {r.text}"
        assert r.json()["code"] == "cycle_closed"


def test_archive_needs_a_closed_cycle(world: World) -> None:
    sp = Space(world)
    cid = sp.create_cycle(name="Archive me")["cycle"]["id"]
    assert sp.admin.post(f"/api/v1/cycles/{cid}/archive").json()["code"] == "invalid_status"
    sp.admin.post(f"/api/v1/cycles/{cid}/start")
    sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    assert sp.admin.post(f"/api/v1/cycles/{cid}/archive").json()["archived"] is True
    assert all(c["id"] != cid for c in sp.admin.get(sp.purl("/cycles")).json()["items"])
    assert any(
        c["id"] == cid
        for c in sp.admin.get(sp.purl("/cycles"), params={"include_archived": "true"}).json()["items"]
    )


def test_tcms_060_clone_only_failed_at_current_versions(world: World) -> None:
    sp = Space(world)
    failed, _ = sp.case("Will fail")
    passed, _ = sp.case("Will pass")
    src = sp.create_cycle(name="Source", selection={"case_ids": [str(failed), str(passed)]})["cycle"]
    runs = {r["test_case"]["id"]: r for r in sp.runs(src["id"])}
    _seed_result(sp, runs[str(failed)]["id"], state="final", status="failed")
    _seed_result(sp, runs[str(passed)]["id"], state="final", status="passed")
    _bump_version(sp, failed)
    clone = sp.admin.post(
        f"/api/v1/cycles/{src['id']}/clone", json={"name": "Retest round", "only_statuses": ["failed"]}
    )
    assert clone.status_code == 201, clone.text
    assert clone.json()["added"] == 1
    new_runs = sp.runs(clone.json()["cycle"]["id"])
    assert [r["test_case"]["id"] for r in new_runs] == [str(failed)]
    assert new_runs[0]["pinned_version_no"] == 2  # current eligible version, not the source run's v1
    assert new_runs[0]["status"] == "not_run"
    assert (
        sp.admin.post(
            f"/api/v1/cycles/{src['id']}/clone", json={"name": "Bad", "only_statuses": ["passed"]}
        ).status_code
        == 422
    )


# -- sync (US-085) --------------------------------------------------------------------------------


def test_br_31_ac_pln_02_sync_from_plan(world: World) -> None:
    sp = Space(world)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Sync plan", "type": "regression"}).json()
    c1, _ = sp.case("Case 1")
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]})
    created = sp.create_cycle(name="Sync cycle", plan_id=plan["id"], selection={"from_plan": True})
    cid = created["cycle"]["id"]
    assert created["added"] == 1
    run1 = sp.runs(cid)[0]
    _seed_result(sp, run1["id"], state="final", status="failed")
    added = [str(sp.case(f"New {i}")[0]) for i in range(3)]
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": added})
    sp.admin.request("DELETE", f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]})
    assert sp.cycle(cid)["summary"]["total"] == 1  # unchanged until sync (AC-PLN-02)
    synced = sp.admin.post(f"/api/v1/cycles/{cid}/sync-from-plan")
    assert synced.status_code == 200, synced.text
    assert synced.json()["added"] == 3
    assert sp.cycle(cid)["summary"]["total"] == 4  # the removed plan case keeps its run with results
    assert sp.admin.post(f"/api/v1/cycles/{cid}/sync-from-plan").json()["added"] == 0
    plain = sp.create_cycle(name="No plan")["cycle"]["id"]
    assert sp.admin.post(f"/api/v1/cycles/{plain}/sync-from-plan").json()["code"] == "invalid_status"


# -- versions (US-086) ----------------------------------------------------------------------------


@pytest.mark.br("BR-04")
def test_br_04_update_to_latest_only_without_attempts(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("Versioned")
    cid = sp.create_cycle(name="Update cycle", selection={"case_ids": [str(c1)]})["cycle"]["id"]
    run = sp.runs(cid)[0]
    assert (run["pinned_version_no"], run["newer_version_no"]) == (1, None)
    _bump_version(sp, c1)
    listed = sp.runs(cid)[0]
    assert listed["newer_version_no"] == 2  # "v1↑" in the table
    detail = sp.admin.get(f"/api/v1/runs/{run['id']}").json()
    assert detail["newer_version"] == {"version_no": 2, "eligible": True, "can_update": True, "reason": None}
    r = sp.admin.post(f"/api/v1/runs/{run['id']}/update-version")
    assert r.status_code == 200, r.text
    assert r.json()["pinned_version_no"] == 2
    assert r.json()["newer_version"] is None
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/update-version").json()["code"] == "already_latest"
    _seed_result(sp, run["id"], state="final")
    _bump_version(sp, c1)
    blocked = sp.admin.get(f"/api/v1/runs/{run['id']}").json()["newer_version"]
    assert blocked == {"version_no": 3, "eligible": True, "can_update": False, "reason": "run_has_results"}
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/update-version").json()["code"] == "run_has_results"


def test_us_086_assignee_may_update_their_own_run(world: World) -> None:
    """docs/02 §7.2: cycle.manage, or the assignee holding run.execute."""
    sp = Space(world)
    tester = sp.member("Tester", "qa_engineer")
    c1, _ = sp.case("Mine")
    c2, _ = sp.case("Not mine")
    cid = sp.create_cycle(name="Assignee update", selection={"case_ids": [str(c1), str(c2)]})["cycle"]["id"]
    runs = {r["test_case"]["id"]: r for r in sp.runs(cid)}
    sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign",
        json={"run_ids": [runs[str(c1)]["id"]], "assignee_id": str(tester.id)},
    )
    _bump_version(sp, c1)
    _bump_version(sp, c2)
    tc = world.login(tester)
    assert tc.post(f"/api/v1/runs/{runs[str(c1)]['id']}/update-version").status_code == 200
    assert tc.post(f"/api/v1/runs/{runs[str(c2)]['id']}/update-version").status_code == 403


def test_us_086_bulk_update_skips_runs_without_eligible_versions(world: World) -> None:
    sp = Space(world)
    a, _ = sp.case("Bumped")
    b, _ = sp.case("Archived later")
    c, _ = sp.case("Has results")
    cid = sp.create_cycle(name="Bulk versions", selection={"case_ids": [str(a), str(b), str(c)]})["cycle"][
        "id"
    ]
    runs = {r["test_case"]["id"]: r for r in sp.runs(cid)}
    _seed_result(sp, runs[str(c)]["id"], state="final")
    for x in (a, b, c):
        _bump_version(sp, x)
    assert sp.admin.post(f"/api/v1/test-cases/{b}/archive", json={}).status_code == 200
    r = sp.admin.post(f"/api/v1/cycles/{cid}/runs/update-versions")
    assert r.status_code == 200, r.text
    assert r.json() == {"count": 1}
    versions = {x["test_case"]["id"]: x["pinned_version_no"] for x in sp.runs(cid)}
    assert versions == {str(a): 2, str(b): 1, str(c): 1}


@pytest.mark.br("BR-05")
def test_br_05_replace_run_supersedes(world: World) -> None:
    sp = Space(world)
    tester = sp.member("Tester", "qa_engineer")
    c1, _ = sp.case("To replace")
    cid = sp.create_cycle(name="Replace cycle", selection={"case_ids": [str(c1)]})["cycle"]["id"]
    run = sp.runs(cid)[0]
    sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign", json={"run_ids": [run["id"]], "assignee_id": str(tester.id)}
    )
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/replace").json()["code"] == "run_has_results"
    _seed_result(sp, run["id"], state="final", status="failed")
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/replace").json()["code"] == "already_latest"
    _bump_version(sp, c1)
    r = sp.admin.post(f"/api/v1/runs/{run['id']}/replace")
    assert r.status_code == 201, r.text
    new = r.json()
    assert (new["pinned_version_no"], new["status"], new["position"]) == (2, "not_run", run["position"])
    assert new["assignee"]["id"] == str(tester.id)
    active = sp.runs(cid)
    assert [x["id"] for x in active] == [new["id"]]
    every = sp.runs(cid, include_superseded="true")
    assert {x["id"]: x["superseded"] for x in every} == {run["id"]: True, new["id"]: False}
    old = sp.admin.get(f"/api/v1/runs/{run['id']}", params={"include": "history"}).json()
    assert old["superseded_by_run_id"] == new["id"]
    assert [h["status"] for h in old["history"]] == ["failed"]  # the old run keeps its results
    cyc = sp.cycle(cid)
    assert (cyc["summary"]["total"], cyc["superseded_runs"]) == (1, 1)  # superseded excluded from metrics
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/replace").json()["code"] == "run_superseded"


def test_get_run_includes(world: World) -> None:
    """docs/06 §5.4: run with case summary; include=version,history,draft; unknown include → 400."""
    sp = Space(world)
    c1, k1 = sp.case("Detail me")
    cid = sp.create_cycle(name="Detail cycle", selection={"case_ids": [str(c1)]})["cycle"]["id"]
    run = sp.runs(cid)[0]
    r = sp.admin.get(f"/api/v1/runs/{run['id']}", params={"include": "version,history,draft"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["test_case"]["key"] == k1
    assert body["test_case"]["folder_path"] == ["Suite"]
    assert body["cycle"]["id"] == cid
    assert body["version"]["version_no"] == 1
    assert body["version"]["steps"][0]["action"].startswith("Do")
    assert body["history"] == []
    assert body["draft"] is None
    assert sp.admin.get(f"/api/v1/runs/{run['id']}", params={"include": "queue"}).status_code == 400


# -- reorder (US-087) -----------------------------------------------------------------------------


def test_us_087_reorder_runs(world: World) -> None:
    sp = Space(world)
    ids_ = [sp.case(f"Case {i}")[0] for i in range(3)]
    sp.admin.patch(f"/api/v1/test-cases/{ids_[2]}", json={"priority": "critical", "row_version": 1})
    cid = sp.create_cycle(name="Reorder cycle", selection={"case_ids": [str(c) for c in ids_]})["cycle"]["id"]
    runs = sp.runs(cid)
    reversed_ids = [r["id"] for r in reversed(runs)]
    r = sp.admin.post(f"/api/v1/cycles/{cid}/runs/reorder", json={"run_ids_in_order": reversed_ids})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in sp.runs(cid, sort="position")] == reversed_ids
    assert (
        sp.admin.post(f"/api/v1/cycles/{cid}/runs/reorder", json={"sort_by": "priority"}).status_code == 200
    )
    assert sp.runs(cid, sort="position")[0]["test_case"]["id"] == str(ids_[2])
    sp.admin.post(f"/api/v1/cycles/{cid}/runs/reorder", json={"sort_by": "folder"})
    assert [x["test_case"]["id"] for x in sp.runs(cid, sort="position")] == [str(c) for c in ids_]
    partial = sp.admin.post(f"/api/v1/cycles/{cid}/runs/reorder", json={"run_ids_in_order": reversed_ids[:2]})
    assert partial.status_code == 422


# -- audit, keys, project archive -----------------------------------------------------------------


def test_audit_actions_follow_docs_02_13_1(world: World) -> None:
    """docs/02 §13.1: cycle.created/updated/started/closed/reopened and run.added/removed/assigned…;
    one run.added per run with a shared bulk id (docs/04 §5.2)."""
    sp = Space(world)
    ids_ = [str(sp.case(f"Audited {i}")[0]) for i in range(2)]
    cyc = sp.create_cycle(name="Audited", selection={"case_ids": ids_})["cycle"]
    sp.admin.patch(
        f"/api/v1/cycles/{cyc['id']}", json={"build": "2.5.0-rc1", "row_version": cyc["row_version"]}
    )
    sp.admin.post(f"/api/v1/cycles/{cyc['id']}/start")
    actions = [
        a[0]
        for a in _rows(
            world, "SELECT action FROM audit_events WHERE project_id = :p ORDER BY occurred_at", p=str(sp.pid)
        )
    ]
    assert "cycle.created" in actions
    assert "cycle.updated" in actions
    assert "cycle.started" in actions
    assert actions.count("run.added") == 2
    assert not [a for a in actions if a.startswith("test_cycle.")]
    added = _rows(
        world,
        "SELECT entity_type, entity_key, context->>'bulk_operation_id' FROM audit_events "
        "WHERE action = 'run.added' AND project_id = :p",
        p=str(sp.pid),
    )
    assert {a[0] for a in added} == {"test_run"}
    assert all(a[1].startswith(cyc["key"] + " / ") for a in added)
    assert len({a[2] for a in added}) == 1


def test_resolve_plan_and_cycle_keys(world: World) -> None:
    """docs/04 §11.1: URLs use keys; /resolve maps PL and CY keys too."""
    sp = Space(world)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Resolve plan", "type": "smoke"}).json()
    cyc = sp.create_cycle(name="Resolve cycle")["cycle"]
    for key, entity, target in [
        (plan["key"], "test_plan", plan["id"]),
        ("PL-1", "test_plan", plan["id"]),
        (cyc["key"], "test_cycle", cyc["id"]),
        ("cy-1", "test_cycle", cyc["id"]),
    ]:
        r = sp.admin.get(sp.purl("/resolve"), params={"key": key})
        assert r.status_code == 200, (key, r.text)
        assert (r.json()["entity_type"], r.json()["id"]) == (entity, target)
    assert sp.admin.get(sp.purl("/resolve"), params={"key": "CY-99"}).status_code == 404


def test_us_029_archive_project_needs_closed_cycles(world: World) -> None:
    """docs/02 §4.2: all cycles must be closed, or the archive closes them (review K17k)."""
    sp = Space(world, key="ARCH")
    planned = sp.create_cycle(name="Planned one")["cycle"]
    active = sp.create_cycle(name="Active one")["cycle"]
    sp.admin.post(f"/api/v1/cycles/{active['id']}/start")
    r = sp.admin.post(sp.purl("/archive"), json={"confirm_key": "ARCH"})
    assert r.status_code == 409, r.text
    assert {c["key"] for c in r.json()["open_cycles"]} == {planned["key"], active["key"]}
    assert (
        sp.admin.post(
            sp.purl("/archive"), json={"confirm_key": "WRONG", "close_open_cycles": True}
        ).status_code
        == 422
    )
    ok = sp.admin.post(sp.purl("/archive"), json={"confirm_key": "ARCH", "close_open_cycles": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "archived"
    statuses = _rows(world, "SELECT status FROM test_cycles WHERE project_id = :p", p=str(sp.pid))
    assert {s[0] for s in statuses} == {"closed"}
