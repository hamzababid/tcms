"""M6 — global search (US-130, TCMS-118/119, AC-SRCH-01) and saved views (US-132, TCMS-120)."""

from __future__ import annotations

import statistics
import time
from typing import Any

import pytest

from tests.api.test_requirements import Req
from tests.world import World

pytestmark = pytest.mark.integration


def _groups(r: Any) -> dict[str, list[dict[str, Any]]]:
    assert r.status_code == 200, r.text
    return {g["type"]: g["items"] for g in r.json()["groups"]}


def test_ac_srch_01_tcms_118_search_by_key(world: World) -> None:
    sp = Req(world)
    case_id, key = sp.case("Login with valid credentials")
    number = key.split("-")[-1]
    for q in (key, f"TC-{number}", number):
        hits = _groups(sp.sana.get("/api/v1/search", params={"q": q, "project_id": str(sp.pid)}))
        assert hits["test_case"][0]["id"] == str(case_id), q
        assert hits["test_case"][0]["project"]["key"] == "SPARK"
    cyc = sp.create_cycle(name="Regression Cycle 01")["cycle"]
    hits = _groups(sp.sana.get("/api/v1/search", params={"q": cyc["key"], "project_id": str(sp.pid)}))
    assert hits["cycle"][0]["id"] == cyc["id"]
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Release plan", "type": "regression"}).json()
    hits = _groups(sp.sana.get("/api/v1/search", params={"q": plan["key"], "project_id": str(sp.pid)}))
    assert hits["plan"][0]["id"] == plan["id"]


def test_tcms_119_search_by_text_grouped(world: World) -> None:
    sp = Req(world)
    sp.case("Dashboard loads quickly")
    sp.add("DASH-1", title="Dashboard KPIs")
    sp.create_cycle(name="Dashboard smoke")
    world.folder(sp.org, sp.pid, "Dashboard")
    hits = _groups(sp.sana.get("/api/v1/search", params={"q": "dashboard", "project_id": str(sp.pid)}))
    assert {"test_case", "requirement", "cycle", "folder"} <= set(hits)
    assert hits["requirement"][0]["key"] == "DASH-1"
    only = _groups(
        sp.sana.get("/api/v1/search", params={"q": "dashboard", "project_id": str(sp.pid), "types": "folder"})
    )
    assert set(only) == {"folder"}
    everywhere = _groups(sp.sana.get("/api/v1/search", params={"q": "dashboard"}))
    assert "test_case" in everywhere, "no project: all my projects"
    other = Req(world, key="HELIOS")
    other.case("Dashboard elsewhere")
    stranger = world.login(world.user(sp.org, "Stranger"))
    assert _groups(stranger.get("/api/v1/search", params={"q": "dashboard"})) == {}
    assert stranger.get("/api/v1/search", params={"q": "x", "project_id": str(sp.pid)}).status_code == 404


@pytest.mark.timing
def test_tcms_119_search_is_fast(world: World) -> None:
    """< 500 ms p95 on the test stack (docs/02 §12, NFR-PERF-05) over 100 cases and references."""
    sp = Req(world)
    for i in range(100):
        sp.case(f"Meter reading import {i}")
    sp.add(" ".join(f"MTR-{i}" for i in range(100)))
    samples = []
    for q in ("meter", "MTR-5", "import 4", "TC-50", "reading"):
        for _ in range(4):
            t0 = time.perf_counter()
            assert (
                sp.sana.get("/api/v1/search", params={"q": q, "project_id": str(sp.pid)}).status_code == 200
            )
            samples.append(time.perf_counter() - t0)
    assert statistics.quantiles(samples, n=20)[-1] < 0.5


def test_tcms_120_saved_views_private_shared_and_defaults(world: World) -> None:
    sp = Req(world)
    url = sp.purl("/saved-views")
    body = {
        "entity_type": "test_case",
        "name": "My high",
        "definition": {"filters": {"priority": "high"}, "sort": "-updated_at", "columns": ["key", "title"]},
        "is_default": True,
    }
    mine = sp.sana.post(url, json=body)
    assert mine.status_code == 201, mine.text
    assert sp.sana.post(url, json=body).status_code == 409, "names are unique per owner and list"
    assert sp.sana.post(url, json={**body, "name": "Shared", "visibility": "project"}).status_code == 403
    shared = sp.bilal.post(
        url, json={**body, "name": "Team regression", "visibility": "project", "is_default": True}
    )
    assert shared.status_code == 201, shared.text
    listed = sp.sana.get(url, params={"entity_type": "test_case"}).json()
    assert [v["name"] for v in listed] == ["My high", "Team regression"], (
        "my default first, then the shared one"
    )
    assert listed[0]["mine"]
    assert not listed[1]["mine"]
    assert [v["name"] for v in sp.omar.get(url, params={"entity_type": "test_case"}).json()] == [
        "Team regression"
    ]
    second = sp.sana.post(url, json={**body, "name": "Another"}).json()
    names_default = [
        v["name"] for v in sp.sana.get(url, params={"entity_type": "test_case"}).json() if v["is_default"]
    ]
    assert names_default == ["Another", "Team regression"], "one private default per list"
    assert sp.sana.patch(f"/api/v1/saved-views/{shared.json()['id']}", json={"name": "x"}).status_code == 403
    r = sp.sana.patch(f"/api/v1/saved-views/{second['id']}", json={"name": "Renamed", "is_default": False})
    assert (r.status_code, r.json()["name"]) == (200, "Renamed")
    bad = sp.sana.post(url, json={**body, "name": "Bad", "entity_type": "nope"})
    assert bad.status_code == 422
    assert sp.sana.delete(f"/api/v1/saved-views/{second['id']}").status_code == 204
    assert sp.omar.delete(f"/api/v1/saved-views/{mine.json()['id']}").status_code == 404, (
        "private views are hidden"
    )


def test_l25_add_plan_cases_from_a_saved_view(world: World) -> None:
    sp = Req(world)
    a, _ = sp.case("Checkout with coupon")
    sp.case("Profile page")
    b, _ = sp.case("Checkout as guest")
    sp.sana.post(
        sp.purl("/requirements/link-cases"), json={"references": "SHOP-1", "test_case_ids": [str(b)]}
    )
    view = sp.bilal.post(
        sp.purl("/saved-views"),
        json={
            "entity_type": "test_case",
            "name": "Checkout",
            "visibility": "project",
            "definition": {"filters": {"q": "checkout"}},
        },
    ).json()
    plan = sp.admin.post(sp.purl("/test-plans"), json={"name": "Checkout plan", "type": "regression"}).json()
    r = sp.admin.post(f"/api/v1/test-plans/{plan['id']}/cases", json={"saved_view_id": view["id"]})
    assert (r.status_code, r.json()["added"]) == (200, 2), r.text
    linked = sp.bilal.post(
        sp.purl("/saved-views"),
        json={
            "entity_type": "test_case",
            "name": "With SHOP-1",
            "definition": {"filters": {"requirement": "SHOP-1"}},
        },
    ).json()
    plan2 = sp.admin.post(sp.purl("/test-plans"), json={"name": "Shop plan", "type": "regression"}).json()
    r = sp.bilal.post(f"/api/v1/test-plans/{plan2['id']}/cases", json={"saved_view_id": linked["id"]})
    assert r.json()["added"] == 1
    private = sp.sana.post(
        sp.purl("/saved-views"),
        json={"entity_type": "test_case", "name": "Mine", "definition": {"filters": {}}},
    ).json()
    assert (
        sp.admin.post(
            f"/api/v1/test-plans/{plan['id']}/cases", json={"saved_view_id": private["id"]}
        ).status_code
        == 422
    )
    assert a  # the first checkout case is part of the view
