"""Demo data for local development (`make seed`), written only through module services.

Each milestone registers the steps it can seed with `step(...)`; steps run in registration order and
must be idempotent. Until a milestone adds steps, seeding reports that there is nothing to load.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedStep:
    name: str
    profiles: frozenset[str]
    run: Callable[[str], str]


_STEPS: list[SeedStep] = []


def step(name: str, *, profiles: tuple[str, ...]) -> Callable[[Callable[[str], str]], Callable[[str], str]]:
    def register(fn: Callable[[str], str]) -> Callable[[str], str]:
        _STEPS.append(SeedStep(name, frozenset(profiles), fn))
        return fn

    return register


def run(profile: str) -> Iterator[str]:
    from tcms.seed import steps  # noqa: F401 — registers the available steps

    selected = [s for s in _STEPS if profile in s.profiles]
    if not selected:
        yield f"seed[{profile}]: no seed steps are registered yet (system roles are created by the migration)"
        return
    for s in selected:
        yield f"seed[{profile}] {s.name}: {s.run(profile)}"
