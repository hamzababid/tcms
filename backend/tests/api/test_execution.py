"""M3 E08 — cycles and runs (US-080…087). API tests for FR-EXE-001…004/011/012/013, BR-03/04/05/11/12/31.

Acceptance: AC-PLN-01 (TCMS-052), AC-PLN-02 (TCMS-053), TCMS-054/055/056/057/058/059/060, TCMS-025b.
The runner (recording/finalizing attempts) is M4; tests seed result rows directly where a finalized or
draft attempt is needed (close contract, replace-run).
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
    def __init__(self, world: World, key: str = "SPARK") -> None:
        self.world = world
        self.org: OrgHandle = world.org()
        self.pid = world.project(self.org, key)
        self.admin: ApiClient = world.login(self.org.admin)
        self.folder = world.folder(self.org, self.pid, "Suite")
        self.env_id = self.admin.get(self.purl("/environments")).json()[0]["id"]

    def purl(self, suffix: str = "") -> str:
        return f"/api/v1/projects/{self.pid}{suffix}"

    def case(self, title: str | None = None) -> tuple[UUID, str]:
        return self.world.case(self.org, self.pid, self.folder, title)

    def create_cycle(self, **overrides: Any) -> dict[str, Any]:
        body = {"name": overrides.pop("name", "Regression cycle"), "environment_id": self.env_id, **overrides}
        r = self.admin.post(self.purl("/cycles"), json=body)
        assert r.status_code in (201, 202), r.text
        return r.json()

    def runs(self, cycle_id: str, **params: Any) -> dict[str, Any]:
        return self.admin.get(f"/api/v1/cycles/{cycle_id}/runs", params=params).json()


def _seed_result(
    world: World, run_id: str, project_id: UUID, org_id: UUID, env_id: str, *, state: str, executed_by: UUID
) -> str:
    """Insert a result attempt directly (the runner is M4). Updates the run's latest_result_id/status.

    `executed_by` is required by the baseline CHECK (source='automation' OR executed_by IS NOT NULL).
    """
    rid = ids.new_id()
    now = clock.now()
    status = "passed" if state == "final" else None
    with world.factory() as s:
        s.execute(
            text(
                "INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, state, "
                "status, source, executed_by, started_at, finished_at, environment_id, skipped_steps) VALUES "
                "(:id, :org, :p, :run, 1, :state, :status, 'manual', :by, :now, :fin, :env, 0)"
            ),
            {
                "id": str(rid),
                "org": str(org_id),
                "p": str(project_id),
                "run": run_id,
                "state": state,
                "status": status,
                "by": str(executed_by),
                "now": now,
                "fin": now if state == "final" else None,
                "env": env_id,
            },
        )
        if state == "final":
            s.execute(
                text("UPDATE test_runs SET latest_result_id = :r, status = 'passed' WHERE id = :run"),
                {"r": str(rid), "run": run_id},
            )
        s.commit()
    return str(rid)


# -- BR-03 / BR-12 / AC-PLN-01: create cycle with version pinning + exclusions --------------------


@pytest.mark.br("BR-12")
def test_br_03_br_12_ac_pln_01_create_cycle_from_plan(world: World) -> None:
    """AC-PLN-01 / TCMS-052: a plan of 5 cases (1 archived, 1 deprecated) → 3 runs, 2 skipped w/ reasons."""
    sp = Space(world)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Reg plan", "type": "regression"}).json()
    good = [sp.case(f"Good {i}") for i in range(3)]
    arch_id, arch_key = sp.case("Archived")
    dep_id, dep_key = sp.case("Deprecated")
    all_ids = [c[0] for c in good] + [arch_id, dep_id]
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c) for c in all_ids]})
    # archive one, deprecate another (BR-13)
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
    reasons = {x["key"]: x["reason"] for x in body["skipped"]}
    assert reasons == {arch_key: "archived", dep_key: "deprecated"}
    # BR-12: creating again from the same cases skips duplicates
    cid = body["cycle_id"]
    again = sp.admin.post(f"/api/v1/cycles/{cid}/runs", json={"case_ids": [str(good[0][0])]}).json()
    assert again["added"] == 0
    assert again["skipped"][0]["reason"] == "already_in_cycle"


def test_br_03_pins_approved_version_when_approval_enforced(world: World) -> None:
    """BR-03/BR-17: with approval enforced, a case with no approved version is skipped (no_eligible_version)."""
    sp = Space(world)
    # enable approval on the project
    proj = sp.admin.get(sp.purl("")).json()
    sp.admin.patch(
        sp.purl(""),
        json={"settings": {"approval_required": True}, "row_version": proj["row_version"]},
    )
    cid, _ = sp.case("Needs approval")
    r = sp.admin.post(
        sp.purl("/cycles"),
        json={"name": "Approval cycle", "environment_id": sp.env_id, "selection": {"case_ids": [str(cid)]}},
    ).json()
    assert r["added"] == 0
    assert r["skipped"][0]["reason"] == "no_eligible_version"


# -- TCMS-025b: archived environment not selectable -----------------------------------------------


def test_tcms_025b_archived_environment_rejected(world: World) -> None:
    sp = Space(world)
    # archive the only environment and try to create a cycle with it
    assert sp.admin.post(f"/api/v1/environments/{sp.env_id}/archive").status_code == 200
    r = sp.admin.post(
        sp.purl("/cycles"), json={"name": "Bad env", "environment_id": sp.env_id, "selection": {}}
    )
    assert r.status_code == 422, r.text


# -- TCMS-054: background creation over the inline limit ------------------------------------------


def test_tcms_054_large_cycle_created_in_background(world: World, clean_jobs: None) -> None:
    sp = Space(world)
    # Patch the inline limit down so the test does not need 500+ cases.
    from tcms.execution import rules as exec_rules

    original = exec_rules.INLINE_RUN_LIMIT
    exec_rules.INLINE_RUN_LIMIT = 2
    try:
        ids_ = [str(sp.case(f"Case {i}")[0]) for i in range(3)]
        # Drain any jobs enqueued during setup (invitation emails) so run_one picks up create_runs.
        with world.factory() as s:
            s.execute(text("DELETE FROM jobs"))
            s.commit()
        r = sp.admin.post(
            sp.purl("/cycles"),
            json={"name": "Big cycle", "environment_id": sp.env_id, "selection": {"case_ids": ids_}},
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["runs_pending"] is True
        cid = body["cycle_id"]
        assert sp.admin.get(f"/api/v1/cycles/{cid}").json()["runs_pending"] is True
        # run the background job
        ran = run_one(world.factory, "test-worker")
        assert ran
        cyc = sp.admin.get(f"/api/v1/cycles/{cid}").json()
        assert cyc["runs_pending"] is False
        assert cyc["summary"]["total"] == 3
    finally:
        exec_rules.INLINE_RUN_LIMIT = original


# -- TCMS-057: remove run with results refused ----------------------------------------------------


def test_tcms_057_remove_run_with_results_refused(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("Removable")
    cyc = sp.create_cycle(name="Remove cycle", selection={"case_ids": [str(c1)]})
    cid = cyc["cycle_id"]
    run = sp.runs(cid)["items"][0]
    # not_run with no attempts → removable
    r = sp.admin.request("DELETE", f"/api/v1/cycles/{cid}/runs", json={"run_ids": [run["id"]]})
    assert r.status_code == 200
    assert r.json()["count"] == 1
    # add again, seed a final result, then removal is refused
    sp.admin.post(f"/api/v1/cycles/{cid}/runs", json={"case_ids": [str(c1)]})
    run2 = sp.runs(cid)["items"][0]
    _seed_result(world, run2["id"], sp.pid, sp.org.id, sp.env_id, state="final", executed_by=sp.org.admin.id)
    bad = sp.admin.request("DELETE", f"/api/v1/cycles/{cid}/runs", json={"run_ids": [run2["id"]]})
    assert bad.status_code == 409
    assert bad.json()["code"] == "run_has_results"


# -- TCMS-055 / TCMS-056: assign and claim --------------------------------------------------------


def test_tcms_055_056_assign_and_claim(world: World) -> None:
    sp = Space(world)
    tester = world.user(sp.org, "Tester")
    world.member(sp.org, sp.pid, tester, "qa_engineer")  # qa_engineer holds run.execute
    c1, _ = sp.case("Assignable")
    c2, _ = sp.case("Claimable")
    cyc = sp.create_cycle(name="Assign cycle", selection={"case_ids": [str(c1), str(c2)]})
    cid = cyc["cycle_id"]
    runs = {r["title"]: r for r in sp.runs(cid)["items"]}
    # bulk assign c1 to the tester
    r = sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign",
        json={"run_ids": [runs["Assignable"]["id"]], "assignee_id": str(tester.id)},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 1
    # assigning to a non-executor (the org admin is not a project member) is refused
    bad = sp.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign",
        json={"run_ids": [runs["Claimable"]["id"]], "assignee_id": str(world.user(sp.org, "Nobody").id)},
    )
    assert bad.status_code == 422
    # the tester claims the pool run
    tc = world.login(tester)
    claimed = tc.post(f"/api/v1/runs/{runs['Claimable']['id']}/claim")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assignee"]["id"] == str(tester.id)


# -- TCMS-058 / 059: close and reopen -------------------------------------------------------------


def test_tcms_058_close_lists_drafts(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("Has draft")
    cyc = sp.create_cycle(name="Close cycle", selection={"case_ids": [str(c1)]})
    cid = cyc["cycle_id"]
    sp.admin.post(f"/api/v1/cycles/{cid}/start")
    run = sp.runs(cid)["items"][0]
    _seed_result(world, run["id"], sp.pid, sp.org.id, sp.env_id, state="draft", executed_by=sp.org.admin.id)
    # closing without discard lists the drafts (409)
    r = sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "draft_exists"
    assert run["id"] in r.json().get("draft_run_ids", [])
    # with discard_drafts the close succeeds
    ok = sp.admin.post(f"/api/v1/cycles/{cid}/close", json={"discard_drafts": True})
    assert ok.status_code == 200
    assert ok.json()["status"] == "closed"


def test_tcms_059_reopen_requires_permission_and_reason(world: World) -> None:
    sp = Space(world)
    cyc = sp.create_cycle(name="Reopen cycle", selection={})
    cid = cyc["cycle_id"]
    sp.admin.post(f"/api/v1/cycles/{cid}/start")
    sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    # missing reason → 422
    assert sp.admin.post(f"/api/v1/cycles/{cid}/reopen", json={"reason": ""}).status_code == 422
    # a qa_engineer lacks cycle.reopen → 403
    eng = world.user(sp.org, "Eng")
    world.member(sp.org, sp.pid, eng, "qa_engineer")
    ec = world.login(eng)
    assert ec.post(f"/api/v1/cycles/{cid}/reopen", json={"reason": "retest"}).status_code == 403
    # admin with a reason → success, back to active
    ok = sp.admin.post(f"/api/v1/cycles/{cid}/reopen", json={"reason": "more testing"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "active"


# -- TCMS-060: clone with only_statuses -----------------------------------------------------------


def test_tcms_060_clone_only_failed(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("Will fail")
    c2, _ = sp.case("Not run")
    cyc = sp.create_cycle(name="Source", selection={"case_ids": [str(c1), str(c2)]})
    cid = cyc["cycle_id"]
    runs = {r["title"]: r for r in sp.runs(cid)["items"]}
    # mark c1's run failed via a seeded final result, then set status failed
    _seed_result(
        world,
        runs["Will fail"]["id"],
        sp.pid,
        sp.org.id,
        sp.env_id,
        state="final",
        executed_by=sp.org.admin.id,
    )
    with world.factory() as s:
        s.execute(text("UPDATE test_runs SET status='failed' WHERE id=:r"), {"r": runs["Will fail"]["id"]})
        s.commit()
    clone = sp.admin.post(
        f"/api/v1/cycles/{cid}/clone", json={"name": "Retest round", "only_statuses": ["failed"]}
    )
    assert clone.status_code == 201, clone.text
    assert clone.json()["added"] == 1  # only the failed case carried over


# -- BR-31 / AC-PLN-02: sync from plan ------------------------------------------------------------


def test_br_31_ac_pln_02_sync_from_plan(world: World) -> None:
    sp = Space(world)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Sync plan", "type": "regression"}).json()
    c1, _ = sp.case("Case 1")
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c1)]})
    cyc = sp.create_cycle(name="Sync cycle", plan_id=plan["id"], selection={"from_plan": True})
    cid = cyc["cycle_id"]
    assert cyc["added"] == 1
    # add a case to the plan; the cycle is unchanged until sync (AC-PLN-02)
    c2, _ = sp.case("Case 2")
    sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"case_ids": [str(c2)]})
    assert sp.admin.get(f"/api/v1/cycles/{cid}").json()["summary"]["total"] == 1
    synced = sp.admin.post(f"/api/v1/cycles/{cid}/sync-from-plan")
    assert synced.status_code == 200
    assert synced.json()["added"] == 1
    assert sp.admin.get(f"/api/v1/cycles/{cid}").json()["summary"]["total"] == 2


# -- BR-04 / BR-05: update-to-latest and replace --------------------------------------------------


def _bump_version(world: World, sp: Space, case_id: UUID) -> None:
    """Save new content to create version 2 (BR-01)."""
    detail = sp.admin.get(f"/api/v1/test-cases/{case_id}").json()
    sp.admin.put(
        f"/api/v1/test-cases/{case_id}/content",
        json={
            "content": {
                "format": "steps",
                "title": detail["title"],
                "steps": [{"action": "Changed", "expected_result": "New"}],
            },
            "row_version": detail["row_version"],
        },
    )


def test_br_04_update_to_latest_only_without_attempts(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("Versioned")
    cyc = sp.create_cycle(name="Update cycle", selection={"case_ids": [str(c1)]})
    cid = cyc["cycle_id"]
    run = sp.runs(cid)["items"][0]
    assert run["version_no"] == 1
    _bump_version(world, sp, c1)
    # not-run run: update-to-latest succeeds and re-pins v2
    r = sp.admin.post(f"/api/v1/runs/{run['id']}/update-version")
    assert r.status_code == 200, r.text
    assert r.json()["version_no"] == 2
    # already latest → 409
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/update-version").json()["code"] == "already_latest"
    # with an attempt, update-to-latest is refused (BR-04)
    _seed_result(world, run["id"], sp.pid, sp.org.id, sp.env_id, state="final", executed_by=sp.org.admin.id)
    _bump_version(world, sp, c1)
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/update-version").json()["code"] == "run_has_results"


def test_br_05_replace_run_supersedes(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("To replace")
    cyc = sp.create_cycle(name="Replace cycle", selection={"case_ids": [str(c1)]})
    cid = cyc["cycle_id"]
    run = sp.runs(cid)["items"][0]
    # replace requires a finalized attempt
    assert sp.admin.post(f"/api/v1/runs/{run['id']}/replace").json()["code"] == "run_has_results"
    _seed_result(world, run["id"], sp.pid, sp.org.id, sp.env_id, state="final", executed_by=sp.org.admin.id)
    _bump_version(world, sp, c1)
    r = sp.admin.post(f"/api/v1/runs/{run['id']}/replace")
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["version_no"] == 2
    assert new["status"] == "not_run"
    # the active run list shows only the new run; the old appears with include_superseded
    active = sp.runs(cid)["items"]
    assert len(active) == 1
    assert active[0]["id"] == new["id"]
    all_runs = sp.runs(cid, include_superseded="true")["items"]
    assert len(all_runs) == 2
    assert any(x["superseded"] for x in all_runs)


# -- US-087: reorder ------------------------------------------------------------------------------


def test_us_087_reorder_runs(world: World) -> None:
    sp = Space(world)
    ids_ = [sp.case(f"Case {i}")[0] for i in range(3)]
    cyc = sp.create_cycle(name="Reorder cycle", selection={"case_ids": [str(c) for c in ids_]})
    cid = cyc["cycle_id"]
    runs = sp.runs(cid)["items"]
    reversed_ids = [r["id"] for r in reversed(runs)]
    r = sp.admin.post(f"/api/v1/cycles/{cid}/runs/reorder", json={"ordered_run_ids": reversed_ids})
    assert r.status_code == 200
    after = sp.runs(cid, sort="position")["items"]
    assert [x["id"] for x in after] == reversed_ids


# -- BR-11: closed cycle is read-only -------------------------------------------------------------


def test_br_11_closed_cycle_blocks_changes(world: World) -> None:
    sp = Space(world)
    c1, _ = sp.case("Case A")
    cyc = sp.create_cycle(name="Closed cycle", selection={"case_ids": [str(c1)]})
    cid = cyc["cycle_id"]
    sp.admin.post(f"/api/v1/cycles/{cid}/start")
    sp.admin.post(f"/api/v1/cycles/{cid}/close", json={})
    c2, _ = sp.case("Case B")
    # add cases / assign refused in a closed cycle
    assert (
        sp.admin.post(f"/api/v1/cycles/{cid}/runs", json={"case_ids": [str(c2)]}).json()["code"]
        == "cycle_closed"
    )
