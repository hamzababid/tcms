"""M8a — import wizard and exports (docs/02 §15; M8 D2–D7): AC-IMP-01…03, TCMS-134…136, US-150…153."""

from __future__ import annotations

import io
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from tcms.platform import transfers
from tcms.platform.jobs.worker import run_one
from tests.api.test_execution import Space, _rows
from tests.world import ApiClient, World

pytestmark = pytest.mark.integration

HEADER = ["ID", "Summary", "Module", "Prio", "Step", "Expected", "Tags"]


def _xlsx(rows: list[list[Any]], header: list[str] = HEADER, sheet: str = "Regression") -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet
    ws.append(header)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _csv(rows: list[list[str]], header: list[str]) -> bytes:
    lines = [",".join(header)] + [",".join(r) for r in rows]
    return ("\n".join(lines) + "\n").encode()


class Imp(Space):
    def __init__(self, world: World) -> None:
        super().__init__(world)
        transfers.configure(world.app.state.tcms.store)  # other tests build apps with other settings

    def upload(
        self,
        data: bytes,
        name: str = "cases.xlsx",
        entity: str = "test_case",
        client: ApiClient | None = None,
    ) -> dict[str, Any]:
        r = (client or self.admin).post(
            self.purl("/imports"), files={"file": (name, data)}, data={"entity": entity}
        )
        assert r.status_code == 201, r.text
        return dict(r.json())

    def run(self) -> None:
        while run_one(self.world.factory, "test-worker"):
            pass

    def validate(self, up: dict[str, Any], client: ApiClient | None = None, **body: Any) -> dict[str, Any]:
        sheet = up["sheets"][0]
        payload = {"sheet": sheet["name"], "mapping": body.pop("mapping", sheet["suggested_mapping"]), **body}
        r = (client or self.admin).post(f"/api/v1/data-transfers/{up['transfer_id']}/validate", json=payload)
        assert r.status_code == 202, r.text
        self.run()
        return dict((client or self.admin).get(f"/api/v1/data-transfers/{up['transfer_id']}").json())

    def commit(self, up: dict[str, Any], client: ApiClient | None = None) -> Any:
        r = (client or self.admin).post(f"/api/v1/data-transfers/{up['transfer_id']}/commit")
        if r.status_code == 202:
            self.run()
        return r


def test_us_150_upload_suggests_a_mapping_and_value_lists(world: World, clean_jobs: None) -> None:
    sp = Imp(world)
    up = sp.upload(_xlsx([["", "Login works", "Web/Auth", "P1", "Open login", "Form shown", "smoke"]]))
    sheet = up["sheets"][0]
    assert (sheet["name"], sheet["rows"]) == ("Regression", 1)
    assert sheet["suggested_mapping"] == {
        "ID": "key", "Summary": "title", "Module": "folder", "Prio": "priority", "Step": "step_action",
        "Expected": "step_expected", "Tags": "tags",
    }  # fmt: skip
    assert sheet["values"]["Prio"] == ["P1"]
    assert {f["key"] for f in up["fields"]} >= {"title", "priority", "step_action"}
    assert (
        sp.admin.post(
            sp.purl("/imports"), files={"file": ("x.txt", b"a")}, data={"entity": "test_case"}
        ).status_code
        == 415
    )
    big = b"0" * (20 * 1024 * 1024 + 1)
    assert (
        sp.admin.post(
            sp.purl("/imports"), files={"file": ("x.csv", big)}, data={"entity": "test_case"}
        ).status_code
        == 413
    )


def test_ac_imp_01_tcms_134_dry_run_reports_row_errors_and_gates_commit(
    world: World, clean_jobs: None
) -> None:
    sp = Imp(world)
    rows = [
        [
            "",
            "Login with valid credentials",
            "Web/Auth/Login",
            "P1",
            "Open the login page",
            "Form shown",
            "smoke",
        ],
        ["", "", "", "", "Enter email and password", "Dashboard in 3 s", ""],
        ["", "Locked account", "Web/Auth/Login", "Urgent!!", "Try to sign in", "Locked message", ""],
        ["", "Reset password", "Web/Auth/Reset", "", "", "Mail arrives", ""],
    ]
    up = sp.upload(_xlsx(rows))
    t = sp.validate(up)
    assert t["status"] == "validated"
    counts = t["summary"]["counts"]
    assert (counts["create"], counts["error"], counts["folders_to_create"]) == (1, 2, 3)
    errs = {(e["row"], e["column"], e["code"]) for e in t["errors"]}
    assert (4, "priority", "invalid_value") in errs, "AC-IMP-01: row and column"
    assert (5, "step_action", "field_required") in errs
    assert t["summary"]["committable"] is False
    r = sp.commit(up)
    assert (r.status_code, r.json()["code"]) == (409, "import_has_errors")
    csv_errors = sp.admin.get(f"/api/v1/data-transfers/{up['transfer_id']}/errors")
    assert "Urgent!!" in csv_errors.text
    t = sp.validate(up, options={"skip_error_rows": True}, value_maps={"priority": {"Urgent!!": "critical"}})
    assert t["summary"]["counts"]["error"] == 1, "the value map fixed the priority"
    assert sp.commit(up).status_code == 202
    done = sp.admin.get(f"/api/v1/data-transfers/{up['transfer_id']}").json()
    assert done["status"] == "committed", done
    assert done["summary"]["result"] == {
        "created": 2,
        "updated": 0,
        "unchanged": 0,
        "skipped": 1,
        "folders_created": 3,
    }
    report = sp.admin.get(done["download_url"]).text
    assert "skipped" in report
    assert "created" in report
    cases = sp.admin.get(sp.purl("/test-cases"), params={"q": "Login with valid"}).json()["items"]
    assert len(cases) == 1
    detail = sp.admin.get(f"/api/v1/test-cases/{cases[0]['id']}").json()
    assert [s["action"] for s in detail["version"]["steps"]] == [
        "Open the login page",
        "Enter email and password",
    ]
    assert (detail["priority"], detail["tags"]) == ("high", ["smoke"])
    acts = [
        a for (a,) in _rows(world, "SELECT action FROM audit_events WHERE project_id = :p", p=str(sp.pid))
    ]
    assert acts.count("import.committed") == 1
    ctx_rows = _rows(
        world,
        "SELECT count(*) FROM audit_events WHERE action = 'test_case.created' AND context->>'bulk_operation_id' = :t",
        t=up["transfer_id"],
    )
    assert ctx_rows[0][0] == 2, "each case's audit carries the import id"


def test_ac_imp_02_tcms_135_export_then_reimport_is_a_no_op(world: World, clean_jobs: None) -> None:
    sp = Imp(world)
    up = sp.upload(
        _xlsx(
            [
                [
                    "",
                    "-1 day looks like a formula",
                    "Suite A",
                    "high",
                    "Step one",
                    "One",
                    "smoke, regression",
                ],
                ["", "", "", "", "Step two", "", ""],
                ["", "Second case", "Suite A/Sub", "low", "Only step", "Done", ""],
            ]
        )
    )
    sp.validate(up)
    sp.commit(up)
    r = sp.admin.post(
        sp.purl("/exports"), json={"entity": "test_case", "format": "xlsx", "filters": {"q": ""}}
    )
    assert r.status_code == 200, r.text
    ws = load_workbook(io.BytesIO(r.content), read_only=True).active
    exported = [list(x) for x in ws.iter_rows(values_only=True)]  # type: ignore[union-attr]
    assert exported[0][:3] == ["Key", "Title", "Folder"]
    assert exported[1][1] == "'-1 day looks like a formula", "formula escaped on export"
    again = sp.upload(r.content, name="export.xlsx")
    t = sp.validate(again)
    assert t["summary"]["counts"]["unchanged"] == 2, t
    assert (t["summary"]["counts"]["create"], t["summary"]["counts"]["update"]) == (0, 0), "AC-IMP-02"
    assert sp.commit(again).status_code == 409, "nothing to import"
    # Edit one title in the export: one update with a new version.
    wb = load_workbook(io.BytesIO(r.content))
    sheet = wb.active
    assert sheet is not None
    sheet.cell(row=4, column=2, value="Second case renamed")
    buf = io.BytesIO()
    wb.save(buf)
    edited = sp.upload(buf.getvalue(), name="edited.xlsx")
    t = sp.validate(edited)
    assert (t["summary"]["counts"]["update"], t["summary"]["counts"]["unchanged"]) == (1, 1)
    sp.commit(edited)
    key = exported[3][0]
    case = sp.admin.get(sp.purl("/resolve"), params={"key": key}).json()
    detail = sp.admin.get(f"/api/v1/test-cases/{case['id']}").json()
    assert (detail["title"], detail["latest_version_no"]) == ("Second case renamed", 2)


def test_ac_imp_03_tcms_136_a_failure_leaves_nothing(
    world: World, clean_jobs: None, monkeypatch: Any
) -> None:
    from tcms.testdesign import service as testdesign

    sp = Imp(world)
    up = sp.upload(_xlsx([["", f"Case {i}", "Atomic", "", "Do", "", ""] for i in range(3)]))
    sp.validate(up)
    real = testdesign.create_case
    calls = {"n": 0}

    def flaky(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk on fire")
        return real(*a, **k)

    monkeypatch.setattr(testdesign, "create_case", flaky)
    sp.commit(up)
    t = sp.admin.get(f"/api/v1/data-transfers/{up['transfer_id']}").json()
    assert t["status"] == "failed"
    assert "Nothing was imported" in t["errors"][0]["message"]
    assert sp.admin.get(sp.purl("/test-cases"), params={"q": "Case"}).json()["total"] == 0
    assert [f["name"] for f in sp.admin.get(sp.purl("/folders")).json()] == ["Suite"], "no folder either"
    audit = _rows(
        world,
        "SELECT count(*) FROM audit_events WHERE context->>'bulk_operation_id' = :t",
        t=up["transfer_id"],
    )
    assert audit[0][0] == 0, "no audit rows from the rolled-back part"
    notes = _rows(world, "SELECT type FROM notifications WHERE entity_id = :t", t=up["transfer_id"])
    assert [n for (n,) in notes] == ["import.failed"]


def test_single_cell_steps_owner_fallback_and_folder_permission(world: World, clean_jobs: None) -> None:
    sp = Imp(world)
    sana_user = sp.member("Sana", "qa_engineer")
    sana = world.login(sana_user)
    header = ["Title", "Steps", "Expected", "Owner", "Folder"]
    data = _csv(
        [
            [
                "Checkout total",
                '"1. Add item\n2. Open cart"',
                '"1. Added\n2. Total shown"',
                "nobody@x.test",
                "Suite",
            ]
        ],
        header,
    )
    up = sp.upload(data, name="cases.csv", client=sana)
    t = sp.validate(up, client=sana, options={"steps_layout": "single_cell"})
    assert t["summary"]["counts"]["create"] == 1
    assert [w["code"] for w in t["summary"]["warnings"]] == ["unknown_owner"]
    sp.commit(up, client=sana)
    case = sp.admin.get(sp.purl("/test-cases"), params={"q": "Checkout total"}).json()["items"][0]
    detail = sp.admin.get(f"/api/v1/test-cases/{case['id']}").json()
    assert [(s["action"], s["expected_result"]) for s in detail["version"]["steps"]] == [
        ("Add item", "Added"),
        ("Open cart", "Total shown"),
    ]
    assert detail["owner"]["id"] == str(sana_user.id), "unknown owner → the importer"
    # An engineer cannot create folders (folder.manage).
    up2 = sp.upload(
        _csv([["New area case", "Do it", "", "", "Brand new area"]], header), name="b.csv", client=sana
    )
    t2 = sp.validate(up2, client=sana)
    assert [e["code"] for e in t2["errors"]] == ["permission_denied"]
    assert sp.admin.get(f"/api/v1/data-transfers/{up2['transfer_id']}").status_code == 200, (
        "project.configure sees it"
    )
    viewer = world.login(sp.member("Faisal", "viewer"))
    assert (
        viewer.post(
            sp.purl("/imports"), files={"file": ("a.csv", data)}, data={"entity": "test_case"}
        ).status_code
        == 403
    )


def test_us_153_requirement_references_import_and_export(world: World, clean_jobs: None) -> None:
    sp = Imp(world)
    a_id, a_key = sp.case("Requirement case A")
    b_id, b_key = sp.case("Requirement case B")
    sp.admin.post(sp.purl("/requirements"), json={"references": "SPK-1", "title": "Old title"})
    data = _csv(
        [
            ["SPK-1", "Sign in", "", f'"{a_key}, {b_key}"'],
            ["SPK-2", "Reset", "https://jira.test/SPK-2", a_key],
            ["SPK-3", "", "", "SPARK-TC-999"],
        ],
        ["Key", "Summary", "URL", "Test cases"],
    )
    up = sp.upload(data, name="refs.csv", entity="requirement")
    assert up["sheets"][0]["suggested_mapping"] == {
        "Key": "reference",
        "Summary": "title",
        "URL": "url",
        "Test cases": "cases",
    }
    t = sp.validate(up)
    c = t["summary"]["counts"]
    assert (c["create"], c["update"], c["error"], c["links_to_add"]) == (1, 1, 1, 3)
    assert t["errors"][0]["code"] == "unknown_case"
    t = sp.validate(up, options={"skip_error_rows": True})
    sp.commit(up)
    done = sp.admin.get(f"/api/v1/data-transfers/{up['transfer_id']}").json()
    assert done["summary"]["result"]["links_added"] == 3
    refs = {r["reference"]: r for r in sp.admin.get(sp.purl("/requirements")).json()["items"]}
    assert (refs["SPK-1"]["title"], refs["SPK-1"]["case_count"]) == ("Sign in", 2)
    assert refs["SPK-2"]["url"] == "https://jira.test/SPK-2"
    r = sp.admin.post(sp.purl("/exports"), json={"entity": "requirement", "format": "csv"})
    assert r.status_code == 200
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Reference,Title,Link,Linked cases"
    assert lines[1] == f'SPK-1,Sign in,,"{a_key}, {b_key}"'
    del a_id, b_id


def test_us_151_mapping_templates(world: World) -> None:
    sp = Imp(world)
    body = {"entity": "test_case", "name": "Jira export", "mapping": {"columns": {"Summary": "title"}}}
    r = sp.admin.post(sp.purl("/import-mappings"), json=body)
    assert r.status_code == 201, r.text
    again = sp.admin.post(
        sp.purl("/import-mappings"), json={**body, "name": "jira EXPORT", "mapping": {"columns": {}}}
    )
    assert again.json()["id"] == r.json()["id"], "same name replaces"
    listed = sp.admin.get(sp.purl("/import-mappings"), params={"entity": "test_case"}).json()
    assert [(t["name"], t["mapping"]) for t in listed] == [("Jira export", {"columns": {}})]
    assert sp.admin.delete(f"/api/v1/import-mappings/{r.json()['id']}").status_code == 204
    assert sp.admin.get(sp.purl("/import-mappings")).json() == []


@pytest.mark.timing
def test_nfr_perf_06_import_5000_cases_with_20000_steps(world: World, clean_jobs: None) -> None:
    """NFR-PERF-06 / P5: 5,000 cases and 20,000 steps import in under 2 minutes (dry run + commit)."""
    import time

    sp = Imp(world)
    rows: list[list[Any]] = []
    for i in range(5000):
        rows.append(
            ["", f"Generated case {i}", f"Area {i % 20}/Module {i % 7}", "medium", "Step 1", "OK", ""]
        )
        rows += [["", "", "", "", f"Step {n}", "OK", ""] for n in range(2, 5)]
    up = sp.upload(_xlsx(rows), name="big.xlsx")
    started = time.perf_counter()
    t = sp.validate(up)
    validated = time.perf_counter()
    assert t["summary"]["counts"]["create"] == 5000, t["summary"]
    sp.commit(up)
    done = time.perf_counter()
    result = sp.admin.get(f"/api/v1/data-transfers/{up['transfer_id']}").json()
    assert result["status"] == "committed", result["errors"]
    print(f"dry run {validated - started:.1f} s, commit {done - validated:.1f} s")
    assert done - started < 120
