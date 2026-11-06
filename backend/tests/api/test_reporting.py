"""M7a — metrics, dashboards, readiness, decisions, reports and exports (docs/02 §11; M7 spec):
AC-RPT-01…05, AC-REL-01…03, BR-24, TCMS-113…117 at API level."""

from __future__ import annotations

import csv
import io
from typing import Any

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from tcms.platform.jobs.worker import run_one
from tests.api.test_attempts import _done
from tests.api.test_execution import _bump_version, _rows
from tests.api.test_requirements import Req
from tests.world import World

pytestmark = pytest.mark.integration


class Rep(Req):
    def plan(
        self, release_id: str | None, case_ids: list[str], rules: list[dict[str, Any]], name: str
    ) -> str:
        body: dict[str, Any] = {"name": name, "type": "regression", "exit_rules": rules}
        if release_id:
            body["release_id"] = release_id
        r = self.admin.post(self.purl("/test-plans"), json=body)
        assert r.status_code == 201, r.text
        pid = str(r.json()["id"])
        assert (
            self.admin.post(f"/api/v1/test-plans/{pid}/cases", json={"case_ids": case_ids}).status_code == 200
        )
        return pid

    def plan_cycle(self, plan_id: str, release_id: str | None) -> list[str]:
        body: dict[str, Any] = {
            "name": f"From plan {plan_id[-6:]} {len(self.runs_cache)}",
            "plan_id": plan_id,
            "selection": {"from_plan": True},
            "default_assignee_id": str(self.sana_user.id),
        }
        if release_id:
            body["release_id"] = release_id
        cyc = self.create_cycle(**body)["cycle"]
        assert self.admin.post(f"/api/v1/cycles/{cyc['id']}/start").status_code == 200
        runs = [r["id"] for r in self.runs(cyc["id"])]
        self.runs_cache.append(cyc["id"])
        return runs

    runs_cache: list[str]

    def __init__(self, world: World, key: str = "SPARK") -> None:
        super().__init__(world, key)
        self.runs_cache = []

    def readiness(self, release_id: str) -> dict[str, Any]:
        r = self.admin.get(f"/api/v1/releases/{release_id}/readiness")
        assert r.status_code == 200, r.text
        return dict(r.json())


def _rules(ready: dict[str, Any]) -> dict[str, tuple[bool, Any]]:
    return {
        x["type"]: (x["met"], x["count"] if x["count"] is not None else (x["actual"] or {}).get("numerator"))
        for x in ready["rules"]
    }


@pytest.mark.br("BR-24")
def test_br_24_ac_rpt_01_02_tcms_113_114_summary_rates_and_superseded_runs(world: World) -> None:
    sp = Rep(world)
    rel = sp.release("v1")
    cases = [str(sp.case(f"Sum {i}")[0]) for i in range(5)]
    runs = sp.cycle_in(rel, cases)
    empty = sp.admin.get(sp.purl("/execution-summary"), params={"release_id": rel}).json()
    assert empty["pass_rate"] == {"numerator": 0, "denominator": 0, "value": None}, "AC-RPT-02: — not 0%"
    _done(sp.sana, runs[0], "passed")
    _done(sp.sana, runs[1], "passed")
    _done(sp.sana, runs[2], "failed")
    _done(sp.sana, runs[3], "skipped", outcome="not_applicable", reason="Not in this build")
    _done(sp.sana, runs[4], "failed")
    _bump_version(sp, __import__("uuid").UUID(cases[4]))
    assert sp.admin.post(f"/api/v1/runs/{runs[4]}/replace").status_code == 201  # supersedes the failed run
    m = sp.admin.get(sp.purl("/execution-summary"), params={"release_id": rel}).json()
    assert (m["total"], m["not_applicable"], m["applicable"], m["executed"]) == (5, 1, 4, 3)
    assert m["failed"] == 1, "TCMS-114: the superseded failed run is not counted"
    assert m["pass_rate"] == {"numerator": 2, "denominator": 3, "value": 2 / 3}
    assert m["execution_progress"]["numerator"] == 3
    assert m["execution_progress"]["denominator"] == 4
    dash = sp.admin.get(sp.purl("/dashboards/manager"), params={"release_id": rel}).json()
    assert dash["summary"] == m, "TCMS-115: the Overview uses the same numbers"
    report = sp.admin.get(sp.purl("/reports/cycle-execution"), params={"release_id": rel}).json()
    statuses = sorted(r["status"] for r in report["items"])
    assert statuses == sorted(["passed", "passed", "failed", "not_applicable", "not_run"])
    assert report["total"] == m["total"]
    assert sum(1 for r in report["items"] if r["status"] == "failed") == dash["summary"]["failed"]


def test_ac_rel_01_tcms_116_plan_rules_over_the_plans_cycles(world: World) -> None:
    sp = Rep(world)
    rel = sp.release("v2.5")
    a = [str(sp.case(f"Case A{i}")[0]) for i in range(4)]
    b = [str(sp.case(f"Case B{i}")[0]) for i in range(2)]
    plan_a = sp.plan(
        rel,
        a,
        [{"type": "min_pass_rate", "threshold": 0.95}, {"type": "max_failed", "threshold": 0}],
        "Regression",
    )
    plan_b = sp.plan(rel, b, [{"type": "min_execution_progress", "threshold": 1.0}], "Smoke")
    sp.plan(rel, b, [], "No rules")  # plans without rules do not count (D1)
    runs_a = sp.plan_cycle(plan_a, rel)
    runs_b = sp.plan_cycle(plan_b, rel)
    for r in runs_a[:3]:
        _done(sp.sana, r, "passed")
    _done(sp.sana, runs_a[3], "failed")
    ready = sp.readiness(rel)
    assert ready["ready"] is False
    assert ready["uses_defaults"] is False
    by_plan = {p["plan"]["name"]: p["ready"] for p in ready["plans"]}
    assert by_plan == {"Regression": False, "Smoke": False}
    rules = {(x["plan"]["name"], x["type"]): x for x in ready["rules"]}
    assert rules[("Regression", "min_pass_rate")]["actual"] == {
        "numerator": 3,
        "denominator": 4,
        "value": 0.75,
    }
    assert (rules[("Regression", "max_failed")]["count"], rules[("Regression", "max_failed")]["met"]) == (
        1,
        False,
    )
    assert rules[("Smoke", "min_execution_progress")]["actual"]["numerator"] == 0, (
        "only the Smoke plan's cycles"
    )
    # An ad-hoc cycle in the release does not change a plan's rules (D1).
    (extra,) = sp.cycle_in(rel, [b[0]])
    _done(sp.sana, extra, "passed")
    again = {(x["plan"]["name"], x["type"]): x["actual"] for x in sp.readiness(rel)["rules"]}
    assert again[("Smoke", "min_execution_progress")]["numerator"] == 0
    for r in runs_b:
        _done(sp.sana, r, "passed")
    plan_view = sp.admin.get(f"/api/v1/test-plans/{plan_b}/readiness").json()
    assert (plan_view["ready"], plan_view["plan"]["key"]) == (True, plan_view["plan"]["key"]), "L25"
    _done(sp.sana, runs_a[3], "passed")  # retest
    final = sp.readiness(rel)
    assert final["ready"] is True, final


def test_ac_rel_02_defaults_when_no_plan_has_rules(world: World) -> None:
    sp = Rep(world)
    rel = sp.release("v3")
    cases = [str(sp.case(f"Case D{i}")[0]) for i in range(2)]
    runs = sp.cycle_in(rel, cases)
    ready = sp.readiness(rel)
    assert ready["uses_defaults"] is True
    types = [x["type"] for x in ready["rules"]]
    assert types == ["min_execution_progress", "max_failed", "min_pass_rate_applicable"], (
        "the default coverage rule needs references in scope"
    )
    assert all(x["plan"] is None for x in ready["rules"])
    assert ready["ready"] is False
    sp.sana.post(sp.purl("/requirements/link-cases"), json={"references": "R-1", "test_case_ids": cases})
    for r in runs:
        _done(sp.sana, r, "passed")
    ready = sp.readiness(rel)
    assert [x["type"] for x in ready["rules"]][-1] == "min_requirement_coverage"
    assert ready["ready"] is True, _rules(ready)
    empty = sp.release("v4")
    nothing = sp.readiness(empty)
    assert nothing["ready"] is False
    assert {x["note"] for x in nothing["rules"]} == {"No runs in scope"}, "D2: undefined is not met"


def test_ac_rel_03_tcms_116_decision_is_append_only_with_a_snapshot(world: World, owner_engine: Any) -> None:
    sp = Rep(world)
    rel = sp.release("v5")
    (run,) = sp.cycle_in(rel, [str(sp.case("One")[0])])
    _done(sp.sana, run, "failed")
    url = f"/api/v1/releases/{rel}/decisions"
    r = sp.admin.post(url, json={"decision": "go_with_risks", "comment": "Ship it"})
    assert (r.status_code, r.json()["errors"][0]["field"]) == (422, "risks")
    assert sp.bilal.post(url, json={"decision": "go", "comment": "x"}).status_code == 403, "release.manage"
    r = sp.admin.post(url, json={"decision": "no_go", "comment": "One failure open"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["decision"], d["ready"], d["snapshot"]["summary"]["failed"]) == ("no_go", False, 1)
    assert d["snapshot"]["release"]["name"] == "v5"
    _done(sp.sana, run, "passed")
    later = sp.admin.post(
        url, json={"decision": "go_with_risks", "comment": "Retested", "risks": "Perf untested"}
    )
    assert later.status_code == 201
    listed = sp.admin.get(url).json()
    assert [x["decision"] for x in listed] == ["go_with_risks", "no_go"]
    assert listed[1]["snapshot"] == d["snapshot"], "later results do not change the stored snapshot"
    assert sp.readiness(rel)["latest_decision"]["decision"] == "go_with_risks"
    with world.factory() as s, pytest.raises(Exception, match=r"permission denied|immutable_record"):
        s.execute(text("UPDATE release_decisions SET comment = 'x' WHERE id = :i"), {"i": d["id"]})
        s.commit()
    actions = [a for (a,) in _rows(world, "SELECT action FROM audit_events WHERE entity_id = :e", e=rel)]
    assert actions.count("release.decision_recorded") == 2
    summaries = sp.admin.get(sp.purl("/release-summaries")).json()
    v5 = next(x for x in summaries if x["name"] == "v5")
    assert v5["latest_decision"]["decision"] == "go_with_risks"


def test_tcms_115_manager_dashboard_widgets(world: World) -> None:
    sp = Rep(world)
    rel = sp.release("v6")
    cases = [str(sp.case(f"Case M{i}")[0]) for i in range(3)]
    sp.admin.post(
        sp.purl("/test-cases/bulk"),
        json={"action": "add_tags", "case_ids": cases[:1], "params": {"tags": ["regression"]}},
    )
    runs = sp.cycle_in(rel, cases)
    res = _done(sp.sana, runs[0], "failed")
    sp.sana.post(f"/api/v1/results/{res['result']['id']}/bug-links", json={"reference": "SPK-1"})
    _done(sp.sana, runs[1], "failed")
    sp.add("SPK-90")
    d = sp.admin.get(sp.purl("/dashboards/manager"), params={"release_id": rel}).json()
    assert d["bugs"] == {"linked": 1, "on_failing_runs": 1, "failures_without_bug": 1}
    assert [b["reference"] for b in d["top_bugs"]] == ["SPK-1"]
    assert d["regression"]["total"] == 1
    assert d["regression"]["failed"] == 1
    (sana,) = [t for t in d["team"] if t["user"] and t["user"]["id"] == str(sp.sana_user.id)]
    assert (sana["assigned"], sana["executed"], sana["remaining"], sana["failed"]) == (3, 2, 1, 2)
    assert d["readiness"]["release"]["name"] == "v6"
    assert d["readiness"]["ready"] is False
    assert len(d["cycles"]) == 1
    assert d["cycles"][0]["summary"]["failed"] == 2
    assert d["repository"]["total_cases"] >= 3
    mine = sp.admin.get(sp.purl("/dashboards/manager"), params={"tester_id": str(sp.omar_user.id)}).json()
    assert mine["summary"]["total"] == 0
    bad = sp.admin.get(sp.purl("/dashboards/manager"), params={"cycle_ids": "nope"})
    assert bad.status_code == 400
    org = sp.admin.get("/api/v1/organization/dashboard").json()["projects"]
    assert [p["project"]["key"] for p in org] == ["SPARK"]
    assert org[0]["failed"] == 2
    assert org[0]["active_cycles"] == 1
    viewer = world.login(sp.member("Faisal", "viewer"))
    assert [p["project"]["key"] for p in viewer.get("/api/v1/organization/dashboard").json()["projects"]] == [
        "SPARK"
    ]
    outsider = world.login(world.user(sp.org, "Nobody"))
    assert outsider.get("/api/v1/organization/dashboard").json()["projects"] == [], (
        "US-146: own projects only"
    )


def test_quality_dashboard_trends_from_snapshots(world: World, clean_jobs: None) -> None:
    sp = Rep(world)
    rel = sp.release("v7")
    runs = sp.cycle_in(rel, [str(sp.case(f"Case Q{i}")[0]) for i in range(2)])
    _done(sp.sana, runs[0], "passed")
    _done(sp.sana, runs[1], "failed")
    r = sp.admin.post(sp.purl("/metrics/refresh"))
    assert r.status_code == 202
    assert sp.admin.post(sp.purl("/metrics/refresh")).status_code == 202, "deduplicated, not an error"
    while run_one(world.factory, "test-worker"):
        pass
    snaps = _rows(
        world, "SELECT release_id, counters FROM metric_snapshots WHERE project_id = :p", p=str(sp.pid)
    )
    assert len(snaps) == 3, "project, release and cycle scopes"
    by_rel = {str(r) if r else None: c for r, c in snaps}
    assert by_rel[rel]["failed"] == 1
    assert by_rel[rel]["executed_on_day"] == 2
    q = sp.admin.get(sp.purl("/dashboards/quality"), params={"release_id": rel}).json()
    today = q["days"][-1]
    assert (today["live"], today["executed"], today["passed"], today["failed"]) == (True, 2, 1, 1)
    assert today["pass_rate"]["value"] == 0.5
    assert [x["release"]["name"] for x in q["releases"]] == ["v7"]
    assert q["last_snapshot_day"] is not None


def test_reports_filters_and_columns(world: World) -> None:
    sp = Rep(world)
    rel = sp.release("v8")
    cases = [str(sp.case(f"Case R{i}")[0]) for i in range(2)]
    sp.sana.post(
        sp.purl("/requirements/link-cases"), json={"references": "SPK-7", "test_case_ids": cases[:1]}
    )
    runs = sp.cycle_in(rel, cases)
    res = _done(sp.sana, runs[0], "failed")
    sp.sana.post(f"/api/v1/results/{res['result']['id']}/bug-links", json={"reference": "SPK-2"})
    _done(sp.sana, runs[1], "passed")

    def rep(name: str, **params: Any) -> dict[str, Any]:
        r = sp.admin.get(sp.purl(f"/reports/{name}"), params=params)
        assert r.status_code == 200, r.text
        return dict(r.json())

    ce = rep("cycle-execution", release_id=rel, status="failed")
    assert [(r["status"], r["bugs"], r["assignee"]) for r in ce["items"]] == [("failed", "SPK-2", "Sana")]
    assert [c["key"] for c in ce["columns"]][:3] == ["cycle", "case_key", "title"]
    hist = rep("results-history", release_id=rel)
    assert sorted(r["status"] for r in hist["items"]) == ["failed", "passed"]
    assert rep("bug-links", release_id=rel)["items"][0]["reference"] == "SPK-2"
    tr = rep("traceability", release_id=rel)
    assert [(r["requirement"], r["status_in_release"], r["bugs"]) for r in tr["items"]] == [
        ("SPK-7", "failed", "SPK-2")
    ]
    act = rep("tester-activity", release_id=rel)
    assert [(r["tester"], r["executed"], r["failed"]) for r in act["items"]] == [("Sana", 2, 1)]
    inv = rep("case-inventory", release_id=rel)
    assert {r["latest_status"] for r in inv["items"]} == {"failed", "passed"}
    assert next(r for r in inv["items"] if r["requirements"])["requirements"] == "SPK-7"
    assert (
        sp.admin.get(sp.purl("/reports/bug-links"), params={"tester_id": str(sp.sana_user.id)}).status_code
        == 400
    )
    assert sp.admin.get(sp.purl("/reports/unknown")).status_code == 404
    assert sp.admin.get(sp.purl("/reports/case-inventory"), params={"page_size": 1}).json()["total"] == 2


def test_ac_rpt_05_tcms_117_export_escapes_formulas(world: World) -> None:
    sp = Rep(world)
    case_id, _ = sp.case('=HYPERLINK("http://evil")')
    (run,) = sp.cycle_in(None, [str(case_id)])
    _done(sp.sana, run, "passed")
    url = sp.purl("/reports/cycle-execution/export")
    r = sp.admin.post(url, json={"format": "csv", "filters": {}})
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Cycle", "Case", "Title"]
    assert rows[1][2] == '\'=HYPERLINK("http://evil")'
    x = sp.admin.post(url, json={"format": "xlsx", "filters": {}})
    assert x.status_code == 200
    ws = load_workbook(io.BytesIO(x.content), read_only=True).active
    values = [list(row) for row in ws.iter_rows(values_only=True)]  # type: ignore[union-attr]
    assert values[1][2] == '\'=HYPERLINK("http://evil")'
    viewer_no_export = world.login(sp.member("Ghost", "viewer"))
    assert viewer_no_export.post(url, json={"format": "csv", "filters": {}}).status_code == 200, "data.export"
    acts = [
        a for (a,) in _rows(world, "SELECT action FROM audit_events WHERE project_id = :p", p=str(sp.pid))
    ]
    assert acts.count("export.created") == 3


def test_ac_rpt_04_large_export_runs_in_the_background(
    world: World, clean_jobs: None, monkeypatch: Any
) -> None:
    from tcms.reporting import exports

    monkeypatch.setattr(exports, "SYNC_MAX", 1)
    sp = Rep(world)
    runs = sp.cycle_in(None, [str(sp.case(f"Big {i}")[0]) for i in range(3)])
    _done(sp.sana, runs[0], "passed")
    r = sp.sana.post(sp.purl("/reports/cycle-execution/export"), json={"format": "xlsx", "filters": {}})
    assert r.status_code == 202, r.text
    tid = r.json()["transfer_id"]
    assert sp.sana.get(f"/api/v1/data-transfers/{tid}").json()["status"] == "generating"
    from tcms.platform import transfers

    transfers.configure(world.app.state.tcms.store)  # other tests build apps with other settings
    while run_one(world.factory, "test-worker"):
        pass
    t = sp.sana.get(f"/api/v1/data-transfers/{tid}").json()
    errors = _rows(world, "SELECT type, status, last_error FROM jobs")
    assert t["status"] == "ready", errors
    assert t["summary"]["rows"] == 3
    f = sp.sana.get(t["download_url"])
    assert f.status_code == 200
    assert len(list(load_workbook(io.BytesIO(f.content), read_only=True).active.iter_rows())) == 4  # type: ignore[union-attr]
    assert sp.omar.get(t["download_url"]).status_code == 403, "initiator only"
    assert sp.admin.get(f"/api/v1/data-transfers/{tid}").status_code == 200, "project.configure may see it"
    notes = _rows(world, "SELECT type FROM notifications WHERE user_id = :u", u=str(sp.sana_user.id))
    assert ("export.ready",) in [tuple(n) for n in notes]
