"""Optimistic concurrency (BR-25, docs/06 §2.7)."""

from __future__ import annotations

from typing import Any

from tcms.core.errors import RowVersionRequired, StaleRowVersion


def check_row_version(current: int, supplied: int | None, *, current_repr: Any = None) -> None:
    if supplied is None:
        raise RowVersionRequired()
    if supplied != current:
        raise StaleRowVersion(current_row_version=current, current=current_repr)
