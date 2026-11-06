"""M4 E09 — result attempts and My Work (US-090…US-100). API tests for FR-EXE-005…010/014, BR-06…10,
BR-30, BR-32 and docs/02 §7.3 (with reviews K2, K17h/i).

Acceptance: AC-EXE-01…08, TCMS-070, 072…085, 089. The exhaustive roll-up matrix (TCMS-071) is in
`tests/unit/test_execution_rules.py`; SQL immutability (TCMS-076) in `tests/integration/test_immutability.py`;
concurrency (TCMS-090) and AC-EXE-09 in `tests/integration/test_attempt_concurrency.py`.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from tests.api.test_execution import Space, _bump_version, _rows
from tests.world import ApiClient, World

pytestmark = pytest.mark.integration

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


class Exec(Space):
    """A Space with two engineers and a lead, and a helper for one-run cycles."""

    def __init__(self, world: World, key: str = "SPARK") -> None:
        super().__init__(world, key)
        self.sana_user = self.member("Sana", "qa_engineer")
        self.omar_user = self.member("Omar", "qa_engineer")
        self.bilal_user = self.member("Bilal", "qa_lead")
        self.sana = world.login(self.sana_user)
        self.omar = world.login(self.omar_user)
        self.bilal = world.login(self.bilal_user)

    def one_run(self, steps: int = 2, *, assignee: Any = None, start: bool = True) -> tuple[str, str]:
        """A cycle with one run of a fresh case → (cycle id, run id)."""
        case_id, _ = self.world.case(self.org, self.pid, self.folder, None, steps=steps)
        body: dict[str, Any] = {"selection": {"case_ids": [str(case_id)]}}
        if assignee is not None:
            body["default_assignee_id"] = str(assignee.id)
        cycle = self.create_cycle(name=f"Cycle {case_id.hex[-10:]}", **body)["cycle"]
        if start:
            assert self.admin.post(f"/api/v1/cycles/{cycle['id']}/start").status_code == 200
        return cycle["id"], self.runs(cycle["id"])[0]["id"]

    def run(
        self, run_id: str, include: str = "draft,history", client: ApiClient | None = None
    ) -> dict[str, Any]:
        r = (client or self.admin).get(f"/api/v1/runs/{run_id}", params={"include": include})
        assert r.status_code == 200, r.text
        return dict(r.json())


def _start(c: ApiClient, run_id: str, **body: Any) -> Any:
    return c.post(f"/api/v1/runs/{run_id}/results", json=body or None)


def _step(c: ApiClient, res: dict[str, Any], i: int, **fields: Any) -> Any:
    return c.patch(f"/api/v1/results/{res['id']}/steps/{res['steps'][i]['step_id']}", json=fields)


def _finish(c: ApiClient, res_id: str, **body: Any) -> Any:
    return c.post(f"/api/v1/results/{res_id}/finalize", json=body)


def _record(c: ApiClient, res: dict[str, Any], *statuses: str) -> None:
    for i, st in enumerate(statuses):
        fields: dict[str, Any] = {"status": st}
        if st == "failed":
            fields["actual_result"] = f"Step {i + 1} went wrong"
        r = _step(c, res, i, **fields)
        assert r.status_code == 200, r.text


def _done(c: ApiClient, run_id: str, *statuses: str, **body: Any) -> dict[str, Any]:
    """Start, record the step statuses and finish → the finalize response."""
    res = _start(c, run_id).json()
    _record(c, res, *statuses)
    r = _finish(c, res["id"], **body)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _actions(world: World, entity_id: str) -> list[str]:
    rows = _rows(
        world, "SELECT action FROM audit_events WHERE entity_id = :e ORDER BY occurred_at", e=entity_id
    )
    return [r[0] for r in rows]


def _upload(c: ApiClient, step_result_id: str) -> Any:
    return c.post(
        "/api/v1/attachments",
        data={"entity_type": "test_step_result", "entity_id": step_result_id},
        files={"file": ("shot.png", io.BytesIO(PNG), "image/png")},
    )


# -- start, record, finish (US-090/091) -----------------------------------------------------------


@pytest.mark.br("BR-30")
def test_tcms_070_tcms_084_execute_a_run_all_passed(world: World) -> None:
    """TCMS-070: start → record → finish; the run is passed and the cycle counts it. TCMS-084 / BR-30: the
    first execution activates a planned cycle."""
    ex = Exec(world)
    cid, run_id = ex.one_run(steps=2, assignee=ex.sana_user, start=False)
    assert ex.cycle(cid)["status"] == "planned"

    r = _start(ex.sana, run_id)
    assert r.status_code == 201, r.text
    res = r.json()
    assert (res["state"], res["attempt_no"], res["status"]) == ("draft", 1, None)
    assert [s["status"] for s in res["steps"]] == ["not_run", "not_run"]
    assert res["executed_by"]["id"] == str(ex.sana_user.id)
    assert res["environment"]["id"] == ex.env_id
    assert ex.cycle(cid)["status"] == "active"
    assert ex.run(run_id)["status"] == "in_progress"
    assert ex.run(run_id)["draft"]["id"] == res["id"]

    again = _start(ex.sana, run_id)
    assert again.status_code == 200, "the caller's own draft is returned"
    assert again.json()["id"] == res["id"]

    _record(ex.sana, res, "passed", "passed")
    done = _finish(ex.sana, res["id"])
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["result"]["state"], body["result"]["status"]) == ("final", "passed")
    assert body["result"]["duration_seconds"] is not None
    assert body["run"]["status"] == "passed"
    assert [a["status"] for a in body["run"]["history"]] == ["passed"]
    summary = ex.cycle(cid)["summary"]
    assert (summary["passed"], summary["executed"], summary["execution_progress"]["value"]) == (1, 1, 1.0)
    assert _actions(world, res["id"]) == ["result.started", "result.finalized"]
    started = _rows(
        world, "SELECT context FROM audit_events WHERE action = 'cycle.started' AND entity_id = :c", c=cid
    )
    assert started[0][0]["automatic"] is True


def test_ac_exe_01_tcms_072_failed_step_requires_an_actual_result(world: World) -> None:
    """AC-EXE-01 / TCMS-072 / BR-10: [passed, failed, not_run] finishes as failed, but only with an actual
    result on the failed step."""
    ex = Exec(world)
    _, run_id = ex.one_run(steps=3)
    res = _start(ex.admin, run_id).json()
    _step(ex.admin, res, 0, status="passed")
    _step(ex.admin, res, 1, status="failed")
    r = _finish(ex.admin, res["id"])
    assert r.status_code == 422
    assert r.json()["code"] == "actual_result_required"
    assert r.json()["errors"][0]["field"] == "steps[1].actual_result"
    _step(ex.admin, res, 1, actual_result="Dashboard took 9 s")
    ok = _finish(ex.admin, res["id"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["result"]["status"] == "failed"


def test_ac_exe_03_tcms_073_incomplete_attempt_needs_an_outcome(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=2)
    res = _start(ex.admin, run_id).json()
    _step(ex.admin, res, 0, status="passed")
    r = _finish(ex.admin, res["id"])
    assert r.status_code == 422
    assert r.json()["code"] == "incomplete_attempt"
    assert r.json()["detail"].startswith("Step 2 has no result")
    assert ex.run(run_id)["status"] == "in_progress"


@pytest.mark.br("BR-10")
def test_tcms_074_block_a_run_with_a_reason(world: World) -> None:
    """TCMS-074 / FR-EXE-008: an explicit Blocked needs a reason, which the history shows."""
    ex = Exec(world)
    _, run_id = ex.one_run(steps=3)
    res = _start(ex.admin, run_id).json()
    _step(ex.admin, res, 0, status="passed")
    no_reason = _finish(ex.admin, res["id"], outcome="blocked")
    assert no_reason.status_code == 422
    assert no_reason.json()["code"] == "reason_required"
    ok = _finish(ex.admin, res["id"], outcome="blocked", reason="QA environment is down")
    assert ok.status_code == 200, ok.text
    assert ok.json()["run"]["status"] == "blocked"
    assert ok.json()["run"]["history"][0]["reason"] == "QA environment is down"


@pytest.mark.br("BR-10")
def test_br_10_k2_blocked_from_steps_also_needs_a_reason(world: World) -> None:
    """Review K2: a Blocked derived from a blocked step needs a reason too (the database requires it)."""
    ex = Exec(world)
    _, run_id = ex.one_run(steps=2)
    res = _start(ex.admin, run_id).json()
    _record(ex.admin, res, "passed", "blocked")
    r = _finish(ex.admin, res["id"])
    assert (r.status_code, r.json()["code"]) == (422, "reason_required")
    assert (
        _finish(ex.admin, res["id"], reason="Payment sandbox unavailable").json()["result"]["status"]
        == "blocked"
    )


def test_ac_exe_02_tcms_075_passed_with_skipped_steps_is_flagged(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=3)
    body = _done(ex.admin, run_id, "passed", "skipped", "passed")
    assert (body["result"]["status"], body["result"]["skipped_steps"]) == ("passed", 1)
    assert body["run"]["history"][0]["skipped_steps"] == 1


def test_k17h_k17i_explicit_outcome_cannot_contradict_the_steps(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=2)
    res = _start(ex.admin, run_id).json()
    _record(ex.admin, res, "passed", "failed")
    for outcome in ("blocked", "passed", "failed"):
        r = _finish(ex.admin, res["id"], outcome=outcome, reason="x")
        assert (r.status_code, r.json()["code"]) == (422, "outcome_conflicts_with_steps"), outcome
    assert ex.run(run_id)["status"] == "in_progress"


def test_pass_all_remaining_marks_only_not_run_steps(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=3)
    res = _start(ex.admin, run_id).json()
    _step(ex.admin, res, 0, status="skipped")
    r = ex.admin.post(
        f"/api/v1/results/{res['id']}/steps/bulk", json={"status": "passed", "only_not_run": True}
    )
    assert r.json() == {"count": 2}
    steps = ex.admin.get(f"/api/v1/results/{res['id']}").json()["steps"]
    assert [s["status"] for s in steps] == ["skipped", "passed", "passed"]


# -- immutability, one draft, closed cycle (US-097) ----------------------------------------------


@pytest.mark.br("BR-06")
def test_br_06_ac_exe_04_tcms_076_final_attempt_rejects_every_api_change(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=1)
    res = _start(ex.admin, run_id).json()
    _record(ex.admin, res, "passed")
    _finish(ex.admin, res["id"])
    for r in (
        _step(ex.admin, res, 0, status="failed", actual_result="x"),
        ex.admin.patch(f"/api/v1/results/{res['id']}", json={"comment": "late"}),
        ex.admin.post(
            f"/api/v1/results/{res['id']}/steps/bulk", json={"status": "passed", "only_not_run": True}
        ),
        _finish(ex.admin, res["id"]),
        ex.admin.delete(f"/api/v1/results/{res['id']}"),
        _upload(ex.admin, res["steps"][0]["id"]),
    ):
        assert (r.status_code, r.json()["code"]) == (409, "immutable_record"), r.text


@pytest.mark.br("BR-07")
def test_br_07_ac_exe_05_tcms_077_one_draft_and_take_over(world: World) -> None:
    """AC-EXE-05: another tester gets 409 draft_exists; only a cycle manager may take the draft over."""
    ex = Exec(world)
    _, run_id = ex.one_run(steps=2)
    res = _start(ex.sana, run_id).json()
    clash = _start(ex.omar, run_id)
    assert (clash.status_code, clash.json()["code"]) == (409, "draft_exists")
    assert clash.json()["executed_by"] == "Sana"
    assert clash.json()["can_take_over"] is False
    assert _step(ex.omar, res, 0, status="passed").status_code == 403
    assert _start(ex.omar, run_id, take_over=True).status_code == 409, "take-over needs cycle.manage"

    taken = _start(ex.bilal, run_id, take_over=True)
    assert taken.status_code == 200, taken.text
    assert taken.json()["id"] == res["id"]
    assert taken.json()["executed_by"]["id"] == str(ex.bilal_user.id)
    assert "result.draft_taken_over" in _actions(world, res["id"])
    assert _step(ex.sana, res, 0, status="passed").status_code == 403, "Sana no longer runs it"


def test_ac_exe_06_tcms_078_closed_cycle_rejects_execution(world: World) -> None:
    ex = Exec(world)
    cid, run_id = ex.one_run(steps=1)
    assert ex.admin.post(f"/api/v1/cycles/{cid}/close", json={}).status_code == 200
    r = _start(ex.admin, run_id)
    assert (r.status_code, r.json()["code"]) == (409, "cycle_closed")


def test_ac_exe_07_tcms_079_retest_keeps_history_and_counts_the_latest(world: World) -> None:
    ex = Exec(world)
    cid, run_id = ex.one_run(steps=1)
    first = _done(ex.admin, run_id, "failed")
    assert first["run"]["status"] == "failed"
    second = _done(ex.admin, run_id, "passed")
    assert second["result"]["attempt_no"] == 2
    history = second["run"]["history"]
    assert [(a["attempt_no"], a["status"]) for a in history] == [(1, "failed"), (2, "passed")]
    summary = ex.cycle(cid)["summary"]
    assert (summary["total"], summary["passed"], summary["failed"]) == (1, 1, 0)


def test_tcms_080_correct_a_result_with_a_reason(world: World) -> None:
    """FR-EXE-010: a new attempt references the corrected one; finishing it needs a reason."""
    ex = Exec(world)
    cid, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    first = _done(ex.sana, run_id, "passed")["result"]
    assert _start(ex.omar, run_id, corrects_result_id=first["id"]).status_code == 403, "not the tester"
    res = _start(ex.sana, run_id, corrects_result_id=first["id"])
    assert res.status_code == 201, res.text
    corr = res.json()
    assert corr["corrects_result_id"] == first["id"]
    _record(ex.sana, corr, "failed")
    no_reason = _finish(ex.sana, corr["id"])
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "reason_required")
    done = _finish(ex.sana, corr["id"], reason="Step 1 was wrongly passed")
    assert done.json()["run"]["status"] == "failed"
    history = done.json()["run"]["history"]
    assert history[0]["corrected_by_result_id"] == corr["id"]
    assert _actions(world, corr["id"])[-1] == "result.corrected"
    assert ex.cycle(cid)["summary"]["failed"] == 1, "metrics use the correction"

    stale = _start(ex.sana, run_id, corrects_result_id=first["id"])
    assert (stale.status_code, stale.json()["errors"][0]["code"]) == (422, "not_latest")


@pytest.mark.br("BR-04")
def test_ac_exe_08_tcms_081_082_pinned_version_after_edit(world: World) -> None:
    """The run keeps showing the pinned v1 after the case moves to v2; with a result it cannot be updated
    (use Replace run); a run without attempts can."""
    ex = Exec(world)
    case_id, _ = ex.world.case(ex.org, ex.pid, ex.folder, "Pinned", steps=2)
    other, _ = ex.world.case(ex.org, ex.pid, ex.folder, "Untouched", steps=1)
    cid = ex.create_cycle(name="Pins", selection={"case_ids": [str(case_id), str(other)]})["cycle"]["id"]
    ex.admin.post(f"/api/v1/cycles/{cid}/start")
    runs = {r["test_case"]["id"]: r["id"] for r in ex.runs(cid)}
    _done(ex.admin, runs[str(case_id)], "passed", "passed")
    _bump_version(ex, case_id)
    run = ex.run(runs[str(case_id)], include="version,history")
    assert run["pinned_version_no"] == 1
    assert run["version"]["version_no"] == 1
    assert [s["action"] for s in run["version"]["steps"]] == ["Do 1", "Do 2"]
    assert run["newer_version"] == {
        "version_no": 2,
        "eligible": True,
        "can_update": False,
        "reason": "run_has_results",
    }
    r = ex.admin.post(f"/api/v1/runs/{runs[str(case_id)]}/update-version")
    assert (r.status_code, r.json()["code"]) == (409, "run_has_results")
    _bump_version(ex, other)
    assert ex.admin.post(f"/api/v1/runs/{runs[str(other)]}/update-version").json()["pinned_version_no"] == 2


@pytest.mark.br("BR-32")
def test_br_32_tcms_085_only_assignee_executes(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    _, pool_run = ex.one_run(steps=1)
    # Without the setting anyone may run it, and executed_by records the actual tester.
    assert _start(ex.omar, run_id).json()["executed_by"]["id"] == str(ex.omar_user.id)
    draft = ex.run(run_id)["draft"]
    assert ex.admin.delete(f"/api/v1/results/{draft['id']}").status_code == 204

    rv = ex.admin.get(ex.purl()).json()["row_version"]
    on = ex.admin.patch(ex.purl(), json={"settings": {"only_assignee_executes": True}, "row_version": rv})
    assert on.status_code == 200, on.text
    r = _start(ex.omar, run_id)
    assert (r.status_code, r.json()["code"]) == (403, "not_assignee")
    assert _start(ex.omar, pool_run).status_code == 201, "unassigned runs stay open to all"
    assert _start(ex.bilal, run_id).status_code == 201, "cycle.manage may execute"


def test_tcms_089_text_format_case(world: World) -> None:
    """docs/02 §7.3: no step rows; the tester chooses the result; Failed needs a comment."""
    ex = Exec(world)
    created = ex.admin.post(
        ex.purl("/test-cases"),
        json={
            "folder_id": str(ex.folder),
            "content": {"format": "text", "title": "Explore checkout", "text_body": "Try odd carts"},
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case"]["id"]
    cid = ex.create_cycle(name="Text cycle", selection={"case_ids": [case_id]})["cycle"]["id"]
    run_id = ex.runs(cid)[0]["id"]
    res = _start(ex.admin, run_id).json()
    assert res["steps"] == []
    r = _finish(ex.admin, res["id"])
    assert (r.status_code, r.json()["code"]) == (422, "outcome_required")
    r = _finish(ex.admin, res["id"], outcome="failed")
    assert (r.status_code, r.json()["code"]) == (422, "field_required")
    assert (
        ex.admin.patch(
            f"/api/v1/results/{res['id']}", json={"comment": "Total wrong for 3 items"}
        ).status_code
        == 200
    )
    ok = _finish(ex.admin, res["id"], outcome="failed")
    assert ok.json()["result"]["status"] == "failed"
    assert ok.json()["result"]["comment"] == "Total wrong for 3 items"


# -- evidence and discard (US-093) ----------------------------------------------------------------


def test_tcms_087_step_evidence_and_discard(world: World) -> None:
    """Evidence on a step of a draft: the tester (or a cycle manager) may attach; others may not. Discarding
    removes the draft, its steps and its evidence, and is audited with what was recorded."""
    ex = Exec(world)
    _, run_id = ex.one_run(steps=2, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    _record(ex.sana, res, "failed")
    step_result = res["steps"][0]["id"]
    up = _upload(ex.sana, step_result)
    assert up.status_code == 201, up.text
    assert _upload(ex.omar, step_result).status_code == 403
    assert _upload(ex.bilal, step_result).status_code == 201
    steps = ex.sana.get(f"/api/v1/results/{res['id']}").json()["steps"]
    assert len(steps[0]["attachments"]) == 2
    assert ex.run(run_id)["draft"]["steps"][0]["attachments"][0]["file_name"] == "shot.png"

    assert ex.omar.delete(f"/api/v1/results/{res['id']}").status_code == 403
    assert ex.sana.delete(f"/api/v1/results/{res['id']}").status_code == 204
    assert ex.run(run_id)["status"] == "not_run"
    assert ex.sana.get(f"/api/v1/results/{res['id']}").status_code == 404
    links = _rows(world, "SELECT count(*) FROM attachment_links WHERE entity_id = :e", e=step_result)
    assert links[0][0] == 0
    summary = _rows(
        world,
        "SELECT summary FROM audit_events WHERE action = 'result.discarded' AND entity_id = :e",
        e=res["id"],
    )
    assert "1 of 2 steps recorded" in summary[0][0]


def test_discard_falls_back_to_the_latest_final_status(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=1)
    _done(ex.admin, run_id, "failed")
    retest = _start(ex.admin, run_id).json()
    assert ex.run(run_id)["status"] == "in_progress"
    ex.admin.delete(f"/api/v1/results/{retest['id']}")
    assert ex.run(run_id)["status"] == "failed"


@pytest.mark.br("BR-05")
def test_tcms_083_replace_after_a_real_result_excludes_the_old_run(world: World) -> None:
    ex = Exec(world)
    case_id, _ = ex.world.case(ex.org, ex.pid, ex.folder, "Replace me", steps=1)
    cid = ex.create_cycle(name="Replace", selection={"case_ids": [str(case_id)]})["cycle"]["id"]
    old = ex.runs(cid)[0]["id"]
    _done(ex.admin, old, "failed")
    _bump_version(ex, case_id)
    new = ex.admin.post(f"/api/v1/runs/{old}/replace")
    assert new.status_code == 201, new.text
    assert (new.json()["pinned_version_no"], new.json()["status"]) == (2, "not_run")
    summary = ex.cycle(cid)["summary"]
    assert (summary["total"], summary["failed"], summary["not_run"]) == (1, 0, 1)
    assert _start(ex.admin, old).json()["code"] == "run_superseded"


# -- queue (US-094) and My Work (US-099) ----------------------------------------------------------


def test_runner_queue_is_my_open_runs_in_position_order(world: World) -> None:
    ex = Exec(world)
    cases = [ex.world.case(ex.org, ex.pid, ex.folder, f"Queue case {i}", steps=1)[0] for i in range(4)]
    cid = ex.create_cycle(name="Queue", selection={"case_ids": [str(c) for c in cases]})["cycle"]["id"]
    runs = [r["id"] for r in ex.runs(cid)]
    ex.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign", json={"run_ids": runs[:3], "assignee_id": str(ex.sana_user.id)}
    )
    q = ex.run(runs[1], include="queue", client=ex.sana)["queue"]
    assert q == {
        "filter": "mine_open",
        "position": 2,
        "total": 3,
        "previous_run_id": runs[0],
        "next_run_id": runs[2],
    }

    _done(ex.sana, runs[0], "passed")
    after = ex.run(runs[0], include="queue", client=ex.sana)["queue"]
    assert (after["position"], after["total"], after["next_run_id"]) == (None, 2, runs[1])
    everything = ex.sana.get(f"/api/v1/runs/{runs[0]}", params={"include": "queue", "queue_filter": "all"})
    assert everything.json()["queue"]["total"] == 4
    # Nobody assigned to Omar: his queue falls back to every open run.
    omar = ex.run(runs[3], include="queue", client=ex.omar)["queue"]
    assert (omar["filter"], omar["total"], omar["position"]) == ("open", 3, 3)
    bad = ex.sana.get(f"/api/v1/runs/{runs[0]}", params={"include": "queue", "queue_filter": "nope"})
    assert bad.status_code == 400

    # docs/06 §6: the runs list takes a comma list of statuses.
    assert len(ex.runs(cid, status="not_run,in_progress")) == 3
    mine = ex.sana.get(
        f"/api/v1/cycles/{cid}/runs", params={"status": "not_run,in_progress", "assignee_id": "me"}
    ).json()["items"]
    assert [r["id"] for r in mine] == runs[1:3]


def test_us_099_my_work_lists_my_cycles_reviews_and_week(world: World) -> None:
    """FR-EXE-014 / docs/02 §7.5: my runs in planned and active cycles across my projects, grouped by
    cycle with counts and the next run; cases awaiting my review; what I finished this week."""
    ex = Exec(world)
    other = world.project(ex.org, "HELIOS")
    world.member(ex.org, other, ex.sana_user, "qa_engineer")
    hf = world.folder(ex.org, other, "H")
    h_case, _ = world.case(ex.org, other, hf, "Helios case")
    h_env = ex.admin.get(f"/api/v1/projects/{other}/environments").json()[0]["id"]
    ex.admin.post(
        f"/api/v1/projects/{other}/cycles",
        json={
            "name": "Helios smoke",
            "environment_id": h_env,
            "selection": {"case_ids": [str(h_case)]},
            "default_assignee_id": str(ex.sana_user.id),
            "due_date": "2026-11-20",
        },
    )
    cid, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    second_case, _ = ex.world.case(ex.org, ex.pid, ex.folder, "Second", steps=1)
    ex.admin.post(f"/api/v1/cycles/{cid}/runs", json={"case_ids": [str(second_case)]})
    second = next(r["id"] for r in ex.runs(cid) if r["id"] != run_id)
    ex.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign", json={"run_ids": [second], "assignee_id": str(ex.sana_user.id)}
    )
    closed_cid, _ = ex.one_run(steps=1, assignee=ex.sana_user)
    ex.admin.post(f"/api/v1/cycles/{closed_cid}/close", json={})
    _done(ex.sana, run_id, "failed")

    work = ex.sana.get("/api/v1/me/work")
    assert work.status_code == 200, work.text
    body = work.json()
    keys = [c["key"] for c in body["cycles"]]
    assert len(keys) == 2, "closed cycles are not listed"
    spark = next(c for c in body["cycles"] if c["project"]["key"] == "SPARK")
    helios = next(c for c in body["cycles"] if c["project"]["key"] == "HELIOS")
    assert (spark["summary"]["total"], spark["summary"]["failed"], spark["summary"]["not_run"]) == (2, 1, 1)
    assert spark["next_run_id"] == second
    assert (helios["status"], helios["due_date"], helios["summary"]["not_run"]) == (
        "planned",
        "2026-11-20",
        1,
    )
    assert body["week"]["failed"] == 1
    assert body["today"]["failed"] == 1, "R-142: executed today"
    assert [(a["run_id"], a["status"]) for a in body["attention"]] == [(run_id, "failed")], "R-142"
    assert body["bugs_linked_week"] == 0
    assert body["reviews"] == [], "engineers cannot approve"


def test_us_099_my_work_shows_cases_awaiting_my_review(world: World) -> None:
    ex = Exec(world)
    rv = ex.admin.get(ex.purl()).json()["row_version"]
    ex.admin.patch(ex.purl(), json={"settings": {"approval_required": True}, "row_version": rv})
    case_id, key = ex.world.case(ex.org, ex.pid, ex.folder, "Needs review", steps=1)
    assert ex.admin.post(f"/api/v1/test-cases/{case_id}/submit", json={}).status_code == 200
    reviews = ex.bilal.get("/api/v1/me/work").json()["reviews"]
    assert [(r["key"], r["project"]["key"]) for r in reviews] == [(key, "SPARK")]
    assert ex.sana.get("/api/v1/me/work").json()["reviews"] == []


def test_run_status_consistency_check_reports_mismatches(world: World) -> None:
    """docs/04 §5.6: the nightly check compares run.status with BR-08 and only reports."""
    from tcms.core.context import AccessContext, Principal, RequestMeta
    from tcms.core.uow import unit_of_work
    from tcms.execution import service

    ex = Exec(world)
    _, run_id = ex.one_run(steps=1)
    _done(ex.admin, run_id, "passed")
    ctx = AccessContext.for_principal(Principal.system(ex.org.id), RequestMeta("t"), project_id=ex.pid)
    with unit_of_work(world.factory) as uow:
        assert service.verify_run_statuses(uow, ctx) == []
    with world.factory() as s:
        from sqlalchemy import text

        s.execute(text("UPDATE test_runs SET status = 'blocked' WHERE id = :r"), {"r": run_id})
        s.commit()
    with unit_of_work(world.factory) as uow:
        assert [str(r) for r in service.verify_run_statuses(uow, ctx)] == [run_id]
        assert (ex.org.id, ex.pid) in service.projects_with_runs(uow)
