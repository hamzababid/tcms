"""Sorting and filtering allow-lists (docs/06 §2.5, §2.6)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, Date, Integer, MetaData, Table, Text
from sqlalchemy.dialects import postgresql

from tcms.core.errors import InvalidFilter, InvalidSort
from tcms.core.pagination import FilterField, PageParams, parse_filters, parse_sort

t = Table(
    "things",
    MetaData(),
    Column("key", Text),
    Column("status", Text),
    Column("n", Integer),
    Column("due", Date),
)
SORTS = {"key": t.c.key, "n": t.c.n}
FILTERS = {
    "status": FilterField(t.c.status, kind="enum", choices=frozenset({"passed", "failed", "blocked"})),
    "n": FilterField(t.c.n, kind="int"),
    "due": FilterField(t.c.due, kind="date"),
    "key": FilterField(t.c.key),
}


def sql(clause: object) -> str:
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]


def test_page_params_limits() -> None:
    assert PageParams().page_size == 50
    assert PageParams(page=3, page_size=20).offset == 40
    with pytest.raises(ValidationError):
        PageParams(page_size=201)
    with pytest.raises(ValidationError):
        PageParams(page=0)


def test_sort_parsing() -> None:
    clauses = parse_sort("-n,key", SORTS, default="key")
    assert [sql(c) for c in clauses] == ["things.n DESC", "things.key ASC"]
    assert [sql(c) for c in parse_sort(None, SORTS, default="-key")] == ["things.key DESC"]


def test_sort_rejects_unknown_and_too_many() -> None:
    with pytest.raises(InvalidSort):
        parse_sort("password", SORTS, default="key")
    with pytest.raises(InvalidSort):
        parse_sort("key,n,key,n", SORTS, default="key")


def test_filter_equality_and_or_values() -> None:
    (c,) = parse_filters({"status": "failed,blocked"}, FILTERS)
    assert sql(c) == "things.status = 'failed' OR things.status = 'blocked'"


def test_filter_operators() -> None:
    conds = parse_filters(
        {
            "n__gte": "3",
            "due__lte": "2026-11-10",
            "key__contains": "TC",
            "key__isnull": "false",
            "n__ne": "5",
        },
        FILTERS,
    )
    assert [sql(c) for c in conds] == [
        "things.n >= 3",
        "things.due <= '2026-11-10'",
        "things.key ILIKE '%%' || 'TC' || '%%' ESCAPE '/'",
        "things.key IS NOT NULL",
        "things.n != 5",
    ]


def test_contains_escapes_wildcards() -> None:
    (c,) = parse_filters({"key__contains": "50%_"}, FILTERS)
    assert "'50/%%/_'" in sql(c)  # % doubled only by the literal renderer


def test_reserved_params_are_ignored() -> None:
    assert parse_filters({"page": "2", "page_size": "10", "sort": "key", "q": "x"}, FILTERS) == []


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": "1"},
        {"status": "nope"},
        {"n": "abc"},
        {"due": "yesterday"},
        {"n__like": "1"},
        {"status": ","},
    ],
)
def test_filter_rejects_invalid(params: dict[str, str]) -> None:
    with pytest.raises(InvalidFilter):
        parse_filters(params, FILTERS)
