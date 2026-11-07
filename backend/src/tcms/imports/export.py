"""Test case export in the import layout (docs/02 §15.2; FR-IMP-002; M8 D7): one row per step, a `Key`
column, canonical headers — so the file re-imports as updates and an unchanged file is a no-op
(AC-IMP-02)."""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from tcms.core.context import AccessContext
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.imports import fields as F
from tcms.testdesign import queries as td_queries

COLUMNS: Final = [f for f in F.CASE_FIELDS]
HEADER: Final = [f.label for f in COLUMNS]


def case_rows(uow: UnitOfWork, ctx: AccessContext, case_ids: list[UUID], *, version: str) -> list[list[Any]]:
    s = uow.session
    snaps = []
    for i in range(0, len(case_ids), 1000):
        snaps += td_queries.case_snapshots(s, ctx, case_ids=case_ids[i : i + 1000], version=version)
    snaps.sort(key=lambda c: c.key_num)
    owners = identity_queries.user_refs(s, {c.owner_id for c in snaps})
    rows: list[list[Any]] = []
    for c in snaps:
        content = c.content
        case_values = {
            "key": c.key,
            "title": content.title,
            "folder": "/".join(c.folder_path),
            "type": c.type,
            "priority": c.priority,
            "design_technique": c.design_technique or "",
            "owner": owners[c.owner_id].email if c.owner_id in owners else "",
            "tags": ", ".join(c.tags),
            "automation_status": c.automation_status,
            "estimated_minutes": c.estimated_minutes if c.estimated_minutes is not None else "",
            "description": content.description or "",
            "preconditions": content.preconditions or "",
            "test_data": content.test_data or "",
            "expected_result": content.expected_result or "",
            "postconditions": content.postconditions or "",
            "format": content.format.value,
            "text_body": content.text_body or "",
        }
        steps: list[Any] = list(content.steps) or [None]
        for n, st in enumerate(steps):
            step_values = {
                "step_action": st.action if st else "",
                "step_expected": (st.expected_result or "") if st else "",
                "step_data": (st.data or "") if st else "",
            }
            rows.append(
                [(case_values if n == 0 else {}).get(f.key, step_values.get(f.key, "")) for f in COLUMNS]
            )
    return rows
