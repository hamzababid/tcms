"""M6 — requirement references, coverage and traceability (docs/02 §10, ADR-024): AC-REQ-01…06, BR-23,
TCMS-110…112 at API level."""

from __future__ import annotations

from typing import Any

import pytest

from tests.api.test_attempts import Exec, _done
from tests.api.test_execution import _rows
from tests.world import ApiClient, World

pytestmark = pytest.mark.integration


class Req(Exec):
    """Exec plus a PM (requirement.manage) and helpers for releases, plans and cycles in a release."""

    def __init__(self, world: World, key: str = "SPARK") -> None:
        super().__init__(world, key)
        self.hira_user = self.member("Hira", "pm_ba")
        self.hira = world.login(self.hira_user)

    def release(self, name: str) -> str:
        r = self.admin.post(self.purl("/releases"), json={"name": name})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    def add(self, text: str, client: ApiClient | None = None, **body: Any) -> dict[str, Any]:
        r = (client or self.hira).post(self.purl("/requirements"), json={"references": text, **body})
        assert r.status_code == 201, r.text
        return dict(r.json())

    def cycle_in(self, release_id: str | None, case_ids: list[str]) -> list[str]:
        body: dict[str, Any] = {
            "selection": {"case_ids": case_ids},
            "default_assignee_id": str(self.sana_user.id),
        }
        if release_id:
            body["release_id"] = release_id
        cyc = self.create_cycle(name=f"Cycle {len(case_ids)} {release_id or 'none'} {id(body)}", **body)[
            "cycle"
        ]
        assert self.admin.post(f"/api/v1/cycles/{cyc['id']}/start").status_code == 200
        by_case = {r["test_case"]["id"]: r["id"] for r in self.runs(cyc["id"])}
        return [by_case[c] for c in case_ids]

    def trace(self, **params: Any) -> dict[str, Any]:
        r = self.admin.get(self.purl("/traceability"), params=params)
        assert r.status_code == 200, r.text
        return dict(r.json())


def _rows_by_ref(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["requirement"]["reference"]: row for row in trace["rows"]}


def test_ac_req_06_add_many_with_template_and_no_duplicates(world: World) -> None:
    sp = Req(world)
    rv = sp.admin.get(sp.purl()).json()["row_version"]
    sp.admin.patch(
        sp.purl(),
        json={"row_version": rv, "settings": {"bug_url_template": "https://jira.test/browse/{ref}"}},
    )
    out = sp.add("SPK-120, SPK-10\nSPK-2")
    assert out["created"] == 3
    assert next(r["url"] for r in out["references"]) == "https://jira.test/browse/SPK-120", (
        "falls back to the bug address"
    )
    rv = sp.admin.get(sp.purl()).json()["row_version"]
    sp.admin.patch(
        sp.purl(),
        json={"row_version": rv, "settings": {"requirement_url_template": "https://req.test/{ref}"}},
    )
    single = sp.add("spk-130", url=None, title="Sign in with SSO")
    assert (single["references"][0]["url"], single["references"][0]["title"]) == (
        "https://req.test/spk-130",
        "Sign in with SSO",
    )
    again = sp.add("SPK-120, SPK-999")
    assert again["created"] == 1, "existing references are reused"
    listed = sp.admin.get(sp.purl("/requirements")).json()["items"]
    assert [r["reference"] for r in listed] == ["SPK-2", "SPK-10", "SPK-120", "spk-130", "SPK-999"]
    assert sp.sana.post(sp.purl("/requirements"), json={"references": "X-1"}).status_code == 403, (
        "requirement.manage"
    )
    bad = sp.hira.post(sp.purl("/requirements"), json={"references": "OK-1", "url": "javascript:x"})
    assert bad.status_code == 422


def test_tcms_110_link_from_either_side_and_in_bulk(world: World) -> None:
    sp = Req(world)
    ref = sp.add("SPK-200")["references"][0]
    a, _ = sp.case("Login A")
    b, _ = sp.case("Login B")
    r = sp.sana.post(f"/api/v1/requirements/{ref['id']}/test-cases", json={"test_case_ids": [str(a)]})
    assert (r.status_code, r.json()["count"]) == (200, 1)
    assert (
        sp.sana.post(f"/api/v1/requirements/{ref['id']}/test-cases", json={"test_case_ids": [str(a)]}).json()[
            "count"
        ]
        == 0
    )
    r = sp.sana.post(f"/api/v1/test-cases/{b}/requirements", json={"references": "SPK-200 SPK-201"})
    assert (r.json()["count"], r.json()["created"]) == (2, 1), (
        "linking an unknown reference registers it (D12)"
    )
    bulk = sp.sana.post(
        sp.purl("/requirements/link-cases"), json={"references": "SPK-202", "test_case_ids": [str(a), str(b)]}
    )
    assert bulk.json()["count"] == 2
    case_refs = [x["reference"] for x in sp.admin.get(f"/api/v1/test-cases/{b}/requirements").json()]
    assert case_refs == ["SPK-200", "SPK-201", "SPK-202"]
    detail = sp.admin.get(f"/api/v1/requirements/{ref['id']}").json()
    assert sorted(c["id"] for c in detail["cases"]) == sorted([str(a), str(b)])
    # Repository filters (L19).
    keys = {
        c["id"]
        for c in sp.admin.get(sp.purl("/test-cases"), params={"requirement": "spk-201"}).json()["items"]
    }
    assert keys == {str(b)}
    unlinked, _ = sp.case("No requirement")
    without = {
        c["id"]
        for c in sp.admin.get(sp.purl("/test-cases"), params={"has_requirements": "false"}).json()["items"]
    }
    assert str(unlinked) in without
    assert str(a) not in without
    assert sp.sana.delete(f"/api/v1/requirements/{ref['id']}/test-cases/{a}").status_code == 204
    assert sp.sana.delete(f"/api/v1/requirements/{ref['id']}/test-cases/{a}").status_code == 404
    viewer = world.login(sp.member("Faisal", "viewer"))
    assert (
        viewer.post(f"/api/v1/test-cases/{b}/requirements", json={"references": "SPK-9"}).status_code == 403
    )
    actions = [
        r[0] for r in _rows(world, "SELECT action FROM audit_events WHERE project_id = :p", p=str(sp.pid))
    ]
    assert actions.count("requirement.linked") >= 5
    assert "requirement.unlinked" in actions


@pytest.mark.br("BR-23")
def test_br_23_ac_req_01_to_05_tcms_111_status_per_release(world: World) -> None:
    sp = Req(world)
    rel = sp.release("v2.5")
    other = sp.release("v2.6")
    a, _ = sp.case("Case A")
    b, _ = sp.case("Case B")
    archived, _ = sp.case("Gone")
    for text, cases in (("R-1", [a, b]), ("R-2", [a]), ("R-3", [archived])):
        sp.sana.post(
            sp.purl("/requirements/link-cases"),
            json={"references": text, "test_case_ids": [str(c) for c in cases]},
        )
    plan = sp.admin.post(
        sp.purl("/test-plans"), json={"name": "Plan 2.5", "type": "regression", "release_id": rel}
    ).json()
    assert (
        sp.admin.post(
            f"/api/v1/test-plans/{plan['id']}/requirements", json={"references": "R-3, R-4"}
        ).json()["count"]
        == 2
    )
    r = sp.admin.post(sp.purl("/test-cases/bulk"), json={"action": "archive", "case_ids": [str(archived)]})
    assert r.status_code == 200, r.text
    run_a, run_b = sp.cycle_in(rel, [str(a), str(b)])
    _done(sp.sana, run_a, "passed")
    rows = _rows_by_ref(sp.trace(release_id=rel))
    assert set(rows) == {"R-1", "R-2", "R-3", "R-4"}, (
        "scope: plan of the release or a linked case ran in it (D3)"
    )
    assert rows["R-1"]["status_in_release"] == "not_run"  # AC-REQ-01
    assert rows["R-2"]["status_in_release"] == "passed"
    assert rows["R-3"]["status_in_release"] == "not_covered"  # AC-REQ-03
    assert rows["R-4"]["status_in_release"] == "not_covered"  # AC-REQ-05 gap list
    _done(sp.sana, run_b, "failed")
    assert _rows_by_ref(sp.trace(release_id=rel))["R-1"]["status_in_release"] == "failed"  # AC-REQ-02
    # AC-REQ-04: a later retest in another cycle of the same release passes.
    (retest_b,) = sp.cycle_in(rel, [str(b)])
    _done(sp.sana, retest_b, "passed")
    trace = sp.trace(release_id=rel)
    assert _rows_by_ref(trace)["R-1"]["status_in_release"] == "passed"
    summary = trace["summary"]
    assert (summary["total"], summary["covered"], summary["passed"], summary["not_covered"]) == (4, 2, 2, 2)
    assert summary["coverage"] == {"numerator": 2, "denominator": 4, "value": 0.5}
    assert sp.admin.get(sp.purl("/coverage"), params={"release_id": rel}).json() == summary
    assert _rows_by_ref(sp.trace(release_id=other)) == {}, "nothing in scope for the other release"
    assert set(_rows_by_ref(sp.trace())) == {"R-1", "R-2", "R-3", "R-4"}, "no release: all references"
    # Matrix filters (TCMS-112).
    assert set(_rows_by_ref(sp.trace(release_id=rel, uncovered=True))) == {"R-3", "R-4"}
    assert set(_rows_by_ref(sp.trace(release_id=rel, status="passed"))) == {"R-1", "R-2"}
    assert set(_rows_by_ref(sp.trace(release_id=rel, q="r-2"))) == {"R-2"}
    r1 = _rows_by_ref(trace)["R-1"]
    latest = {c["key"]: c["latest"]["status"] for c in r1["cases"]}
    assert sorted(latest.values()) == ["passed", "passed"]
    plan_refs = sp.admin.get(
        sp.purl("/requirements"), params={"plan_id": plan["id"], "release_id": rel}
    ).json()
    assert [(r["reference"], r["status"]) for r in plan_refs["items"]] == [
        ("R-3", "not_covered"),
        ("R-4", "not_covered"),
    ]


def test_traceability_shows_bugs_of_the_release(world: World) -> None:
    sp = Req(world)
    rel = sp.release("v3")
    a, _ = sp.case("Case A")
    sp.sana.post(sp.purl("/requirements/link-cases"), json={"references": "R-9", "test_case_ids": [str(a)]})
    (run_a,) = sp.cycle_in(rel, [str(a)])
    rid = _done(sp.sana, run_a, "failed")["result"]["id"]
    sp.sana.post(f"/api/v1/results/{rid}/bug-links", json={"reference": "BUG-1"})
    (outside,) = sp.cycle_in(None, [str(a)])
    rid2 = _done(sp.sana, outside, "failed")["result"]["id"]
    sp.sana.post(f"/api/v1/results/{rid2}/bug-links", json={"reference": "BUG-2"})
    row = _rows_by_ref(sp.trace(release_id=rel))["R-9"]
    assert [b["reference"] for b in row["bugs"]] == ["BUG-1"], "only bugs from runs of the release"
    assert {b["reference"] for b in _rows_by_ref(sp.trace())["R-9"]["bugs"]} == {"BUG-1", "BUG-2"}


def test_traceability_rows_are_paged_and_the_summary_is_not(world: World) -> None:
    sp = Req(world)
    sp.add("TR-1, TR-2, TR-3")
    first = sp.trace(page_size=2)
    assert (len(first["rows"]), first["total"], first["page"], first["page_size"]) == (2, 3, 1, 2)
    assert first["summary"]["total"] == 3, "the summary counts every reference in scope"
    second = sp.trace(page_size=2, page=2)
    assert len(second["rows"]) == 1
    seen = {r["requirement"]["reference"] for r in first["rows"] + second["rows"]}
    assert seen == {"TR-1", "TR-2", "TR-3"}
    narrowed = sp.trace(q="TR-2", page_size=2)
    assert (narrowed["total"], narrowed["summary"]["total"]) == (1, 3)


def test_edit_archive_restore_and_permissions(world: World) -> None:
    sp = Req(world)
    ref = sp.add("SPK-300")["references"][0]
    url = f"/api/v1/requirements/{ref['id']}"
    r = sp.hira.patch(url, json={"title": "Export PDF", "url": "https://jira.test/SPK-300"})
    assert (r.status_code, r.json()["title"]) == (200, "Export PDF")
    assert sp.sana.patch(url, json={"title": "x"}).status_code == 403
    assert sp.hira.patch(url, json={"url": "ftp://x"}).status_code == 422
    assert sp.hira.post(url + "/archive").json()["archived"] is True
    assert [x["reference"] for x in sp.admin.get(sp.purl("/requirements")).json()["items"]] == []
    assert len(sp.admin.get(sp.purl("/requirements"), params={"include_archived": True}).json()["items"]) == 1
    assert sp.hira.post(url + "/restore").json()["archived"] is False
    sp.hira.post(url + "/archive")
    assert sp.add("SPK-300")["references"][0]["archived"] is False, "adding it again restores it"
    actions = {
        r[0] for r in _rows(world, "SELECT action FROM audit_events WHERE project_id = :p", p=str(sp.pid))
    }
    assert {
        "requirement.created",
        "requirement.updated",
        "requirement.archived",
        "requirement.restored",
    } <= actions


def test_requirements_are_project_scoped(world: World) -> None:
    sp = Req(world)
    other = Req(world, key="HELIOS")
    ref = other.add("HEL-1")["references"][0]
    assert sp.admin.get(f"/api/v1/requirements/{ref['id']}").status_code in (403, 404)
    assert sp.hira.get(f"/api/v1/requirements/{ref['id']}").status_code == 404
    case, _ = sp.case("Mine")
    r = sp.sana.post(f"/api/v1/requirements/{ref['id']}/test-cases", json={"test_case_ids": [str(case)]})
    assert r.status_code == 404
    foreign_release = other.release("v9")
    assert sp.admin.get(sp.purl("/traceability"), params={"release_id": foreign_release}).status_code == 404


def test_us_072_plan_requirements_link_and_unlink(world: World) -> None:
    sp = Req(world)
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Scoped", "type": "smoke"}).json()
    url = f"/api/v1/test-plans/{plan['id']}/requirements"
    assert sp.admin.post(url, json={"references": "P-1, P-2"}).json()["count"] == 2
    assert sp.admin.post(url, json={"references": "P-2"}).json()["count"] == 0
    got = sp.admin.get(f"/api/v1/test-plans/{plan['id']}", params={"include": "requirements"}).json()
    assert got["requirement_count"] == 2
    ids_ = got["requirement_ids"]
    assert sp.admin.request("DELETE", url, json={"requirement_ids": [ids_[0]]}).json()["count"] == 1
    assert sp.sana.post(url, json={"references": "P-3"}).status_code == 403, "plan.manage"
