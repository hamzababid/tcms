"""Concurrency of attempts (docs/08 §10, TCMS-090, BR-07) and step-save latency (AC-EXE-09).

Each thread uses its own unit of work, like concurrent requests. The services are called directly so
the measurement is the transaction, not the test client.
"""

from __future__ import annotations

import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

import pytest

from tcms.core.context import AccessContext
from tcms.core.errors import DomainError
from tcms.core.permissions import PROJECT_PERMISSIONS
from tcms.core.uow import unit_of_work
from tcms.execution import service
from tests.world import World

pytestmark = pytest.mark.integration


def _setup(world: World, runs: int, steps: int = 2) -> tuple[AccessContext, list[UUID]]:
    org = world.org()
    pid = world.project(org, "CONC")
    folder = world.folder(org, pid, "F")
    ctx = world.ctx(org.id, org.admin.id, is_admin=True, project_id=pid, perms=PROJECT_PERMISSIONS)
    case_ids = [world.case(org, pid, folder, f"Concurrent {i}", steps=steps)[0] for i in range(runs)]
    with unit_of_work(world.factory) as uow:
        env = service.workspace_queries.environments(uow.session, org.id, pid, include_archived=False)[0]
        created = service.create_cycle(
            uow,
            ctx,
            service.CycleData(
                name="Concurrency", environment_id=env.id, selection=service.Selection(case_ids=case_ids)
            ),
        )
        cycle_id = created.cycle.id
    with unit_of_work(world.factory) as uow:
        run_ids = [r.id for r in service.repo.runs_in_cycle(uow.session, ctx, cycle_id)]
    return ctx, run_ids


def _draft(world: World, ctx: AccessContext, run_id: UUID) -> tuple[UUID, list[UUID]]:
    with unit_of_work(world.factory) as uow:
        res = service.start_attempt(uow, ctx, run_id).result
        steps = [r.step_id for r in service.repo.step_results(uow.session, res.id)]
        return res.id, steps


@pytest.mark.br("BR-06")
def test_tcms_090_concurrent_finalize_exactly_one_succeeds(world: World) -> None:
    ctx, (run_id,) = _setup(world, 1, steps=1)
    res_id, (step_id,) = _draft(world, ctx, run_id)
    with unit_of_work(world.factory) as uow:
        service.record_step(uow, ctx, res_id, step_id, fields={"status": "passed"})

    def finish(_: int) -> str:
        try:
            with unit_of_work(world.factory) as uow:
                service.finalize_attempt(uow, ctx, res_id, outcome=None, reason=None, duration_seconds=None)
            return "ok"
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(finish, range(20)))
    assert outcomes.count("ok") == 1, outcomes
    assert set(outcomes) == {"ok", "immutable_record"}


@pytest.mark.br("BR-07")
def test_br_07_concurrent_starts_make_one_draft(world: World) -> None:
    ctx, (run_id,) = _setup(world, 1, steps=1)

    def start(_: int) -> UUID:
        with unit_of_work(world.factory) as uow:
            return service.start_attempt(uow, ctx, run_id).result.id

    with ThreadPoolExecutor(max_workers=20) as pool:
        ids_ = set(pool.map(start, range(20)))
    assert len(ids_) == 1, "the same user gets the same draft back"


@pytest.mark.timing
def test_ac_exe_09_fifty_testers_save_steps_concurrently(world: World) -> None:
    """AC-EXE-09: 50 testers saving step results on different runs: no update lost, p95 < 200 ms.

    Load model of docs/08 §9 P2: 50 testers, 2 s think time between step saves, start times spread over
    the first think interval (a zero-think burst of 200 saves is not the scenario)."""
    ctx, run_ids = _setup(world, 50, steps=4)
    drafts = [_draft(world, ctx, r) for r in run_ids]
    think = 2.0
    offsets = random.Random(9).sample([think * k / 50 for k in range(50)], 50)

    def tester(i: int) -> list[float]:
        res_id, steps = drafts[i]
        timings = []
        time.sleep(offsets[i])
        for n, step_id in enumerate(steps):
            if n:
                time.sleep(think)
            t0 = time.perf_counter()
            with unit_of_work(world.factory) as uow:
                service.record_step(
                    uow, ctx, res_id, step_id, fields={"status": "passed", "comment": f"t{i} s{n}"}
                )
            timings.append(time.perf_counter() - t0)
        return timings

    with ThreadPoolExecutor(max_workers=50) as pool:
        samples = [t for lst in pool.map(tester, range(50)) for t in lst]
    p95 = statistics.quantiles(samples, n=20)[-1]
    with unit_of_work(world.factory) as uow:
        saved: list[Any] = [service.repo.step_results(uow.session, res_id) for res_id, _ in drafts]
    assert all(r.status.value == "passed" and r.comment for rows in saved for r in rows), "an update was lost"
    assert p95 < 0.2, f"p95 step save {p95 * 1000:.0f} ms"
