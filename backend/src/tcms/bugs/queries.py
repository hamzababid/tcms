"""Public read functions of the bugs module (docs/02 §8.2–8.4; docs/06 §4.8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from tcms.bugs import repository as repo
from tcms.bugs import rules
from tcms.bugs.models import BugLink
from tcms.core.context import AccessContext
from tcms.core.errors import NotFound
from tcms.execution import queries as exec_queries
from tcms.testdesign import queries as td


@dataclass(frozen=True)
class LinkView:
    id: UUID
    reference: str
    url: str | None
    title: str | None
    test_case_id: UUID
    case_key: str
    case_title: str
    run_id: UUID | None
    result_id: UUID | None
    step_id: UUID | None
    step_position: int | None
    cycle_id: UUID | None
    cycle_key: str | None
    run_status: str | None
    attempt_no: int | None
    attempt_status: str | None
    created_by: UUID | None
    created_at: datetime
    row_version: int


def _views(s: Session, ctx: AccessContext, rows: list[BugLink]) -> list[LinkView]:
    cases = td.case_refs(s, ctx, sorted({r.test_case_id for r in rows}))
    runs = exec_queries.runs_brief(s, ctx, sorted({r.run_id for r in rows if r.run_id}))
    attempts = exec_queries.attempt_brief(s, ctx, sorted({r.result_id for r in rows if r.result_id}))
    positions = td.step_positions(s, ctx, sorted({r.step_id for r in rows if r.step_id}))
    out = []
    for r in rows:
        case = cases.get(r.test_case_id)
        run = runs.get(r.run_id) if r.run_id else None
        att = attempts.get(r.result_id) if r.result_id else None
        out.append(
            LinkView(
                id=r.id,
                reference=r.reference,
                url=r.url,
                title=r.title,
                test_case_id=r.test_case_id,
                case_key=case.key if case else "",
                case_title=case.title if case else "",
                run_id=r.run_id,
                result_id=r.result_id,
                step_id=r.step_id,
                step_position=positions.get(r.step_id) if r.step_id else None,
                cycle_id=run.cycle_id if run else None,
                cycle_key=run.cycle_key if run else None,
                run_status=run.status if run else None,
                attempt_no=att[0] if att else None,
                attempt_status=(att[2] or att[1]) if att else None,
                created_by=r.created_by,
                created_at=r.created_at,
                row_version=r.row_version,
            )
        )
    return out


def link_detail(s: Session, ctx: AccessContext, link_id: UUID) -> LinkView:
    row = repo.link(s, ctx, link_id)
    if row is None:
        raise NotFound()
    return _views(s, ctx, [row])[0]


def links_of_run(s: Session, ctx: AccessContext, run_id: UUID) -> list[LinkView]:
    return _views(s, ctx, repo.links_of_runs(s, ctx, [run_id]))


def links_of_cycle(s: Session, ctx: AccessContext, cycle_id: UUID) -> list[LinkView]:
    """Every link on the cycle's runs (cycle detail Bugs column, docs/07 §5.8)."""
    run_ids = exec_queries.run_ids_in_cycle(s, ctx, cycle_id)
    return _views(s, ctx, repo.links_of_runs(s, ctx, run_ids))


def links_of_case(s: Session, ctx: AccessContext, case_id: UUID) -> list[LinkView]:
    """Case page Bugs tab: direct case links and links through its runs (R-111)."""
    return _views(s, ctx, repo.links_of_case(s, ctx, case_id))


def links_of_reference(s: Session, ctx: AccessContext, reference: str) -> list[LinkView]:
    rows = repo.links_of_reference(s, ctx, rules.reference_norm(reference))
    if not rows:
        raise NotFound()
    return _views(s, ctx, rows)


def recent_references(s: Session, ctx: AccessContext, cycle_id: UUID, limit: int = 8) -> list[LinkView]:
    """Suggestions in the link popover: references used most recently in the cycle."""
    run_ids = exec_queries.run_ids_in_cycle(s, ctx, cycle_id)
    return _views(s, ctx, repo.recent_references(s, ctx, run_ids, limit))


# -- Bugs list (docs/02 §8.4) ------------------------------------------------------------------------


@dataclass(frozen=True)
class BugSummary:
    reference: str
    url: str | None
    title: str | None
    cases: int
    runs: int
    failing_runs: int
    needs_retest_runs: int
    cycle_keys: list[str]
    first_linked_at: datetime
    last_linked_at: datetime


def bug_list(
    s: Session, ctx: AccessContext, *, q: str | None, cycle_id: UUID | None, failing: bool
) -> list[BugSummary]:
    """One row per reference, most recently linked first. A run counts as failing when it is not
    superseded and its latest status is failed."""
    run_scope = exec_queries.run_ids_in_cycle(s, ctx, cycle_id) if cycle_id else None
    rows = repo.references(s, ctx, q=q, run_ids=run_scope)
    runs = exec_queries.runs_brief(s, ctx, sorted({r.run_id for r in rows if r.run_id}))
    groups: dict[str, list[BugLink]] = {}
    for r in rows:
        groups.setdefault(r.reference_norm, []).append(r)
    out = []
    for links in groups.values():
        run_ids = {r.run_id for r in links if r.run_id}
        briefs = [runs[i] for i in run_ids if i in runs]
        live = [b for b in briefs if not b.superseded]
        latest = links[-1]
        summary = BugSummary(
            reference=latest.reference,
            url=next((r.url for r in reversed(links) if r.url), None),
            title=next((r.title for r in reversed(links) if r.title), None),
            cases=len({r.test_case_id for r in links}),
            runs=len(run_ids),
            failing_runs=sum(1 for b in live if b.status == "failed"),
            needs_retest_runs=sum(1 for b in live if b.needs_retest),
            cycle_keys=sorted({b.cycle_key for b in briefs}, key=lambda k: (len(k), k)),
            first_linked_at=links[0].created_at,
            last_linked_at=latest.created_at,
        )
        if failing and summary.failing_runs == 0:
            continue
        out.append(summary)
    return sorted(out, key=lambda b: b.last_linked_at, reverse=True)


# -- "Copy bug details" (docs/02 §8.2) ----------------------------------------------------------------


def bug_report(s: Session, ctx: AccessContext, result_id: UUID, step_id: UUID | None, run_url: str) -> str:
    att = exec_queries.attempt_context(s, ctx, result_id)
    v = att.version
    by_step = {st.step_id: st for st in att.result.steps}
    steps = [
        rules.ReportStep(
            position=st.position,
            action=st.action,
            data=st.data,
            expected=st.expected_result,
            status=by_step[st.id].status if st.id in by_step else "not_run",
            actual=by_step[st.id].actual_result if st.id in by_step else None,
        )
        for st in (v.steps if v else [])
    ]
    position = next((st.position for st in (v.steps if v else []) if st.id == step_id), None)
    if step_id is not None and position is None:
        raise NotFound()
    data = rules.ReportInput(
        case_key=att.case_key,
        case_title=v.title if v else att.case_title,
        version_no=v.version_no if v else 0,
        preconditions=v.preconditions if v else None,
        test_data=v.test_data if v else None,
        steps=steps,
        text_body=v.text_body if v else None,
        cycle_key=att.cycle_key,
        cycle_name=att.cycle_name,
        environment=att.environment_name,
        build=att.result.build,
        attempt_no=att.result.attempt_no,
        attempt_status=att.result.status,
        attempt_comment=att.result.comment,
        run_url=run_url,
    )
    return rules.bug_report(data, position)


def owner_of_link(s: Session, link_id: UUID) -> tuple[UUID, UUID] | None:
    return repo.owner_of(s, link_id)
