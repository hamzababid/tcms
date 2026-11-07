"""Bug-link use cases (docs/02 §8; ADR-023). The only write entry points of the bugs module.

Bugs live in the team's tracker; Assay records references on attempts and cases. Audit names follow
docs/02 §13.1: `bug.linked`, `bug.updated`, `bug.unlinked`, `bug.retest_requested`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tcms.bugs import repository as repo
from tcms.bugs import rules
from tcms.bugs.errors import AlreadyLinked, BugLinkRequired
from tcms.bugs.models import BugLink
from tcms.core import clock, ids
from tcms.core.context import AccessContext
from tcms.core.errors import FieldError, NotFound, PermissionDenied, ValidationFailed
from tcms.core.events import subscribe
from tcms.core.uow import AuditTarget, UnitOfWork
from tcms.execution import queries as exec_queries
from tcms.execution import service as execution
from tcms.execution.events import DraftDiscarding, ResultFinalizing
from tcms.platform import notifications
from tcms.testdesign import queries as testdesign_queries
from tcms.workspace import queries as workspace_queries


def _settings(uow: UnitOfWork, ctx: AccessContext) -> dict[str, Any]:
    p = workspace_queries.project(uow.session, ctx.principal.organization_id, ctx.pid)
    if p is None:
        raise NotFound()
    return workspace_queries.project_settings(p)


def _target(row: BugLink, where: str) -> AuditTarget:
    return AuditTarget("bug_link", row.id, f"{row.reference} on {where}")


def _validated(reference: str, url: str | None, title: str | None) -> tuple[str, str | None, str | None]:
    problems = rules.link_problems(reference, url, title)
    if problems:
        raise ValidationFailed("Check the bug link", errors=problems)
    return rules.normalize_reference(reference), (url or "").strip() or None, rules.clean_title(title)


def _insert(
    uow: UnitOfWork,
    ctx: AccessContext,
    *,
    reference: str,
    url: str | None,
    title: str | None,
    test_case_id: UUID,
    run_id: UUID | None,
    result_id: UUID | None,
    step_id: UUID | None,
    where: str,
) -> BugLink:
    norm = rules.reference_norm(reference)
    if repo.existing(
        uow.session, ctx, reference_norm=norm, test_case_id=test_case_id, result_id=result_id, step_id=step_id
    ):
        raise AlreadyLinked(f"{reference} is already linked to {where}")
    now = clock.now()
    row = BugLink(
        id=ids.new_id(),
        organization_id=ctx.principal.organization_id,
        project_id=ctx.pid,
        reference=reference,
        reference_norm=norm,
        url=rules.link_url(url, _settings(uow, ctx).get("bug_url_template"), reference),
        title=title,
        test_case_id=test_case_id,
        run_id=run_id,
        result_id=result_id,
        step_id=step_id,
        created_at=now,
        created_by=ctx.principal.user_id,
        updated_at=now,
        updated_by=ctx.principal.user_id,
    )
    repo.add(uow.session, row)
    uow.audit(
        ctx,
        "bug.linked",
        _target(row, where),
        extra={"reference": reference, "url": row.url, **({"step_id": str(step_id)} if step_id else {})},
        summary=f"{ctx.principal.display_name} linked {reference} to {where}",
    )
    return row


def link_to_result(
    uow: UnitOfWork,
    ctx: AccessContext,
    result_id: UUID,
    *,
    reference: str,
    url: str | None,
    title: str | None,
    step_id: UUID | None,
) -> BugLink:
    """BR-20 / AC-BUG-01: a link on an attempt records the attempt, its run, the step and the case. Draft
    and final attempts both accept links (links are not part of the attempt, BR-06)."""
    ctx.require("defect.create")
    reference, url, title = _validated(reference, url, title)
    att = exec_queries.attempt_context(uow.session, ctx, result_id)
    where = f"{att.cycle_key} / {att.case_key} #{att.result.attempt_no}"
    if step_id is not None:
        positions = {st.id: st.position for st in (att.version.steps if att.version else [])}
        if step_id not in positions:
            raise ValidationFailed(
                "Unknown step", errors=[FieldError("step_id", "invalid_value", "Not a step of this run")]
            )
        where += f" step {positions[step_id]}"
    return _insert(
        uow,
        ctx,
        reference=reference,
        url=url,
        title=title,
        test_case_id=att.test_case_id,
        run_id=att.run_id,
        result_id=att.result.id,
        step_id=step_id,
        where=where,
    )


def link_to_case(
    uow: UnitOfWork, ctx: AccessContext, case_id: UUID, *, reference: str, url: str | None, title: str | None
) -> BugLink:
    """docs/02 §8.2: a bug found outside execution, linked to the case directly."""
    ctx.require("defect.create")
    reference, url, title = _validated(reference, url, title)
    ref = testdesign_queries.case_refs(uow.session, ctx, [case_id]).get(case_id)
    if ref is None:
        raise NotFound()
    return _insert(
        uow,
        ctx,
        reference=reference,
        url=url,
        title=title,
        test_case_id=case_id,
        run_id=None,
        result_id=None,
        step_id=None,
        where=ref.key,
    )


def _editable(uow: UnitOfWork, ctx: AccessContext, link_id: UUID) -> BugLink:
    row = repo.link(uow.session, ctx, link_id, for_update=True)
    if row is None:
        raise NotFound()
    if not (
        ctx.has("defect.edit") or (row.created_by is not None and row.created_by == ctx.principal.user_id)
    ):
        raise PermissionDenied(
            "defect.edit", "Only the person who linked it or a bug-link editor can change it"
        )
    return row


def update_link(
    uow: UnitOfWork, ctx: AccessContext, link_id: UUID, *, fields: dict[str, str | None]
) -> BugLink:
    """Correct the URL or title (docs/02 §8.2). The reference itself is not edited: remove and link again."""
    row = _editable(uow, ctx, link_id)
    url = fields.get("url", row.url) if "url" in fields else row.url
    title = fields.get("title", row.title) if "title" in fields else row.title
    problems = [p for p in (rules.url_problem(url), rules.title_problem(title)) if p]
    if problems:
        raise ValidationFailed("Check the bug link", errors=problems)
    changes: dict[str, list[Any]] = {}
    new_url, new_title = (url or "").strip() or None, rules.clean_title(title)
    if new_url != row.url:
        changes["url"] = [row.url, new_url]
        row.url = new_url
    if new_title != row.title:
        changes["title"] = [row.title, new_title]
        row.title = new_title
    if changes:
        row.updated_at = clock.now()
        row.updated_by = ctx.principal.user_id
        row.row_version += 1
        uow.audit(ctx, "bug.updated", _target(row, "its record"), changes=changes)
    return row


def remove_link(uow: UnitOfWork, ctx: AccessContext, link_id: UUID) -> None:
    row = _editable(uow, ctx, link_id)
    uow.audit(
        ctx,
        "bug.unlinked",
        _target(row, "its record"),
        extra={"reference": row.reference, "result_id": str(row.result_id) if row.result_id else None},
        summary=f"{ctx.principal.display_name} removed the link to {row.reference}",
    )
    repo.remove(uow.session, row)


@dataclass(frozen=True)
class RetestOutcome:
    reference: str
    linked_runs: int
    flagged_run_ids: list[UUID]


def request_retest(uow: UnitOfWork, ctx: AccessContext, reference: str, *, dry_run: bool) -> RetestOutcome:
    """BR-21 / AC-BUG-03: flag every non-superseded run linked to the reference in a non-closed cycle."""
    ctx.require("cycle.manage")
    links = repo.links_of_reference(uow.session, ctx, rules.reference_norm(reference))
    if not links:
        raise NotFound(f"No bug {reference.strip()} is linked in this project")
    run_ids = sorted({row.run_id for row in links if row.run_id is not None})
    flagged = execution.flag_runs_for_retest(uow, ctx, run_ids, dry_run=dry_run)
    shown = links[-1].reference
    if not dry_run:
        uow.audit(
            ctx,
            "bug.retest_requested",
            AuditTarget("bug_reference", None, shown),
            extra={"reference": shown, "run_ids": [str(r) for r in flagged]},
            summary=f"{ctx.principal.display_name} marked {shown} ready for retest ({len(flagged)} run(s))",
        )
        _notify_retest(uow, ctx, shown, flagged)
    return RetestOutcome(shown, len(run_ids), flagged)


def _notify_retest(uow: UnitOfWork, ctx: AccessContext, reference: str, run_ids: list[UUID]) -> None:
    """M7 / L33: each assignee hears once per cycle that their runs need a retest."""
    groups: dict[tuple[UUID, UUID], tuple[str, int]] = {}
    for _, assignee, cycle_id, cycle_key in exec_queries.run_assignees(uow.session, ctx, run_ids):
        if assignee is None:
            continue
        key, n = groups.get((assignee, cycle_id), (cycle_key, 0))
        groups[(assignee, cycle_id)] = (key, n + 1)
    for (assignee, cycle_id), (cycle_key, n) in groups.items():
        notifications.notify(
            uow,
            organization_id=ctx.principal.organization_id,
            user_ids={assignee},
            type="bug.retest_requested",
            project_id=ctx.pid,
            entity_type="test_cycle",
            entity_id=cycle_id,
            payload={
                "reference": reference,
                "cycle_key": cycle_key,
                "count": n,
                "by": ctx.principal.display_name,
            },
            exclude=ctx.principal.user_id,
        )


# -- execution events (docs/03 §5.4) ----------------------------------------------------------------


@subscribe(ResultFinalizing)
def require_link_for_failure(uow: UnitOfWork, event: ResultFinalizing) -> None:
    """AC-BUG-04: with `require_bug_link_for_failure`, a Failed attempt needs a link on that attempt."""
    if event.status != "failed":
        return
    ctx = event.ctx
    if not _settings(uow, ctx).get("require_bug_link_for_failure"):
        return
    if not repo.has_link_on_result(uow.session, ctx, event.result_id):
        raise BugLinkRequired("This project needs a bug link on every failed result")


@subscribe(DraftDiscarding)
def drop_links_of_discarded_draft(uow: UnitOfWork, event: DraftDiscarding) -> None:
    """docs/02 §8.2: a discarded draft takes its bug links with it (audited)."""
    ctx = event.ctx
    rows = repo.links_of_result(uow.session, ctx, event.result_id)
    for row in rows:
        uow.audit(
            ctx,
            "bug.unlinked",
            _target(row, "a discarded draft"),
            extra={"reference": row.reference, "reason": event.reason},
        )
    if rows:
        repo.delete_links_of_result(uow.session, ctx, event.result_id)
