"""M5 — bug links (docs/02 §8, ADR-023): AC-BUG-01…06, BR-20, BR-21, TCMS-100…107 (API level).

Bugs live in the team's tracker; Assay stores references on attempts and cases.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.api.test_attempts import Exec, _done, _finish, _record, _start, _step
from tests.api.test_execution import _bump_version, _rows
from tests.world import ApiClient, World

pytestmark = pytest.mark.integration

TEMPLATE = "https://acme.atlassian.net/browse/{ref}"


def _settings(ex: Exec, **settings: Any) -> None:
    rv = ex.admin.get(ex.purl()).json()["row_version"]
    r = ex.admin.patch(ex.purl(), json={"settings": settings, "row_version": rv})
    assert r.status_code == 200, r.text


def _link(c: ApiClient, result_id: str, reference: str, **body: Any) -> Any:
    return c.post(f"/api/v1/results/{result_id}/bug-links", json={"reference": reference, **body})


def _audit(world: World, action: str, project_id: Any) -> list[Any]:
    return _rows(
        world,
        "SELECT entity_key, context FROM audit_events WHERE action = :a AND project_id = :p ORDER BY occurred_at",
        a=action,
        p=str(project_id),
    )


@pytest.mark.br("BR-20")
def test_ac_bug_01_02_tcms_100_link_from_a_failed_step(world: World) -> None:
    """AC-BUG-01: the link stores attempt, run, step and case; it shows on the run, the cycle and the case.
    AC-BUG-02: the project template builds the URL."""
    ex = Exec(world)
    _settings(ex, bug_tracker_name="Jira", bug_url_template=TEMPLATE)
    cid, run_id = ex.one_run(steps=3, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    _record(ex.sana, res, "passed", "passed", "failed")
    step3 = res["steps"][2]["step_id"]
    r = _link(ex.sana, res["id"], " SPK-431 ", step_id=step3, title="Dashboard slow")
    assert r.status_code == 201, r.text
    link = r.json()
    assert link["reference"] == "SPK-431"
    assert link["url"] == "https://acme.atlassian.net/browse/SPK-431"
    assert (link["run_id"], link["result_id"], link["step_id"], link["step_position"]) == (
        run_id,
        res["id"],
        step3,
        3,
    )
    assert link["attempt_status"] == "draft"
    assert link["can_edit"] is True
    case_id = link["test_case"]["id"]
    assert [x["id"] for x in ex.admin.get(f"/api/v1/runs/{run_id}/bug-links").json()] == [link["id"]]
    assert [x["reference"] for x in ex.admin.get(f"/api/v1/cycles/{cid}/bug-links").json()] == ["SPK-431"]
    assert [x["reference"] for x in ex.admin.get(f"/api/v1/test-cases/{case_id}/bug-links").json()] == [
        "SPK-431"
    ]
    assert ex.admin.get(f"/api/v1/cycles/{cid}/bug-links", params={"recent": True}).json()[0][
        "reference"
    ] == ("SPK-431")
    given = _link(ex.sana, res["id"], "SPK-500", url="https://other.test/500").json()
    assert given["url"] == "https://other.test/500", "a given URL is kept"
    keys = [k for k, _ in _audit(world, "bug.linked", ex.pid)]
    assert keys[0].startswith("SPK-431 on ")
    assert keys[0].endswith(" step 3")


def test_ac_bug_05_06_validation_and_duplicates(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=2, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    for body, field in (
        ({"reference": "SPK 1"}, "reference"),
        ({"reference": "SPK-1", "url": "javascript:alert(1)"}, "url"),
        ({"reference": "SPK-1", "url": "ftp://x.test/1"}, "url"),
        ({"reference": "SPK-1", "step_id": "00000000-0000-0000-0000-000000000001"}, "step_id"),
    ):
        r = ex.sana.post(f"/api/v1/results/{res['id']}/bug-links", json=body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["errors"][0]["field"] == field
    assert _link(ex.sana, res["id"], "SPK-1").status_code == 201
    dup = _link(ex.sana, res["id"], "spk-1")
    assert (dup.status_code, dup.json()["code"]) == (409, "already_linked"), (
        "references compare case-insensitively"
    )
    assert _link(ex.sana, res["id"], "SPK-1", step_id=res["steps"][0]["step_id"]).status_code == 201


@pytest.mark.br("BR-20")
def test_br_20_final_attempts_accept_links_and_stay_immutable(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    done = _done(ex.sana, run_id, "failed")
    rid = done["result"]["id"]
    r = _link(ex.sana, rid, "SPK-77")
    assert r.status_code == 201, r.text
    assert r.json()["attempt_status"] == "failed"
    after = ex.admin.get(f"/api/v1/results/{rid}").json()
    assert (after["state"], after["status"]) == ("final", "failed")


def test_tcms_102_link_a_case_directly(world: World) -> None:
    ex = Exec(world)
    case_id, _ = ex.case("Found outside a cycle")
    r = ex.sana.post(f"/api/v1/test-cases/{case_id}/bug-links", json={"reference": "#1287"})
    assert r.status_code == 201, r.text
    assert (r.json()["run_id"], r.json()["cycle"]) == (None, None)
    assert (
        ex.sana.post(f"/api/v1/test-cases/{case_id}/bug-links", json={"reference": "#1287"}).status_code
        == 409
    )
    listed = ex.admin.get(f"/api/v1/test-cases/{case_id}/bug-links").json()
    assert [x["reference"] for x in listed] == ["#1287"]


def test_tcms_107_edit_and_remove_permissions(world: World) -> None:
    """The person who linked it, or `defect.edit`, may change or remove a link; Viewers may not link."""
    ex = Exec(world)
    viewer = world.login(ex.member("Faisal", "viewer"))
    pm = world.login(ex.member("Hira", "pm_ba"))
    _, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    assert _link(viewer, res["id"], "SPK-9").status_code == 403
    link = _link(ex.sana, res["id"], "SPK-9").json()
    assert viewer.get(f"/api/v1/runs/{run_id}/bug-links").json()[0]["can_edit"] is False
    assert pm.patch(f"/api/v1/bug-links/{link['id']}", json={"title": "x"}).status_code == 403
    assert pm.delete(f"/api/v1/bug-links/{link['id']}").status_code == 403
    r = ex.sana.patch(
        f"/api/v1/bug-links/{link['id']}", json={"title": "Login slow", "url": "https://t.test/9"}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["title"], r.json()["url"]) == ("Login slow", "https://t.test/9")
    bad = ex.sana.patch(f"/api/v1/bug-links/{link['id']}", json={"url": "javascript:x"})
    assert bad.status_code == 422
    cleared = ex.sana.patch(f"/api/v1/bug-links/{link['id']}", json={"url": None}).json()
    assert cleared["url"] is None
    assert ex.omar.delete(f"/api/v1/bug-links/{link['id']}").status_code == 204, (
        "defect.edit removes any link"
    )
    assert ex.admin.get(f"/api/v1/runs/{run_id}/bug-links").json() == []
    assert [k for k, _ in _audit(world, "bug.updated", ex.pid)]
    assert len(_audit(world, "bug.unlinked", ex.pid)) == 1


def _replace(ex: Exec, run_id: str) -> str:
    case_id = ex.admin.get(f"/api/v1/runs/{run_id}").json()["test_case"]["id"]
    _bump_version(ex, case_id)
    r = ex.admin.post(f"/api/v1/runs/{run_id}/replace")
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


@pytest.mark.br("BR-21")
def test_br_21_ac_bug_03_tcms_103_ready_for_retest_flags_only_eligible_runs(world: World) -> None:
    ex = Exec(world)
    cid, run_a = ex.one_run(steps=1, assignee=ex.sana_user)
    _, run_b = ex.one_run(steps=1, assignee=ex.sana_user)
    _, run_old = ex.one_run(steps=1, assignee=ex.sana_user)
    closed_cid, run_closed = ex.one_run(steps=1, assignee=ex.sana_user)
    for run_id in (run_a, run_b, run_old, run_closed):
        rid = _done(ex.sana, run_id, "failed")["result"]["id"]
        assert _link(ex.sana, rid, "SPK-431").status_code == 201
    _replace(ex, run_old)
    assert ex.admin.post(f"/api/v1/cycles/{closed_cid}/close", json={}).status_code == 200
    url = ex.purl("/bugs/retest")
    assert ex.sana.post(url, json={"reference": "SPK-431"}).status_code == 403, "needs cycle.manage"
    assert ex.bilal.post(url, json={"reference": "SPK-999"}).status_code == 404
    preview = ex.bilal.post(url, json={"reference": "spk-431", "dry_run": True}).json()
    assert (preview["linked_runs"], preview["flagged"], preview["dry_run"]) == (4, 2, True)
    assert not ex.run(run_a)["needs_retest"], "a dry run changes nothing"
    done = ex.bilal.post(url, json={"reference": "SPK-431"}).json()
    assert done["flagged"] == 2
    flags = {r: ex.run(r)["needs_retest"] for r in (run_a, run_b, run_old, run_closed)}
    assert flags == {run_a: True, run_b: True, run_old: False, run_closed: False}
    assert ex.cycle(cid)["summary"]["needs_retest"] == 1
    ((key, context),) = _audit(world, "bug.retest_requested", ex.pid)
    assert key == "SPK-431"
    assert sorted(context["run_ids"]) == sorted([run_a, run_b])
    # TCMS-104: a new final attempt clears the flag; the bug stays on the run history.
    _done(ex.sana, run_a, "passed")
    assert not ex.run(run_a)["needs_retest"]
    assert [x["reference"] for x in ex.admin.get(f"/api/v1/runs/{run_a}/bug-links").json()] == ["SPK-431"]


def test_tcms_105_bugs_list_groups_by_reference(world: World) -> None:
    ex = Exec(world)
    cid, run_a = ex.one_run(steps=1, assignee=ex.sana_user)
    _, run_b = ex.one_run(steps=1, assignee=ex.sana_user)
    ra = _done(ex.sana, run_a, "failed")["result"]["id"]
    rb = _done(ex.sana, run_b, "passed")["result"]["id"]
    _link(ex.sana, ra, "SPK-431", title="Dashboard slow")
    _link(ex.sana, rb, "spk-431")
    _link(ex.sana, rb, "SPK-2")
    case_id = ex.run(run_a)["test_case"]["id"]
    ex.sana.post(f"/api/v1/test-cases/{case_id}/bug-links", json={"reference": "SPK-431"})
    page = ex.admin.get(ex.purl("/bugs")).json()
    assert page["total"] == 2
    top = {b["reference"].upper(): b for b in page["items"]}["SPK-431"]
    assert (top["cases"], top["runs"], top["failing_runs"], top["title"]) == (2, 2, 1, "Dashboard slow")
    assert len(top["cycle_keys"]) == 2
    assert [
        b["reference"] for b in ex.admin.get(ex.purl("/bugs"), params={"failing": True}).json()["items"]
    ] == [top["reference"]]
    assert [
        b["reference"] for b in ex.admin.get(ex.purl("/bugs"), params={"q": "spk-2"}).json()["items"]
    ] == ["SPK-2"]
    in_cycle = ex.admin.get(ex.purl("/bugs"), params={"cycle_id": cid}).json()["items"]
    assert [(b["reference"].upper(), b["runs"]) for b in in_cycle] == [("SPK-431", 1)]
    links = ex.admin.get(ex.purl("/bugs/links"), params={"reference": "SPK-431"}).json()
    assert len(links) == 3
    assert ex.admin.get(ex.purl("/bugs/links"), params={"reference": "NOPE-1"}).status_code == 404


def test_ac_bug_04_tcms_106_failed_result_needs_a_bug_link(world: World) -> None:
    ex = Exec(world)
    _settings(ex, require_bug_link_for_failure=True)
    _, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    _record(ex.sana, res, "failed")
    r = _finish(ex.sana, res["id"])
    assert (r.status_code, r.json()["code"]) == (422, "bug_link_required"), r.text
    assert ex.run(run_id)["draft"]["state"] == "draft", "nothing was finalized"
    assert _link(ex.sana, res["id"], "SPK-3").status_code == 201
    assert _finish(ex.sana, res["id"]).status_code == 200
    _, passing = ex.one_run(steps=1, assignee=ex.sana_user)
    _done(ex.sana, passing, "passed")  # only failures need a link


def test_discarding_a_draft_removes_its_links(world: World) -> None:
    """docs/02 §8.2: discard (and closing a cycle with drafts) takes the attempt's links with it, audited."""
    ex = Exec(world)
    cid, run_id = ex.one_run(steps=1, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    _link(ex.sana, res["id"], "SPK-10")
    assert ex.sana.delete(f"/api/v1/results/{res['id']}").status_code == 204
    assert ex.admin.get(f"/api/v1/runs/{run_id}/bug-links").json() == []
    res2 = _start(ex.sana, run_id).json()
    _step(ex.sana, res2, 0, status="passed")
    _link(ex.sana, res2["id"], "SPK-11")
    assert ex.admin.post(f"/api/v1/cycles/{cid}/close", json={"discard_drafts": True}).status_code == 200
    assert ex.admin.get(f"/api/v1/cycles/{cid}/bug-links").json() == []
    reasons = [ctx for _, ctx in _audit(world, "bug.unlinked", ex.pid)]
    assert len(reasons) == 2
    assert "draft discarded" in str(reasons[0])
    assert f"when {ex.cycle(cid)['key']} was closed" in str(reasons[1])


def test_project_tracker_settings(world: World) -> None:
    ex = Exec(world)
    rv = ex.admin.get(ex.purl()).json()["row_version"]
    bad = ex.admin.patch(
        ex.purl(), json={"settings": {"bug_url_template": "https://x.test/"}, "row_version": rv}
    )
    assert bad.status_code == 422
    assert bad.json()["errors"][0]["field"] == "settings.bug_url_template"
    _settings(
        ex,
        bug_tracker_name="Azure DevOps",
        bug_url_template="https://dev.azure.com/acme/_workitems/edit/{ref}",
    )
    got = ex.admin.get(ex.purl()).json()["settings"]
    assert (got["bug_tracker_name"], got["bug_url_template"]) == (
        "Azure DevOps",
        "https://dev.azure.com/acme/_workitems/edit/{ref}",
    )
    assert got["require_bug_link_for_failure"] is False
    _settings(ex, bug_url_template="")
    assert ex.admin.get(ex.purl()).json()["settings"]["bug_url_template"] is None


def test_copy_bug_details_report(world: World) -> None:
    ex = Exec(world)
    _, run_id = ex.one_run(steps=3, assignee=ex.sana_user)
    res = _start(ex.sana, run_id).json()
    _record(ex.sana, res, "passed", "failed")
    r = ex.sana.get(f"/api/v1/results/{res['id']}/bug-report", params={"step_id": res["steps"][1]["step_id"]})
    assert r.status_code == 200, r.text
    text = r.json()["text"]
    assert "1. " in text
    assert "2. " in text
    assert "3. " not in text
    assert "**Actual**\nStep 2 went wrong" in text
    assert f"/run/{run_id}" in text
    assert (
        ex.sana.get(
            f"/api/v1/results/{res['id']}/bug-report",
            params={"step_id": "00000000-0000-0000-0000-000000000001"},
        ).status_code
        == 404
    )


def test_bug_links_are_project_scoped(world: World) -> None:
    ex = Exec(world)
    other = Exec(world, key="HELIOS")
    _, run_id = other.one_run(steps=1, assignee=other.sana_user)
    res = _start(other.sana, run_id).json()
    link = _link(other.sana, res["id"], "HEL-1").json()
    assert _link(ex.sana, res["id"], "SPK-1").status_code == 404
    assert ex.sana.delete(f"/api/v1/bug-links/{link['id']}").status_code == 404
    assert ex.admin.get(ex.purl("/bugs")).json()["total"] == 0
