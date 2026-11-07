"""Requirement reference import and export (ADR-024, M8 D2): reference, title, link, linked case keys.

Import creates new references, updates the title and link of existing ones, and adds the listed case
links; it never removes links (a file lists what must be linked, not everything that is).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from tcms.core import references as R
from tcms.core.context import AccessContext
from tcms.core.uow import UnitOfWork
from tcms.imports import fields as F
from tcms.imports.cases import MAX_CASES, Problem
from tcms.requirements import queries as rq
from tcms.requirements import service as requirements
from tcms.testdesign import queries as td_queries

Action = Literal["create", "update", "unchanged", "error"]
MAX_REFS = MAX_CASES


@dataclass
class PlannedRef:
    row: int
    action: Action
    reference: str
    ref_id: UUID | None
    title: str | None  # None = keep
    url: str | None  # None = keep
    case_ids: list[UUID] = field(default_factory=list)  # links to add
    problems: list[Problem] = field(default_factory=list)


@dataclass
class RefPlan:
    refs: list[PlannedRef]
    file_problems: list[Problem]

    @property
    def counts(self) -> dict[str, int]:
        out = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
        for r in self.refs:
            out[r.action] += 1
        out["links_to_add"] = sum(len(r.case_ids) for r in self.refs if r.action != "error")
        return out

    @property
    def problems(self) -> list[Problem]:
        return self.file_problems + [p for r in self.refs for p in r.problems]

    def committable(self, skip_error_rows: bool) -> bool:
        if self.file_problems or not any(r.action in ("create", "update") for r in self.refs):
            return False
        return skip_error_rows or not any(r.action == "error" for r in self.refs)


def build_plan(
    uow: UnitOfWork,
    ctx: AccessContext,
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    mapping: dict[str, str],
) -> RefPlan:
    s = uow.session
    columns = {}
    for i, h in enumerate(header):
        f = mapping.get(h, F.IGNORE)
        if f and f not in columns:
            columns[f] = i
    if "reference" not in columns:
        return RefPlan([], [Problem(1, None, "field_required", "Map a column to Reference")])
    if len(rows) > MAX_REFS:
        return RefPlan([], [Problem(1, None, "too_many_rows", f"At most {MAX_REFS:,} references per file")])

    def get(row: Sequence[str], f: str) -> str:
        i = columns.get(f)
        return row[i].strip() if i is not None and i < len(row) else ""

    existing = {
        v.reference.upper(): v
        for v in rq.list_refs(s, ctx, q=None, linked=None, ref_ids=None, include_archived=True)
    }
    wanted_keys = sorted({k for r in rows for k in F.split_list(get(r, "cases"))})
    keys = (
        {key.upper(): cid for cid, key in td_queries.case_keys(s, ctx, keys=wanted_keys).items()}
        if wanted_keys
        else {}
    )
    linked = rq.linked_case_ids(s, ctx, [v.id for v in existing.values()])
    seen: dict[str, int] = {}
    out: list[PlannedRef] = []
    for n, row in enumerate(rows, start=2):
        if not any(c.strip() for c in row):
            continue
        ref = R.normalize_reference(get(row, "reference"))
        problems = []
        p = R.reference_problem(ref)
        if p:
            problems.append(Problem(n, "reference", p.code, p.message))
        elif ref.upper() in seen:
            problems.append(
                Problem(
                    n, "reference", "duplicate_key", f"{ref} appears again (first on row {seen[ref.upper()]})"
                )
            )
        seen.setdefault(ref.upper(), n)
        title = get(row, "title") if "title" in columns else None
        url = get(row, "url") if "url" in columns else None
        for prob in (R.title_problem(title), R.url_problem(url)):
            if prob:
                problems.append(Problem(n, prob.field, prob.code, prob.message))
        case_ids: list[UUID] = []
        for k in F.split_list(get(row, "cases")):
            cid = keys.get(k.upper())
            if cid is None:
                problems.append(Problem(n, "cases", "unknown_case", f"No case {k} in this project"))
            else:
                case_ids.append(cid)
        cur = existing.get(ref.upper())
        new_links = [c for c in dict.fromkeys(case_ids) if not cur or c not in linked.get(cur.id, set())]
        action: Action
        if problems:
            action = "error"
        elif cur is None:
            action = "create"
        elif (
            new_links
            or cur.archived
            or (title is not None and R.clean_title(title) != cur.title)
            or (url is not None and (url or None) != cur.url)
        ):
            action = "update"
        else:
            action = "unchanged"
        out.append(PlannedRef(n, action, ref, cur.id if cur else None, title, url, new_links, problems))
    return RefPlan(out, [])


def commit(uow: UnitOfWork, ctx: AccessContext, plan: RefPlan) -> dict[str, Any]:
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "links_added": 0}
    report: list[tuple[int, str, str, str]] = []
    for r in plan.refs:
        if r.action == "error":
            counts["skipped"] += 1
            report.append((r.row, "skipped", r.reference, "; ".join(p.message for p in r.problems)))
            continue
        if r.action == "unchanged":
            counts["unchanged"] += 1
            report.append((r.row, "unchanged", r.reference, ""))
            continue
        ensured = requirements.ensure_refs(uow, ctx, [r.reference], url=r.url or None, title=r.title or None)
        row = ensured.refs[0]
        if not ensured.created:
            fields: dict[str, str | None] = {}
            if r.title is not None:
                fields["title"] = r.title
            if r.url is not None:
                fields["url"] = r.url
            if fields:
                requirements.update_ref(uow, ctx, row.id, fields=fields)
        if r.case_ids:
            counts["links_added"] += requirements.link(uow, ctx, [row], r.case_ids)
        counts["created" if ensured.created else "updated"] += 1
        report.append(
            (
                r.row,
                "created" if ensured.created else "updated",
                row.reference,
                f"{len(r.case_ids)} links added",
            )
        )
    return {**counts, "report": report}


EXPORT_HEADER = [f.label for f in F.REF_FIELDS]


def export_rows(uow: UnitOfWork, ctx: AccessContext, *, include_archived: bool = False) -> list[list[str]]:
    s = uow.session
    views = rq.list_refs(s, ctx, q=None, linked=None, ref_ids=None, include_archived=include_archived)
    links = rq.linked_case_ids(s, ctx, [v.id for v in views])
    all_cases = sorted({c for ids in links.values() for c in ids})
    keys = td_queries.case_keys(s, ctx, ids=all_cases) if all_cases else {}
    return [
        [
            v.reference,
            v.title or "",
            v.url or "",
            ", ".join(sorted((keys[c] for c in links.get(v.id, ()) if c in keys), key=_natural)),
        ]
        for v in views
    ]


def _natural(key: str) -> tuple[str, int]:
    head, _, num = key.rpartition("-")
    return (head, int(num) if num.isdigit() else 0)
