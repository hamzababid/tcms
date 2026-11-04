"""Tenant scoping for repository queries (docs/04 §3.4, ADR-003).

Every repository function applies `ScopedQuery.project` or `ScopedQuery.org` to its statements.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select

from tcms.core.context import AccessContext

S = TypeVar("S", bound=Select[Any])


class ScopedQuery:
    @staticmethod
    def org(stmt: S, model: Any, ctx: AccessContext) -> S:
        return stmt.where(model.organization_id == ctx.principal.organization_id)

    @staticmethod
    def project(stmt: S, model: Any, ctx: AccessContext) -> S:
        if ctx.project_id is None:
            raise RuntimeError("project-scoped query without a project in the AccessContext")
        return stmt.where(
            model.organization_id == ctx.principal.organization_id,
            model.project_id == ctx.project_id,
        )
