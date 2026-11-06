"""Public read functions of the testdesign module (routers and other modules)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.enums import AutomationStatus, CaseStatus, CaseType, PriorityLevel
from tcms.core.errors import NotFound
from tcms.core.pagination import FilterField, PageParams, paginate, parse_filters, parse_sort
from tcms.testdesign import repository as repo
from tcms.testdesign import rules
from tcms.testdesign.models import Folder, Tag, TestCase, TestCaseTag, TestCaseVersion

# -- folders --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FolderNode:
    id: UUID
    parent_id: UUID | None
    name: str
    description: str | None
    position: int
    depth: int
    case_count: int
    total_count: int
    archived: bool
    row_version: int


def folder_tree(s: Session, ctx: AccessContext, *, include_archived: bool) -> list[FolderNode]:
    """Counts include descendants (docs/02 §5.1); archived folders hide their subtree unless requested."""
    folders = repo.folders(s, ctx)
    totals: dict[UUID, int] = {f.id: 0 for f in folders}
    by_id = {f.id: f for f in folders}
    for f in folders:
        for segment in f.path.strip("/").split("/"):
            ancestor = UUID(segment)
            if ancestor in totals:
                totals[ancestor] += f.case_count
    archived_ids = {f.id for f in folders if f.archived_at is not None}

    def hidden(f: Folder) -> bool:
        return any(UUID(seg) in archived_ids for seg in f.path.strip("/").split("/"))

    return (
        [
            FolderNode(
                f.id,
                f.parent_id,
                f.name,
                f.description,
                f.position,
                f.depth,
                f.case_count,
                totals[f.id],
                f.archived_at is not None,
                f.row_version,
            )
            for f in folders
            if include_archived or not hidden(f)
        ]
        if by_id
        else []
    )


def folder_path_names(s: Session, ctx: AccessContext, folder_id: UUID) -> list[str]:
    f = repo.folder(s, ctx, folder_id)
    if f is None:
        return []
    ids = [UUID(x) for x in f.path.strip("/").split("/")]
    names = {x.id: x.name for x in s.execute(select(Folder).where(Folder.id.in_(ids))).scalars()}
    return [names[i] for i in ids if i in names]


# -- case list ------------------------------------------------------------------------------------

CASE_FILTERS: Mapping[str, FilterField] = {
    "status": FilterField(TestCase.status, kind="enum", choices=frozenset(s.value for s in CaseStatus)),
    "type": FilterField(TestCase.type, kind="enum", choices=frozenset(t.value for t in CaseType)),
    "priority": FilterField(
        TestCase.priority, kind="enum", choices=frozenset(p.value for p in PriorityLevel)
    ),
    "owner_id": FilterField(TestCase.owner_id, kind="uuid"),
    "reviewer_id": FilterField(TestCase.reviewer_id, kind="uuid"),
    "automation_status": FilterField(
        TestCase.automation_status, kind="enum", choices=frozenset(a.value for a in AutomationStatus)
    ),
    "updated_at": FilterField(TestCase.updated_at, kind="datetime", operators=frozenset({"gte", "lte"})),
    "created_at": FilterField(TestCase.created_at, kind="datetime", operators=frozenset({"gte", "lte"})),
}
CASE_SORTS: Mapping[str, ColumnElement[Any]] = {
    "key": TestCase.key_num,  # type: ignore[dict-item]
    "title": func.lower(TestCase.title),
    "priority": TestCase.priority,  # type: ignore[dict-item]
    "status": TestCase.status,  # type: ignore[dict-item]
    "updated_at": TestCase.updated_at,  # type: ignore[dict-item]
    "created_at": TestCase.created_at,  # type: ignore[dict-item]
}
SPECIAL_PARAMS = ("folder_id", "include_subfolders", "tag", "include_archived")
KEY_RE = re.compile(r"^(?:([A-Z][A-Z0-9]{1,9})-TC-|TC-)?(\d+)$", re.I)


def case_list_query(s: Session, ctx: AccessContext, params: Mapping[str, str]) -> Select[Any]:
    """Filters of docs/06 §4.4 (operators per §2.6). Archived cases are hidden unless asked for."""
    stmt = repo.case_list_stmt(ctx)
    conditions = parse_filters(params, CASE_FILTERS, extra_allowed=SPECIAL_PARAMS)
    if conditions:
        stmt = stmt.where(*conditions)
    if "status" not in params and params.get("include_archived") != "true":
        stmt = stmt.where(TestCase.status != CaseStatus.archived)
    folder_id = params.get("folder_id")
    if folder_id:
        try:
            fid = UUID(folder_id)
        except ValueError as exc:
            from tcms.core.errors import InvalidFilter

            raise InvalidFilter("Invalid folder_id") from exc
        ids = (
            repo.folder_ids_under(s, ctx, fid)
            if params.get("include_subfolders", "true") != "false"
            else [fid]
        )
        stmt = stmt.where(TestCase.folder_id.in_(ids or [fid]))
    tag = params.get("tag")
    if tag:
        names = [t.strip().lower() for t in tag.split(",") if t.strip()]
        stmt = stmt.where(
            TestCase.id.in_(
                select(TestCaseTag.test_case_id)
                .join(Tag, Tag.id == TestCaseTag.tag_id)
                .where(Tag.project_id == ctx.pid, Tag.name.in_(names))
            )
        )
    q = (params.get("q") or "").strip()
    if q:
        m = KEY_RE.match(q)
        if m and (m.group(1) is None or m.group(1).upper() == _project_key(s, ctx)):
            stmt = stmt.where(TestCase.key_num == int(m.group(2)))
        else:
            ts = func.plainto_tsquery("simple", q)
            stmt = stmt.where(
                or_(TestCase.search_vector.op("@@")(ts), TestCase.title.icontains(q, autoescape=True))
            )
    return stmt


def _project_key(s: Session, ctx: AccessContext) -> str:
    from tcms.workspace import queries as wq

    p = wq.project_ref(s, ctx.principal.organization_id, ctx.pid)
    return p.key if p else ""


@dataclass(frozen=True)
class CaseSummary:
    id: UUID
    key: str
    title: str
    folder_id: UUID
    type: str
    priority: str
    status: str
    format: str
    owner_id: UUID
    reviewer_id: UUID | None
    automation_status: str
    latest_version_no: int
    approved_version_no: int | None
    tags: list[str]
    updated_at: datetime
    row_version: int


def _approved_numbers(s: Session, version_ids: list[UUID]) -> dict[UUID, int]:
    if not version_ids:
        return {}
    return dict(
        s.execute(
            select(TestCaseVersion.id, TestCaseVersion.version_no).where(TestCaseVersion.id.in_(version_ids))
        ).all()
    )


def summaries(s: Session, cases: list[TestCase]) -> list[CaseSummary]:
    tags = repo.tag_names_of(s, [c.id for c in cases])
    approved = _approved_numbers(s, [c.approved_version_id for c in cases if c.approved_version_id])
    return [
        CaseSummary(
            c.id,
            c.key,
            c.title,
            c.folder_id,
            c.type.value,
            c.priority.value,
            c.status.value,
            c.format.value,
            c.owner_id,
            c.reviewer_id,
            c.automation_status.value,
            c.latest_version_no,
            approved.get(c.approved_version_id) if c.approved_version_id else None,
            tags[c.id],
            c.updated_at,
            c.row_version,
        )
        for c in cases
    ]


def list_cases(
    s: Session, ctx: AccessContext, params: Mapping[str, str], page: PageParams
) -> tuple[list[CaseSummary], int]:
    stmt = case_list_query(s, ctx, params).order_by(
        *parse_sort(params.get("sort"), CASE_SORTS, default="key")
    )
    rows, total = paginate(s, stmt, page)
    return summaries(s, [r[0] for r in rows]), total


def matching_case_ids(s: Session, ctx: AccessContext, params: Mapping[str, str], limit: int) -> list[UUID]:
    stmt = (
        case_list_query(s, ctx, params)
        .with_only_columns(TestCase.id)
        .order_by(TestCase.key_num)
        .limit(limit + 1)
    )
    return list(s.execute(stmt).scalars())


# -- case detail ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class StepView:
    id: UUID
    position: int
    action: str
    expected_result: str | None
    data: str | None


@dataclass(frozen=True)
class VersionView:
    id: UUID
    version_no: int
    format: str
    title: str
    description: str | None
    preconditions: str | None
    test_data: str | None
    expected_result: str | None
    postconditions: str | None
    text_body: str | None
    change_note: str | None
    created_by: UUID
    created_at: datetime
    submitted_by: UUID | None
    submitted_at: datetime | None
    approval_mode: str | None
    approved_by: UUID | None
    approved_at: datetime | None
    steps: list[StepView]


def version_view(s: Session, v: TestCaseVersion) -> VersionView:
    steps = repo.steps_of(s, [v.id])[v.id]
    return VersionView(
        v.id,
        v.version_no,
        v.format.value,
        v.title,
        v.description,
        v.preconditions,
        v.test_data,
        v.expected_result,
        v.postconditions,
        v.text_body,
        v.change_note,
        v.created_by,
        v.created_at,
        v.submitted_by,
        v.submitted_at,
        v.approval_mode.value if v.approval_mode else None,
        v.approved_by,
        v.approved_at,
        [StepView(st.id, st.position, st.action, st.expected_result, st.data) for st in steps],
    )


@dataclass(frozen=True)
class LinkView:
    case_id: UUID
    key: str
    title: str
    status: str
    link_type: str
    direction: str  # "related" | "duplicated_from" (this case is a copy) | "duplicated_to"


@dataclass(frozen=True)
class CaseDetail:
    case: TestCase
    summary: CaseSummary
    folder_path: list[str]
    automation_keys: list[str]
    version: VersionView
    links: list[LinkView]
    title_exists_in_folder: bool


def case_detail(
    s: Session, ctx: AccessContext, case_id: UUID, *, version_no: int | None = None
) -> CaseDetail:
    case = repo.case_(s, ctx, case_id)
    if case is None:
        raise NotFound()
    if version_no is None:
        v = repo.version(s, ctx, case.latest_version_id) if case.latest_version_id else None
    else:
        v = repo.version_by_no(s, ctx, case.id, version_no)
    if v is None:
        raise NotFound(f"Version {version_no} not found")
    links = []
    for row in repo.links_of(s, ctx, case.id):
        other_id = row.target_case_id if row.source_case_id == case.id else row.source_case_id
        other = repo.case_(s, ctx, other_id)
        if other is None:
            continue
        direction = (
            "related"
            if row.link_type.value == "related"
            else ("duplicated_from" if row.source_case_id == case.id else "duplicated_to")
        )
        links.append(
            LinkView(other.id, other.key, other.title, other.status.value, row.link_type.value, direction)
        )
    return CaseDetail(
        case=case,
        summary=summaries(s, [case])[0],
        folder_path=folder_path_names(s, ctx, case.folder_id),
        automation_keys=repo.automation_keys_of(s, [case.id])[case.id],
        version=version_view(s, v),
        links=links,
        title_exists_in_folder=repo.title_exists_in_folder(
            s, ctx, case.folder_id, case.title, exclude=case.id
        ),
    )


def case_by_key(s: Session, ctx: AccessContext, key: str) -> TestCase | None:
    """`SPARK-TC-12`, `TC-12` or `12` within the project (docs/02 §12)."""
    m = KEY_RE.match(key.strip())
    if not m or (m.group(1) and m.group(1).upper() != _project_key(s, ctx)):
        return None
    return repo.case_by_number(s, ctx, int(m.group(2)))


def versions(s: Session, ctx: AccessContext, case_id: UUID) -> list[TestCaseVersion]:
    return repo.versions(s, ctx, case_id)


@dataclass(frozen=True)
class Comparison:
    from_version: int
    to_version: int
    fields: list[rules.FieldDiff]
    steps: list[rules.StepDiff]


def compare(s: Session, ctx: AccessContext, case_id: UUID, a: int, b: int) -> Comparison:
    va, vb = repo.version_by_no(s, ctx, case_id, a), repo.version_by_no(s, ctx, case_id, b)
    if va is None or vb is None:
        raise NotFound("Version not found")
    fields, steps = rules.compare(_content(s, va), _content(s, vb))
    return Comparison(a, b, fields, steps)


def _content(s: Session, v: TestCaseVersion) -> rules.Content:
    steps = repo.steps_of(s, [v.id])[v.id]
    return rules.Content(
        format=v.format,
        title=v.title,
        description=v.description,
        preconditions=v.preconditions,
        test_data=v.test_data,
        expected_result=v.expected_result,
        postconditions=v.postconditions,
        text_body=v.text_body,
        steps=tuple(rules.StepContent(st.action, st.expected_result, st.data) for st in steps),
    )


def tags(s: Session, ctx: AccessContext) -> list[tuple[Tag, int]]:
    return repo.tags(s, ctx)


def owning_project_of_case(s: Session, case_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(TestCase.organization_id, TestCase.project_id).where(TestCase.id == case_id)
    ).first()
    return (row[0], row[1]) if row else None


def owning_project_of_folder(s: Session, folder_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(select(Folder.organization_id, Folder.project_id).where(Folder.id == folder_id)).first()
    return (row[0], row[1]) if row else None


def owning_project_of_tag(s: Session, tag_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(select(Tag.organization_id, Tag.project_id).where(Tag.id == tag_id)).first()
    return (row[0], row[1]) if row else None


def owning_project_of_version(s: Session, version_id: UUID) -> tuple[UUID, UUID] | None:
    row = s.execute(
        select(TestCaseVersion.organization_id, TestCaseVersion.project_id).where(
            TestCaseVersion.id == version_id
        )
    ).first()
    return (row[0], row[1]) if row else None


def owning_project_of_step(s: Session, step_id: UUID) -> tuple[UUID, UUID] | None:
    from tcms.testdesign.models import TestCaseStep

    row = s.execute(
        select(TestCaseStep.organization_id, TestCaseStep.project_id).where(TestCaseStep.id == step_id)
    ).first()
    return (row[0], row[1]) if row else None


# -- case references for planning / execution (public cross-module read) --------------------------


@dataclass(frozen=True)
class CaseRef:
    """What planning and execution need to know about a case without touching its private repo."""

    id: UUID
    key: str
    key_num: int
    title: str
    folder_id: UUID
    status: str
    priority: str
    latest_version_id: UUID | None
    approved_version_id: UUID | None


def _case_ref(c: TestCase) -> CaseRef:
    return CaseRef(
        c.id,
        c.key,
        c.key_num,
        c.title,
        c.folder_id,
        c.status.value,
        c.priority.value,
        c.latest_version_id,
        c.approved_version_id,
    )


PRIORITY_RANK: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def case_columns(ctx: AccessContext) -> Any:
    """A project-scoped subquery of case columns other modules may join to (read-only interface,
    docs/03 §5.2): `id, key, key_num, title, priority, priority_rank, folder_id, status`."""
    from sqlalchemy import case as sql_case

    rank = sql_case(
        *((TestCase.priority == p, r) for p, r in PRIORITY_RANK.items()), else_=len(PRIORITY_RANK)
    )
    return (
        select(
            TestCase.id.label("id"),
            TestCase.key.label("key"),
            TestCase.key_num.label("key_num"),
            TestCase.title.label("title"),
            TestCase.priority.label("priority"),
            rank.label("priority_rank"),
            TestCase.folder_id.label("folder_id"),
            TestCase.status.label("status"),
        )
        .where(TestCase.organization_id == ctx.principal.organization_id, TestCase.project_id == ctx.pid)
        .subquery("case_cols")
    )


def folder_order(s: Session, ctx: AccessContext) -> dict[UUID, int]:
    """Folder id → index in tree order (depth first, siblings by position, then name; docs/02 §7.1)."""
    folders = repo.folders(s, ctx)
    children: dict[UUID | None, list[Folder]] = {}
    for f in folders:
        children.setdefault(f.parent_id, []).append(f)
    for lst in children.values():
        lst.sort(key=lambda f: (f.position, f.name.lower()))
    order: dict[UUID, int] = {}

    def walk(parent: UUID | None) -> None:
        for f in children.get(parent, []):
            order[f.id] = len(order)
            walk(f.id)

    walk(None)
    return order


def folder_names(s: Session, ctx: AccessContext, folder_ids: list[UUID]) -> dict[UUID, str]:
    if not folder_ids:
        return {}
    rows = s.execute(
        select(Folder.id, Folder.name).where(
            Folder.organization_id == ctx.principal.organization_id,
            Folder.project_id == ctx.pid,
            Folder.id.in_(folder_ids),
        )
    ).all()
    return {i: n for i, n in rows}


def subtree_folder_ids(s: Session, ctx: AccessContext, folder_id: UUID) -> list[UUID]:
    """The folder and all of its descendants."""
    return repo.folder_ids_under(s, ctx, folder_id) or [folder_id]


def tagged_case_ids_stmt(ctx: AccessContext, tag_names: list[str]) -> Any:
    """Subselect of case ids carrying any of the tags (for joins in other modules)."""
    names = [t.strip().lower() for t in tag_names if t.strip()]
    return (
        select(TestCaseTag.test_case_id)
        .join(Tag, Tag.id == TestCaseTag.tag_id)
        .where(Tag.project_id == ctx.pid, Tag.name.in_(names))
    )


def search_case_ids_stmt(s: Session, ctx: AccessContext, q: str) -> Any:
    """Subselect of case ids matching a key (`SPARK-TC-12`, `TC-12`, `12`) or text, like the case list."""
    stmt = repo.case_list_stmt(ctx).with_only_columns(TestCase.id)
    m = KEY_RE.match(q.strip())
    if m and (m.group(1) is None or m.group(1).upper() == _project_key(s, ctx)):
        return stmt.where(TestCase.key_num == int(m.group(2)))
    ts = func.plainto_tsquery("simple", q)
    return stmt.where(or_(TestCase.search_vector.op("@@")(ts), TestCase.title.icontains(q, autoescape=True)))


def case_refs(s: Session, ctx: AccessContext, ids: list[UUID]) -> dict[UUID, CaseRef]:
    """Case eligibility info (status + pinned-version candidates), scoped to the project."""
    if not ids:
        return {}
    return {c.id: _case_ref(c) for c in repo.cases_by_ids(s, ctx, ids)}


def case_ids_in_folders(
    s: Session, ctx: AccessContext, folder_ids: list[UUID], *, include_subfolders: bool
) -> list[UUID]:
    """All non-archived case ids in the given folders (optionally their subtrees), in key order."""
    if not folder_ids:
        return []
    ids: list[UUID] = []
    for fid in folder_ids:
        ids.extend(repo.folder_ids_under(s, ctx, fid) if include_subfolders else [fid])
    stmt = (
        repo.case_list_stmt(ctx)
        .with_only_columns(TestCase.id)
        .where(TestCase.folder_id.in_(ids or folder_ids), TestCase.status != CaseStatus.archived)
        .order_by(TestCase.key_num)
    )
    return list(s.execute(stmt).scalars())


def version_numbers(s: Session, version_ids: list[UUID]) -> dict[UUID, int]:
    """Map version id → version_no (public; used by execution to label pinned run versions)."""
    if not version_ids:
        return {}
    return dict(
        s.execute(
            select(TestCaseVersion.id, TestCaseVersion.version_no).where(TestCaseVersion.id.in_(version_ids))
        ).all()
    )


def case_ids_with_tags(s: Session, ctx: AccessContext, tag_names: list[str]) -> list[UUID]:
    """Non-archived case ids carrying any of the given tags, in key order."""
    names = [t.strip().lower() for t in tag_names if t.strip()]
    if not names:
        return []
    stmt = (
        repo.case_list_stmt(ctx)
        .with_only_columns(TestCase.id)
        .where(
            TestCase.status != CaseStatus.archived,
            TestCase.id.in_(
                select(TestCaseTag.test_case_id)
                .join(Tag, Tag.id == TestCaseTag.tag_id)
                .where(Tag.project_id == ctx.pid, Tag.name.in_(names))
            ),
        )
        .order_by(TestCase.key_num)
    )
    return list(s.execute(stmt).scalars())


def version_view_by_id(s: Session, ctx: AccessContext, version_id: UUID) -> VersionView | None:
    """A specific (e.g. pinned) version's content, scoped to the project."""
    v = repo.version(s, ctx, version_id)
    return version_view(s, v) if v else None


@dataclass(frozen=True)
class ReviewItem:
    id: UUID
    project_id: UUID
    key: str
    title: str
    updated_at: datetime


def awaiting_review(
    s: Session, org_id: UUID, user_id: UUID, approve_project_ids: list[UUID], limit: int = 50
) -> list[ReviewItem]:
    """My Work › Awaiting my review (docs/02 §7.5): cases in review where I am the reviewer, or with no
    reviewer in projects where I may approve (docs/02 §2.7 recipients). Oldest first."""
    if not approve_project_ids:
        return []
    rows = s.execute(
        select(TestCase.id, TestCase.project_id, TestCase.key, TestCase.title, TestCase.updated_at)
        .where(
            TestCase.organization_id == org_id,
            TestCase.project_id.in_(approve_project_ids),
            TestCase.status == CaseStatus.in_review,
            or_(TestCase.reviewer_id == user_id, TestCase.reviewer_id.is_(None)),
        )
        .order_by(TestCase.updated_at, TestCase.key_num)
        .limit(limit)
    ).all()
    return [ReviewItem(*r) for r in rows]


def step_positions(s: Session, ctx: AccessContext, step_ids: list[UUID]) -> dict[UUID, int]:
    """Position of each pinned step (bug-link chips show "step n", docs/02 §8.2)."""
    from tcms.testdesign.models import TestCaseStep

    if not step_ids:
        return {}
    rows = s.execute(
        select(TestCaseStep.id, TestCaseStep.position).where(
            TestCaseStep.id.in_(step_ids),
            TestCaseStep.organization_id == ctx.principal.organization_id,
            TestCaseStep.project_id == ctx.pid,
        )
    ).all()
    return {r[0]: r[1] for r in rows}
