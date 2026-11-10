"""Per-process, short-lived cache for dashboard figures that scan whole projects (M8c P3).

At 10× year one the quality dashboard's live "today" counters and its per-release block scan every run
of the project (about 2.5 s and 1 s). Each API process keeps such results for `ttl` seconds, so the
trend's last point and the release table may be up to five minutes old; everything else stays live.
Within one database session a dashboard also reuses coverage rows and status counts it already read;
the session forgets them as soon as it flushes a write.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from time import monotonic
from typing import Final, TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session

T = TypeVar("T")
MAX_ENTRIES: Final = 1000
_entries: dict[Hashable, tuple[float, object]] = {}
_lock = threading.Lock()


def cached(key: Hashable, ttl: float, compute: Callable[[], T]) -> T:
    now = monotonic()
    with _lock:
        hit = _entries.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]  # type: ignore[return-value]
    value = compute()
    with _lock:
        if len(_entries) >= MAX_ENTRIES:
            _entries.clear()
        _entries[key] = (now, value)
    return value


SESSION_MEMOS: Final = ("coverage_rows", "status_counts")


@event.listens_for(Session, "after_flush")
def _forget_session_memos(session: Session, _ctx: object) -> None:
    """Figures remembered for a session (coverage rows, status counts) are dropped once it writes."""
    for name in SESSION_MEMOS:
        session.info.pop(name, None)


def clear() -> None:
    with _lock:
        _entries.clear()
