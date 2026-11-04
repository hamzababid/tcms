"""The only source of "now" (docs/04 §3.7). Tests freeze it with `frozen()`."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

_now: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def now() -> datetime:
    return _now()


@contextmanager
def frozen(at: datetime) -> Iterator[None]:
    """Freeze `now()` at a timezone-aware instant (test helper)."""
    if at.tzinfo is None:
        raise ValueError("frozen() needs a timezone-aware datetime")
    global _now
    previous = _now
    _now = lambda: at  # noqa: E731
    try:
        yield
    finally:
        _now = previous
