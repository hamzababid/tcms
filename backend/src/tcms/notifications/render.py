"""Notification → title and link (docs/02 §2.7). Unknown types fall back to their type name."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcms.platform.notifications import NotificationView


@dataclass(frozen=True)
class Rendered:
    title: str
    url: str | None
    project_key: str | None


@dataclass
class Lookups:
    projects: dict[UUID, str]
    cycles: dict[UUID, str]
    cases: dict[UUID, str]  # test_case and test_case_version ids → case key


def lookups(s: Session, rows: Iterable[NotificationView]) -> Lookups:
    rows = list(rows)
    pids = list({r.project_id for r in rows if r.project_id})
    cycle_ids = list({r.entity_id for r in rows if r.entity_type == "test_cycle" and r.entity_id})
    case_ids = list({r.entity_id for r in rows if r.entity_type == "test_case" and r.entity_id})
    version_ids = list({r.entity_id for r in rows if r.entity_type == "test_case_version" and r.entity_id})
    out = Lookups({}, {}, {})
    if pids:
        out.projects = dict(
            s.execute(text("SELECT id, key FROM projects WHERE id = ANY(:i)"), {"i": pids}).all()
        )
    if cycle_ids:
        out.cycles = dict(
            s.execute(text("SELECT id, key FROM test_cycles WHERE id = ANY(:i)"), {"i": cycle_ids}).all()
        )
    if case_ids:
        out.cases.update(
            dict(s.execute(text("SELECT id, key FROM test_cases WHERE id = ANY(:i)"), {"i": case_ids}).all())
        )
    if version_ids:
        out.cases.update(
            dict(
                s.execute(
                    text(
                        "SELECT v.id, c.key FROM test_case_versions v"
                        " JOIN test_cases c ON c.id = v.test_case_id WHERE v.id = ANY(:i)"
                    ),
                    {"i": version_ids},
                ).all()
            )
        )
    return out


def _plural(n: object, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def render(n: NotificationView, lk: Lookups) -> Rendered:
    p = n.payload
    key = lk.projects.get(n.project_id) if n.project_id else None
    base = f"/p/{key}" if key else None
    by = p.get("by") or "Someone"

    def case_url(case_key: str | None) -> str | None:
        return f"{base}/cases/{case_key}" if base and case_key else None

    def cycle_url(cycle_key: str | None) -> str | None:
        return f"{base}/cycles/{cycle_key}" if base and cycle_key else None

    t = n.type
    if t == "runs.assigned":
        ck = p.get("cycle_key") or (lk.cycles.get(n.entity_id) if n.entity_id else None)
        title = (
            f"{_plural(p.get('count', 1), 'run')} assigned to you in {ck} · {p.get('cycle_name', '')}".rstrip(
                " ·"
            )
        )
        return Rendered(title, cycle_url(ck), key)
    if t == "cycle.runs_created":
        ck = lk.cycles.get(n.entity_id) if n.entity_id else None
        return Rendered(
            f"Runs of {ck or 'your cycle'} are ready ({p.get('case_count', 0)} cases)", cycle_url(ck), key
        )
    if t == "bug.retest_requested":
        ck = p.get("cycle_key")
        runs = _plural(p.get("count", 1), "run")
        title = f"{by} flagged {runs} of yours in {ck} for retest ({p.get('reference')})"
        return Rendered(title, cycle_url(ck), key)
    if t in ("test_case.review_requested", "test_case.approved", "test_case.returned"):
        ck = p.get("key") or (lk.cases.get(n.entity_id) if n.entity_id else None)
        verb = {
            "test_case.review_requested": "asked you to review",
            "test_case.approved": "approved",
            "test_case.returned": "returned",
        }[t]
        title = f"{by} {verb} {ck} v{p.get('version', '?')}"
        if t == "test_case.returned" and p.get("comment"):
            title += f": {p['comment']}"
        return Rendered(title, case_url(ck), key)
    if t == "comment.mentioned":
        ck = lk.cases.get(n.entity_id) if n.entity_id else None
        return Rendered(f"{by} mentioned you on {p.get('label') or ck}", case_url(ck), key)
    if t == "bulk.finished":
        title = (
            f"Bulk {str(p.get('action', 'change')).replace('_', ' ')} finished:"
            f" {p.get('updated', 0)} updated, {p.get('skipped', 0)} skipped"
        )
        return Rendered(title, f"{base}/repository" if base else None, key)
    if t == "export.ready":
        url = f"/api/v1/data-transfers/{n.entity_id}/download" if n.entity_id else None
        return Rendered(f"{p.get('title', 'Report')} export is ready ({p.get('rows', 0)} rows)", url, key)
    if t == "import.finished":
        done = ", ".join(f"{p[k]} {k}" for k in ("created", "updated", "unchanged", "skipped") if p.get(k))
        return Rendered(
            f"Import of {p.get('file_name', 'your file')} finished: {done or 'nothing to change'}",
            f"{base}/import?transfer={n.entity_id}" if base else None,
            key,
        )
    if t == "import.failed":
        return Rendered(
            f"Import of {p.get('file_name', 'your file')} failed: {p.get('reason', '')}",
            f"{base}/import?transfer={n.entity_id}" if base else None,
            key,
        )
    return Rendered(t.replace("_", " ").replace(".", " · "), base, key)
