"""Time the M7 dashboards, readiness and reports on the seeded SPARK project (M7 D16).

`tcms seed-timing` runs each endpoint function the API serves (same code path, no HTTP) five times as
SPARK's QA Manager and prints the median and worst wall-clock time. Used with `--profile large`.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Iterator
from typing import Any

from sqlalchemy import text

from tcms.core.config import get_settings
from tcms.core.db import app_engine, session_factory
from tcms.core.uow import unit_of_work


def run(repeat: int = 5) -> Iterator[str]:
    from tcms.api.v1 import reporting as api
    from tcms.api.v1 import requirements as req_api
    from tcms.reporting import reports
    from tcms.seed.steps import _spark_manager_ctx

    factory = session_factory(app_engine(get_settings()))
    with factory() as s:
        ctx = _spark_manager_ctx(s)
        assert ctx is not None, "seed SPARK first"
        rel = s.execute(
            text("SELECT id FROM releases WHERE project_id = :p AND status = 'active' ORDER BY name LIMIT 1"),
            {"p": ctx.pid},
        ).scalar_one()
        counts = s.execute(
            text(
                "SELECT (SELECT count(*) FROM test_cases WHERE project_id = :p),"
                " (SELECT count(*) FROM test_runs WHERE project_id = :p),"
                " (SELECT count(*) FROM test_results WHERE project_id = :p)"
            ),
            {"p": ctx.pid},
        ).one()
    yield f"SPARK: {counts[0]:,} cases, {counts[1]:,} runs, {counts[2]:,} attempts; active release {rel}"

    def filters(**kw: Any) -> Any:
        f = api._Filters.__new__(api._Filters)
        f.kw = {
            "release_id": None, "cycle_ids": None, "environment_id": None, "module_folder_id": None,
            "tester_id": None, "date_from": None, "date_to": None, **kw,
        }  # fmt: skip
        return f

    def report(name: str, **raw: str) -> Callable[[Any], Any]:
        def go(uow: Any) -> Any:
            rep = reports.REPORTS[name]
            f = api._report_filters(uow, ctx, rep, raw)
            return rep.rows(uow.session, ctx, f, 50, 0)

        return go

    cases: list[tuple[str, Callable[[Any], Any]]] = [
        (
            "Overview (manager dashboard), active release",
            lambda u: api.manager_dashboard(filters(release_id=rel), ctx, u),
        ),
        ("Overview (manager dashboard), whole project", lambda u: api.manager_dashboard(filters(), ctx, u)),
        ("Quality dashboard, 30 days", lambda u: api.quality_dashboard(None, None, None, ctx, u)),
        ("Release readiness", lambda u: api.release_readiness(rel, ctx, u)),
        ("Releases page (all releases)", lambda u: api.release_summaries(False, ctx, u)),
        ("Traceability, active release", lambda u: req_api.traceability(rel, None, False, None, ctx, u)),
        ("Report: cycle execution (page 1)", report("cycle-execution", release_id=str(rel))),
        ("Report: results history (page 1)", report("results-history")),
        ("Report: case inventory (page 1)", report("case-inventory")),
        ("Report: tester activity (page 1)", report("tester-activity")),
        ("Execution summary, project", lambda u: api.execution_summary(filters(), ctx, u)),
    ]
    for name, fn in cases:
        times = []
        for _ in range(repeat):
            with unit_of_work(factory) as uow:
                t0 = time.perf_counter()
                fn(uow)
                times.append((time.perf_counter() - t0) * 1000)
        yield f"{name}: median {statistics.median(times):.0f} ms, worst {max(times):.0f} ms"
