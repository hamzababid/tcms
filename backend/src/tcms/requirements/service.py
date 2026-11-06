"""Requirement-reference use cases (docs/02 §10; ADR-024). The only write entry points of the module.

Requirements live in the team's tool. Assay keeps references (`SPK-120` + optional URL and title), links them
to cases, and computes coverage. Audit names (docs/02 §13.1): `requirement.created`, `requirement.updated`,
`requirement.archived`, `requirement.restored`, `requirement.linked`, `requirement.unlinked`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, NotFound, PermissionDenied, ValidationFailed
from tcms.core.references import (
    clean_title,
    link_url,
    normalize_reference,
    reference_norm,
    title_problem,
    url_problem,
)
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.requirements import repository as repo
from tcms.requirements import rules
from tcms.requirements.models import RequirementRef
from tcms.testdesign import queries as testdesign_queries
from tcms.workspace import queries as workspace_queries
from tcms.workspace.rules import requirement_template


def _template(uow: UnitOfWork, ctx: AccessContext) -> str | None:
    p = workspace_queries.project(uow.session, ctx.principal.organization_id, ctx.pid)
    if p is None:
        raise NotFound()
    return requirement_template(workspace_queries.project_settings(p))


def _touch(row: Any, ctx: AccessContext) -> None:
    row.updated_at = clock.now()
    row.updated_by = ctx.principal.user_id
    row.row_version += 1


@dataclass(frozen=True)
class Ensured:
    refs: list[RequirementRef]  # in input order
    created: int


def ensure_refs(
    uow: UnitOfWork,
    ctx: AccessContext,
    references: list[str],
    *,
    url: str | None = None,
    title: str | None = None,
) -> Ensured:
    """Find or create references (case-insensitive, once per project). Creating needs `requirement.manage`
    or `requirement.link` (D12: linking an unknown reference registers it). `url`/`title` apply to a single
    new reference. Archived references are restored when used again."""
    if not (ctx.has("requirement.manage") or ctx.has("requirement.link")):
        raise PermissionDenied("requirement.link")
    problems = [p for p in (url_problem(url), title_problem(title)) if p]
    if problems:
        raise ValidationFailed("Check the requirement", errors=problems)
    norms = [reference_norm(r) for r in references]
    found = repo.refs_by_norm(uow.session, ctx, norms)
    template = _template(uow, ctx)
    out: list[RequirementRef] = []
    created = 0
    now = clock.now()
    for raw, norm in zip(references, norms, strict=True):
        row = found.get(norm)
        if row is None:
            ref = normalize_reference(raw)
            single = len(references) == 1
            row = RequirementRef(
                id=ids.new_id(),
                organization_id=ctx.principal.organization_id,
                project_id=ctx.pid,
                reference=ref,
                reference_norm=norm,
                url=link_url(url if single else None, template, ref),
                title=clean_title(title) if single else None,
                created_at=now,
                created_by=ctx.principal.user_id,
                updated_at=now,
                updated_by=ctx.principal.user_id,
            )
            repo.add(uow.session, row)
            found[norm] = row
            created += 1
            uow.audit(ctx, "requirement.created", _target(row), extra={"reference": ref, "url": row.url})
        elif row.archived_at is not None:
            row.archived_at = None
            _touch(row, ctx)
            uow.audit(ctx, "requirement.restored", _target(row))
        out.append(row)
    return Ensured(out, created)


def _target(row: RequirementRef) -> AuditTarget:
    return AuditTarget("requirement_ref", row.id, row.reference)


def add_refs(
    uow: UnitOfWork, ctx: AccessContext, *, text: str, url: str | None, title: str | None
) -> Ensured:
    """R-120 "paste many": `SPK-120, SPK-121` or one per line; existing ones are reused."""
    ctx.require("requirement.manage")
    refs, problems = rules.paste_problems(text)
    if problems:
        raise ValidationFailed("Check the references", errors=problems)
    return ensure_refs(uow, ctx, refs, url=url, title=title)


def _ref(uow: UnitOfWork, ctx: AccessContext, ref_id: UUID) -> RequirementRef:
    row = repo.ref(uow.session, ctx, ref_id, for_update=True)
    if row is None:
        raise NotFound()
    return row


def update_ref(
    uow: UnitOfWork, ctx: AccessContext, ref_id: UUID, *, fields: dict[str, str | None]
) -> RequirementRef:
    """Correct the URL or title. The reference itself is the identity; add a new one to rename."""
    ctx.require("requirement.manage")
    row = _ref(uow, ctx, ref_id)
    url = fields.get("url", row.url)
    title = fields.get("title", row.title)
    problems = [p for p in (url_problem(url), title_problem(title)) if p]
    if problems:
        raise ValidationFailed("Check the requirement", errors=problems)
    changes: dict[str, list[Any]] = {}
    new_url, new_title = (url or "").strip() or None, clean_title(title)
    if new_url != row.url:
        changes["url"] = [row.url, new_url]
        row.url = new_url
    if new_title != row.title:
        changes["title"] = [row.title, new_title]
        row.title = new_title
    if changes:
        _touch(row, ctx)
        uow.audit(ctx, "requirement.updated", _target(row), changes=changes)
    return row


def set_archived(uow: UnitOfWork, ctx: AccessContext, ref_id: UUID, *, archived: bool) -> RequirementRef:
    """Archived references leave every scope and the matrix; links are kept for history."""
    ctx.require("requirement.manage")
    row = _ref(uow, ctx, ref_id)
    if (row.archived_at is not None) != archived:
        row.archived_at = clock.now() if archived else None
        _touch(row, ctx)
        uow.audit(ctx, "requirement.archived" if archived else "requirement.restored", _target(row))
    return row


def _valid_cases(uow: UnitOfWork, ctx: AccessContext, case_ids: list[UUID]) -> dict[UUID, str]:
    refs = testdesign_queries.case_refs(uow.session, ctx, case_ids)
    unknown = [c for c in case_ids if c not in refs]
    if unknown:
        raise ValidationFailed(
            "Unknown test case", errors=[FieldError("test_case_ids", "not_found", "Unknown test case")]
        )
    return {cid: r.key for cid, r in refs.items()}


def link(uow: UnitOfWork, ctx: AccessContext, refs: list[RequirementRef], case_ids: list[UUID]) -> int:
    """R-121: link every reference to every case (idempotent). `requirement.link`."""
    ctx.require("requirement.link")
    keys = _valid_cases(uow, ctx, case_ids)
    present = repo.existing_links(uow.session, [r.id for r in refs], case_ids)
    added = 0
    for r in refs:
        for cid in dict.fromkeys(case_ids):
            if (r.id, cid) in present:
                continue
            repo.add_link(uow.session, ctx, r.id, cid, ctx.principal.user_id)
            present.add((r.id, cid))
            added += 1
            uow.audit(
                ctx,
                "requirement.linked",
                _target(r),
                extra={"test_case_id": str(cid), "test_case_key": keys[cid]},
                summary=f"{ctx.principal.display_name} linked {r.reference} to {keys[cid]}",
            )
    uow.session.flush()
    return added


def link_references(
    uow: UnitOfWork, ctx: AccessContext, *, text: str, case_ids: list[UUID]
) -> tuple[Ensured, int]:
    """From a case or in bulk from the repository: references by text (created if new, D12)."""
    ctx.require("requirement.link")
    refs, problems = rules.paste_problems(text)
    if problems:
        raise ValidationFailed("Check the references", errors=problems)
    ensured = ensure_refs(uow, ctx, refs)
    return ensured, link(uow, ctx, ensured.refs, case_ids)


def link_cases(uow: UnitOfWork, ctx: AccessContext, ref_id: UUID, case_ids: list[UUID]) -> int:
    row = _ref(uow, ctx, ref_id)
    return link(uow, ctx, [row], case_ids)


def unlink(uow: UnitOfWork, ctx: AccessContext, ref_id: UUID, case_id: UUID) -> None:
    ctx.require("requirement.link")
    row = _ref(uow, ctx, ref_id)
    if repo.remove_link(uow.session, ctx, ref_id, case_id) == 0:
        raise NotFound()
    keys = testdesign_queries.case_refs(uow.session, ctx, [case_id])
    uow.audit(
        ctx,
        "requirement.unlinked",
        _target(row),
        extra={"test_case_id": str(case_id), "test_case_key": keys[case_id].key if case_id in keys else None},
    )
