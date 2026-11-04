"""Pagination, sorting and filtering with allow-lists (docs/06 §2.4–2.6, docs/02 §2.6)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.orm import Session

from tcms.core.errors import FieldError, InvalidFilter, InvalidSort

T = TypeVar("T")

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
MAX_SORT_FIELDS = 3


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def paginate(session: Session, stmt: Select[Any], params: PageParams) -> tuple[list[Any], int]:
    """Run `stmt` for one page and return (rows, total)."""
    total = session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = list(session.execute(stmt.limit(params.page_size).offset(params.offset)).all())
    return rows, int(total)


# --- sorting -------------------------------------------------------------------------------------


def parse_sort(raw: str | None, allowed: Mapping[str, ColumnElement[Any]], default: str) -> list[Any]:
    """`-updated_at,key` → order_by clauses. Unknown field → 400 invalid_sort."""
    spec = raw if raw else default
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if len(parts) > MAX_SORT_FIELDS:
        raise InvalidSort(f"At most {MAX_SORT_FIELDS} sort fields are allowed")
    clauses: list[Any] = []
    for part in parts:
        desc = part.startswith("-")
        name = part[1:] if desc else part
        column = allowed.get(name)
        if column is None:
            raise InvalidSort(
                f"Cannot sort by '{name}'",
                errors=[FieldError("sort", "invalid_sort", f"Allowed: {', '.join(sorted(allowed))}")],
            )
        clauses.append(column.desc() if desc else column.asc())
    return clauses


# --- filtering -----------------------------------------------------------------------------------

OPERATORS = ("ne", "in", "gte", "lte", "contains", "isnull")


def _parse_bool(v: str) -> bool:
    if v.lower() in ("true", "1"):
        return True
    if v.lower() in ("false", "0"):
        return False
    raise ValueError(v)


_PARSERS: dict[str, Callable[[str], Any]] = {
    "str": str,
    "uuid": UUID,
    "int": int,
    "bool": _parse_bool,
    "date": date.fromisoformat,
    "datetime": lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
}


@dataclass(frozen=True)
class FilterField:
    column: ColumnElement[Any]
    kind: str = "str"  # str | uuid | int | bool | date | datetime | enum
    choices: frozenset[str] | None = None  # for kind == "enum"
    operators: frozenset[str] = frozenset(OPERATORS)

    def parse(self, name: str, raw: str) -> Any:
        if self.kind == "enum":
            if self.choices is not None and raw not in self.choices:
                raise InvalidFilter(
                    f"Invalid value '{raw}' for '{name}'",
                    errors=[FieldError(name, "invalid_value", f"Allowed: {', '.join(sorted(self.choices))}")],
                )
            return raw
        try:
            return _PARSERS[self.kind](raw)
        except (ValueError, KeyError) as exc:
            raise InvalidFilter(f"Invalid value '{raw}' for '{name}'") from exc


RESERVED_PARAMS = frozenset({"page", "page_size", "sort", "q", "include", "format"})


def parse_filters(
    params: Mapping[str, str], allowed: Mapping[str, FilterField], *, extra_allowed: Sequence[str] = ()
) -> list[ColumnElement[bool]]:
    """Translate query parameters into SQL conditions. Unknown fields → 400 invalid_filter."""
    conditions: list[ColumnElement[bool]] = []
    for key, raw in params.items():
        if key in RESERVED_PARAMS or key in extra_allowed:
            continue
        name, _, op = key.partition("__")
        field = allowed.get(name)
        if field is None or (op and op not in field.operators):
            raise InvalidFilter(
                f"Unknown filter '{key}'",
                errors=[FieldError(key, "invalid_filter", f"Allowed: {', '.join(sorted(allowed))}")],
            )
        col = field.column
        if op == "isnull":
            conditions.append(col.is_(None) if _parse_bool(raw) else col.is_not(None))
        elif op == "contains":
            conditions.append(col.ilike(f"%{raw}%"))
        elif op == "gte":
            conditions.append(col >= field.parse(name, raw))
        elif op == "lte":
            conditions.append(col <= field.parse(name, raw))
        elif op == "ne":
            conditions.append(col != field.parse(name, raw))
        else:  # equality or `in`; comma-separated values are OR-ed (docs/06 §2.6)
            values = [field.parse(name, v) for v in raw.split(",") if v != ""]
            if not values:
                raise InvalidFilter(f"Empty value for '{key}'")
            conditions.append(col == values[0] if len(values) == 1 else or_(*(col == v for v in values)))
    return conditions


def combine(conditions: Sequence[ColumnElement[bool]]) -> ColumnElement[bool] | None:
    return and_(*conditions) if conditions else None
