"""BR-23 / TCMS-111 property test (docs/04 §7, docs/08 §6.3): the coverage SQL in `reporting.coverage` agrees
with a plain-Python reading of docs/02 §10.5 on random cases, references, cycles and attempts."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tcms.requirements import rules
from tests.api.test_execution import Space
from tests.world import World

pytestmark = pytest.mark.integration

STATUSES = ("passed", "failed", "blocked", "skipped", "not_applicable")

scenario = st.fixed_dictionaries(
    {
        "cases": st.integers(min_value=1, max_value=4),
        "refs": st.lists(st.lists(st.integers(0, 3), max_size=3), min_size=1, max_size=4),
        "planned": st.lists(st.booleans(), min_size=4, max_size=4),
        "cycles": st.lists(
            st.fixed_dictionaries(
                {
                    "release": st.sampled_from([0, 1, None]),
                    "attempts": st.lists(
                        st.lists(st.sampled_from(STATUSES), max_size=2), min_size=4, max_size=4
                    ),
                }
            ),
            max_size=3,
        ),
    }
)


def _attempt(sp: Space, run_id: str, status: str) -> None:
    """A final attempt inserted directly (with the reason that blocked/skipped/N/A need, K2)."""
    from sqlalchemy import text

    from tcms.core import clock, ids

    now = clock.now()
    with sp.world.factory() as s:
        s.execute(
            text(
                "INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, state, status, "
                "source, executed_by, started_at, finished_at, environment_id, skipped_steps, reason) "
                "SELECT :id, :org, :p, :run, coalesce(max(attempt_no), 0) + 1, 'final', :status, 'manual', :by, "
                ":now, :now, :env, 0, :reason FROM test_results WHERE run_id = :run"
            ),
            {
                "id": str(ids.new_id()),
                "org": str(sp.org.id),
                "p": str(sp.pid),
                "run": run_id,
                "status": status,
                "by": str(sp.org.admin.id),
                "now": now,
                "env": sp.env_id,
                "reason": None if status in ("passed", "failed") else "oracle",
            },
        )
        s.commit()


def _oracle(data: dict[str, Any], release: int | None) -> dict[int, str]:
    """docs/02 §10.5 with the D3 scope rule, computed from the generated scenario."""
    n = data["cases"]
    latest: dict[int, str] = {}
    ran: set[int] = set()
    for cyc in data["cycles"]:
        if release is not None and cyc["release"] != release:
            continue
        for case in range(n):
            ran.add(case)
            for status in cyc["attempts"][case]:
                if status != "not_applicable":
                    latest[case] = status  # attempts are recorded in order; the last one is the latest
    out = {}
    for i, linked in enumerate(data["refs"]):
        cases = sorted({c for c in linked if c < n})
        in_scope = release is None or (release == 0 and data["planned"][i]) or any(c in ran for c in cases)
        if in_scope:
            out[i] = rules.status_in_release([latest.get(c) for c in cases])
    return out


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=scenario)
@pytest.mark.br("BR-23")
def test_br_23_coverage_sql_matches_the_python_oracle(world: World, data: dict[str, Any]) -> None:
    sp = Space(world)
    releases = [sp.admin.post(sp.purl("/releases"), json={"name": f"v{i}"}).json()["id"] for i in range(2)]
    cases = [str(sp.case(f"Oracle case {i}")[0]) for i in range(data["cases"])]
    for i, linked in enumerate(data["refs"]):
        ids_ = sorted({cases[c] for c in linked if c < len(cases)})
        ref = sp.admin.post(sp.purl("/requirements"), json={"references": f"R-{i}"}).json()["references"][0]
        if ids_:
            sp.admin.post(f"/api/v1/requirements/{ref['id']}/test-cases", json={"test_case_ids": ids_})
    plan = sp.admin.post(
        sp.purl("/test-plans"), json={"name": "Oracle plan", "type": "regression", "release_id": releases[0]}
    ).json()
    planned = " ".join(f"R-{i}" for i in range(len(data["refs"])) if data["planned"][i])
    if planned:
        sp.admin.post(f"/api/v1/test-plans/{plan['id']}/requirements", json={"references": planned})
    for n, cyc in enumerate(data["cycles"]):
        body: dict[str, Any] = {"name": f"Oracle cycle {n}", "selection": {"case_ids": cases}}
        if cyc["release"] is not None:
            body["release_id"] = releases[cyc["release"]]
        created = sp.create_cycle(**body)["cycle"]
        runs = {r["test_case"]["id"]: r["id"] for r in sp.runs(created["id"])}
        for c, case_id in enumerate(cases):
            for status in cyc["attempts"][c]:
                _attempt(sp, runs[case_id], status)
    for release in (0, 1, None):
        params = {"release_id": releases[release]} if release is not None else {}
        got = {
            int(row["requirement"]["reference"].split("-")[1]): row["status_in_release"]
            for row in sp.admin.get(sp.purl("/traceability"), params=params).json()["rows"]
        }
        assert got == _oracle(data, release), (release, data)
