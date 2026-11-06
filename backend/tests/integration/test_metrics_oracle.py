"""BR-24 / TCMS-113/114 property test (docs/08 §6.4): the execution summary computed by
`reporting.queries` agrees with a plain-Python reading of docs/02 §11.2 on random cycles, runs,
statuses and superseded runs, for the release, a single cycle and the whole project."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from tcms.core import clock, ids
from tests.api.test_execution import Space
from tests.world import World

pytestmark = pytest.mark.integration

STATUSES = ("passed", "failed", "blocked", "skipped", "not_applicable")

scenario = st.fixed_dictionaries(
    {
        "cases": st.integers(min_value=1, max_value=4),
        "cycles": st.lists(
            st.fixed_dictionaries(
                {
                    "release": st.booleans(),
                    "runs": st.lists(
                        st.fixed_dictionaries(
                            {
                                "attempts": st.lists(st.sampled_from(STATUSES), max_size=2),
                                "superseded": st.booleans(),
                            }
                        ),
                        min_size=4,
                        max_size=4,
                    ),
                }
            ),
            min_size=1,
            max_size=3,
        ),
    }
)


def _record(sp: Space, run_id: str, statuses: list[str], superseded_by: str | None) -> None:
    now = clock.now()
    with sp.world.factory() as s:
        last = None
        for st_ in statuses:
            s.execute(
                text(
                    "INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, state, status,"
                    " source, executed_by, started_at, finished_at, environment_id, skipped_steps, reason)"
                    " SELECT :id, :org, :p, :run, coalesce(max(attempt_no), 0) + 1, 'final', :status, 'manual', :by,"
                    " :now, :now, :env, 0, :reason FROM test_results WHERE run_id = :run"
                ),
                {
                    "id": (last := str(ids.new_id())), "org": str(sp.org.id), "p": str(sp.pid), "run": run_id,
                    "status": st_, "by": str(sp.org.admin.id), "now": now, "env": sp.env_id,
                    "reason": None if st_ in ("passed", "failed") else "oracle",
                },
            )  # fmt: skip
        if last:
            s.execute(
                text("UPDATE test_runs SET latest_result_id = :r, status = :st WHERE id = :run"),
                {"r": last, "st": statuses[-1], "run": run_id},
            )
        if superseded_by:
            s.execute(
                text("UPDATE test_runs SET superseded_by_run_id = :by, superseded_at = :now WHERE id = :run"),
                {"by": superseded_by, "now": now, "run": run_id},
            )
        s.commit()


def _oracle(runs: list[tuple[bool, str, bool]]) -> dict[str, Any]:
    """docs/02 §11.2 over (in scope?, status, superseded?) triples."""
    live = [st_ for in_scope, st_, sup in runs if in_scope and not sup]
    n = {s: live.count(s) for s in ("passed", "failed", "blocked", "skipped", "not_applicable", "not_run")}
    applicable = len(live) - n["not_applicable"]
    executed = n["passed"] + n["failed"] + n["blocked"]

    def rate(a: int, b: int) -> dict[str, Any]:
        return {"numerator": a, "denominator": b, "value": None if b == 0 else a / b}

    return {
        "total": len(live),
        "applicable": applicable,
        "executed": executed,
        "failed": n["failed"],
        "execution_progress": rate(executed, applicable),
        "pass_rate": rate(n["passed"], executed),
        "pass_rate_applicable": rate(n["passed"], applicable),
        "blocked_rate": rate(n["blocked"], applicable),
    }


def _pick(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "total",
        "applicable",
        "executed",
        "failed",
        "execution_progress",
        "pass_rate",
        "pass_rate_applicable",
        "blocked_rate",
    )
    return {k: summary[k] for k in keys}


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=scenario)
@pytest.mark.br("BR-24")
def test_br_24_execution_summary_sql_matches_the_python_oracle(world: World, data: dict[str, Any]) -> None:
    sp = Space(world)
    release = sp.admin.post(sp.purl("/releases"), json={"name": "v1"}).json()["id"]
    cases = [str(sp.case(f"Oracle case {i}")[0]) for i in range(data["cases"])]
    facts: list[tuple[str, bool, str, bool]] = []  # (cycle id, in release, status, superseded)
    for n, cyc in enumerate(data["cycles"]):
        body: dict[str, Any] = {"name": f"Oracle cycle {n}", "selection": {"case_ids": cases}}
        if cyc["release"]:
            body["release_id"] = release
        created = sp.create_cycle(**body)["cycle"]
        runs = [r["id"] for r in sp.runs(created["id"])]
        for i, run_id in enumerate(runs):
            spec = cyc["runs"][i]
            # A superseded run points at another run of the same cycle (its replacement).
            other = next((r for r in runs if r != run_id), None)
            sup = bool(spec["superseded"] and other)
            _record(sp, run_id, spec["attempts"], other if sup else None)
            status = spec["attempts"][-1] if spec["attempts"] else "not_run"
            facts.append((created["id"], bool(cyc["release"]), status, sup))
    got = sp.admin.get(sp.purl("/execution-summary"), params={"release_id": release}).json()
    assert _pick(got) == _oracle([(rel, s, sup) for _, rel, s, sup in facts]), data
    everything = sp.admin.get(sp.purl("/execution-summary")).json()
    assert _pick(everything) == _oracle([(True, s, sup) for _, _, s, sup in facts])
    first = facts[0][0]
    one = sp.admin.get(sp.purl("/execution-summary"), params={"cycle_ids": first}).json()
    assert _pick(one) == _oracle([(c == first, s, sup) for c, _, s, sup in facts])
    assert _pick(sp.cycle(first)["summary"]) == _pick(one), "the cycle page and reporting agree"
