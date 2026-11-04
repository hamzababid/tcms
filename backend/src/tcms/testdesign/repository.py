"""Test design data access (private to the module). Every query is organization- and project-scoped."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, func, literal, select, text, update
from sqlalchemy.orm import Session

from tcms.core.context import AccessContext
from tcms.core.enums import CaseStatus
from tcms.testdesign.models import (
    AutomationKey,
    Folder,
    Tag,
    TestCase,
    TestCaseLink,
    TestCaseStep,
    TestCaseTag,
    TestCaseVersion,
)


def _scope(stmt: Any, model: Any, ctx: AccessContext) -> Any:
    return stmt.where(model.organization_id == ctx.principal.organization_id, model.project_id == ctx.pid)


# -- folders --------------------------------------------------------------------------------------


def folders(s: Session, ctx: AccessContext) -> list[Folder]:
    return list(
        s.execute(
            _scope(select(Folder), Folder, ctx).order_by(
                Folder.depth, Folder.position, func.lower(Folder.name)
            )
        ).scalars()
    )


def folder(s: Session, ctx: AccessContext, folder_id: UUID, *, for_update: bool = False) -> Folder | None:
    stmt = _scope(select(Folder), Folder, ctx).where(Folder.id == folder_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def sibling_named(
    s: Session, ctx: AccessContext, parent_id: UUID | None, name: str, *, exclude: UUID | None = None
) -> bool:
    stmt = _scope(select(Folder.id), Folder, ctx).where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id,
        func.lower(Folder.name) == name.lower(),
    )
    if exclude is not None:
        stmt = stmt.where(Folder.id != exclude)
    return s.execute(stmt.limit(1)).first() is not None


def siblings(
    s: Session, ctx: AccessContext, parent_id: UUID | None, *, for_update: bool = False
) -> list[Folder]:
    stmt = _scope(select(Folder), Folder, ctx).where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return list(s.execute(stmt.order_by(Folder.position, func.lower(Folder.name))).scalars())


def subtree(s: Session, ctx: AccessContext, path: str, *, for_update: bool = False) -> list[Folder]:
    stmt = _scope(select(Folder), Folder, ctx).where(Folder.path.startswith(path, autoescape=True))
    if for_update:
        stmt = stmt.with_for_update()
    return list(s.execute(stmt).scalars())


def rewrite_subtree_paths(
    s: Session, ctx: AccessContext, old_prefix: str, new_prefix: str, depth_delta: int
) -> None:
    s.execute(
        update(Folder)
        .where(
            Folder.organization_id == ctx.principal.organization_id,
            Folder.project_id == ctx.pid,
            Folder.path.startswith(old_prefix, autoescape=True),
        )
        .values(
            path=literal(new_prefix) + func.substr(Folder.path, len(old_prefix) + 1),
            depth=Folder.depth + depth_delta,
        )
        .execution_options(synchronize_session=False)
    )


def folder_has_children(s: Session, ctx: AccessContext, folder_id: UUID) -> bool:
    return (
        s.execute(
            _scope(select(Folder.id), Folder, ctx).where(Folder.parent_id == folder_id).limit(1)
        ).first()
        is not None
    )


def folder_has_any_case(s: Session, ctx: AccessContext, folder_id: UUID) -> bool:
    return (
        s.execute(
            _scope(select(TestCase.id), TestCase, ctx).where(TestCase.folder_id == folder_id).limit(1)
        ).first()
        is not None
    )


def adjust_case_count(s: Session, folder_id: UUID, delta: int) -> None:
    if delta:
        s.execute(update(Folder).where(Folder.id == folder_id).values(case_count=Folder.case_count + delta))


# -- cases ----------------------------------------------------------------------------------------


def case_(s: Session, ctx: AccessContext, case_id: UUID, *, for_update: bool = False) -> TestCase | None:
    stmt = _scope(select(TestCase), TestCase, ctx).where(TestCase.id == case_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def case_by_key(s: Session, ctx: AccessContext, key: str) -> TestCase | None:
    return s.execute(_scope(select(TestCase), TestCase, ctx).where(TestCase.key == key)).scalar_one_or_none()


def case_by_number(s: Session, ctx: AccessContext, number: int) -> TestCase | None:
    return s.execute(
        _scope(select(TestCase), TestCase, ctx).where(TestCase.key_num == number)
    ).scalar_one_or_none()


def cases_by_ids(
    s: Session, ctx: AccessContext, ids: Sequence[UUID], *, for_update: bool = False
) -> list[TestCase]:
    if not ids:
        return []
    stmt = _scope(select(TestCase), TestCase, ctx).where(TestCase.id.in_(ids)).order_by(TestCase.key_num)
    if for_update:
        stmt = stmt.with_for_update()
    return list(s.execute(stmt).scalars())


def case_list_stmt(ctx: AccessContext) -> Select[Any]:
    stmt: Select[Any] = _scope(select(TestCase), TestCase, ctx)
    return stmt


def folder_ids_under(s: Session, ctx: AccessContext, folder_id: UUID) -> list[UUID]:
    root = folder(s, ctx, folder_id)
    if root is None:
        return []
    return [f.id for f in subtree(s, ctx, root.path)]


def title_exists_in_folder(
    s: Session, ctx: AccessContext, folder_id: UUID, title: str, *, exclude: UUID | None
) -> bool:
    stmt = _scope(select(TestCase.id), TestCase, ctx).where(
        TestCase.folder_id == folder_id,
        func.lower(TestCase.title) == title.lower(),
        TestCase.status != CaseStatus.archived,
    )
    if exclude is not None:
        stmt = stmt.where(TestCase.id != exclude)
    return s.execute(stmt.limit(1)).first() is not None


def update_search_vector(s: Session, case_id: UUID, description: str | None) -> None:
    """docs/05 §3.3: weights A = key + title, B = description of the latest version."""
    s.execute(
        update(TestCase)
        .where(TestCase.id == case_id)
        .values(
            search_vector=func.setweight(
                func.to_tsvector(text("'simple'"), TestCase.key + " " + TestCase.title), text("'A'")
            ).op("||")(func.setweight(func.to_tsvector(text("'simple'"), description or ""), text("'B'")))
        )
    )


def purge(s: Session, case_id: UUID) -> None:
    """purge_test_case() enforces BR-14 in SQL (raises case_has_runs) and deletes as tcms_owner."""
    s.execute(text("SELECT purge_test_case(:c)"), {"c": case_id})


# -- versions -------------------------------------------------------------------------------------


def version(
    s: Session, ctx: AccessContext, version_id: UUID, *, for_update: bool = False
) -> TestCaseVersion | None:
    stmt = _scope(select(TestCaseVersion), TestCaseVersion, ctx).where(TestCaseVersion.id == version_id)
    if for_update:
        stmt = stmt.with_for_update()
    return s.execute(stmt).scalar_one_or_none()


def version_by_no(s: Session, ctx: AccessContext, case_id: UUID, version_no: int) -> TestCaseVersion | None:
    return s.execute(
        _scope(select(TestCaseVersion), TestCaseVersion, ctx).where(
            TestCaseVersion.test_case_id == case_id, TestCaseVersion.version_no == version_no
        )
    ).scalar_one_or_none()


def versions(s: Session, ctx: AccessContext, case_id: UUID) -> list[TestCaseVersion]:
    return list(
        s.execute(
            _scope(select(TestCaseVersion), TestCaseVersion, ctx)
            .where(TestCaseVersion.test_case_id == case_id)
            .order_by(TestCaseVersion.version_no.desc())
        ).scalars()
    )


def steps_of(s: Session, version_ids: Iterable[UUID]) -> dict[UUID, list[TestCaseStep]]:
    ids = list(version_ids)
    out: dict[UUID, list[TestCaseStep]] = {i: [] for i in ids}
    if ids:
        for st in s.execute(
            select(TestCaseStep).where(TestCaseStep.version_id.in_(ids)).order_by(TestCaseStep.position)
        ).scalars():
            out[st.version_id].append(st)
    return out


def step(s: Session, ctx: AccessContext, step_id: UUID) -> TestCaseStep | None:
    return s.execute(
        _scope(select(TestCaseStep), TestCaseStep, ctx).where(TestCaseStep.id == step_id)
    ).scalar_one_or_none()


# -- tags -----------------------------------------------------------------------------------------


def tags(s: Session, ctx: AccessContext) -> list[tuple[Tag, int]]:
    usage = (
        select(func.count()).select_from(TestCaseTag).where(TestCaseTag.tag_id == Tag.id).scalar_subquery()
    )
    rows = s.execute(_scope(select(Tag, usage), Tag, ctx).order_by(Tag.is_system.desc(), Tag.name)).all()
    return [(t, int(n)) for t, n in rows]


def tag(s: Session, ctx: AccessContext, tag_id: UUID) -> Tag | None:
    return s.execute(_scope(select(Tag), Tag, ctx).where(Tag.id == tag_id)).scalar_one_or_none()


def tags_by_name(s: Session, ctx: AccessContext, names: Iterable[str]) -> dict[str, Tag]:
    names = list(names)
    if not names:
        return {}
    return {t.name: t for t in s.execute(_scope(select(Tag), Tag, ctx).where(Tag.name.in_(names))).scalars()}


def tag_names_of(s: Session, case_ids: Iterable[UUID]) -> dict[UUID, list[str]]:
    ids = list(case_ids)
    out: dict[UUID, list[str]] = {i: [] for i in ids}
    if ids:
        rows = s.execute(
            select(TestCaseTag.test_case_id, Tag.name)
            .join(Tag, Tag.id == TestCaseTag.tag_id)
            .where(TestCaseTag.test_case_id.in_(ids))
            .order_by(Tag.name)
        ).all()
        for cid, name in rows:
            out[cid].append(name)
    return out


def set_case_tags(s: Session, case_id: UUID, tag_ids: Iterable[UUID]) -> None:
    s.execute(delete(TestCaseTag).where(TestCaseTag.test_case_id == case_id))
    for tid in tag_ids:
        s.add(TestCaseTag(test_case_id=case_id, tag_id=tid))


def tag_in_use(s: Session, tag_id: UUID) -> bool:
    return (
        s.execute(select(TestCaseTag.tag_id).where(TestCaseTag.tag_id == tag_id).limit(1)).first() is not None
    )


# -- automation keys and links --------------------------------------------------------------------


def automation_keys_of(s: Session, case_ids: Iterable[UUID]) -> dict[UUID, list[str]]:
    ids = list(case_ids)
    out: dict[UUID, list[str]] = {i: [] for i in ids}
    if ids:
        for cid, key in s.execute(
            select(AutomationKey.test_case_id, AutomationKey.key)
            .where(AutomationKey.test_case_id.in_(ids))
            .order_by(AutomationKey.key)
        ).all():
            out[cid].append(key)
    return out


def automation_keys_taken(
    s: Session, ctx: AccessContext, keys: Iterable[str], *, exclude_case: UUID
) -> list[str]:
    keys = list(keys)
    if not keys:
        return []
    return list(
        s.execute(
            _scope(select(AutomationKey.key), AutomationKey, ctx).where(
                AutomationKey.key.in_(keys), AutomationKey.test_case_id != exclude_case
            )
        ).scalars()
    )


def set_automation_keys(
    s: Session, ctx: AccessContext, case_id: UUID, keys: Iterable[str], actor: UUID | None, now: Any
) -> None:
    from tcms.core import ids

    s.execute(delete(AutomationKey).where(AutomationKey.test_case_id == case_id))
    for k in keys:
        s.add(
            AutomationKey(
                id=ids.new_id(),
                organization_id=ctx.principal.organization_id,
                project_id=ctx.pid,
                test_case_id=case_id,
                key=k,
                created_at=now,
                created_by=actor,
            )
        )


def links_of(s: Session, ctx: AccessContext, case_id: UUID) -> list[TestCaseLink]:
    return list(
        s.execute(
            _scope(select(TestCaseLink), TestCaseLink, ctx)
            .where((TestCaseLink.source_case_id == case_id) | (TestCaseLink.target_case_id == case_id))
            .order_by(TestCaseLink.created_at)
        ).scalars()
    )


def link(s: Session, ctx: AccessContext, source: UUID, target: UUID, link_type: str) -> TestCaseLink | None:
    return s.execute(
        _scope(select(TestCaseLink), TestCaseLink, ctx).where(
            TestCaseLink.source_case_id == source,
            TestCaseLink.target_case_id == target,
            TestCaseLink.link_type == link_type,
        )
    ).scalar_one_or_none()
