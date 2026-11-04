"""In-process domain events (docs/03 §5.4).

Handlers subscribed here run inside the producing transaction (consistency rules). Side effects
(email, integrations) must not run here: handlers enqueue jobs on the UnitOfWork instead.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from tcms.core.uow import UnitOfWork


@dataclass(frozen=True)
class DomainEvent:
    """Base class for domain events (frozen dataclasses)."""


E = TypeVar("E", bound=DomainEvent)
Handler = Callable[["UnitOfWork", Any], None]

_handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)


def subscribe(
    event_type: type[E],
) -> Callable[[Callable[[UnitOfWork, E], None]], Callable[[UnitOfWork, E], None]]:
    def register(fn: Callable[[UnitOfWork, E], None]) -> Callable[[UnitOfWork, E], None]:
        if fn not in _handlers[event_type]:
            _handlers[event_type].append(fn)
        return fn

    return register


def handlers_for(event: DomainEvent) -> list[Handler]:
    return list(_handlers.get(type(event), ()))
