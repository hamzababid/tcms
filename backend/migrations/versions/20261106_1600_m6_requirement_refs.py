"""M6 requirement references, case and plan links, search indexes (docs/schema/05_m6_requirement_refs.sql).

Revision ID: 0004_m6_requirement_refs
Revises: 0003_m5_bug_links
Create Date: 2026-11-06
"""

from collections.abc import Sequence

revision: str = "0004_m6_requirement_refs"
down_revision: str | None = "0003_m5_bug_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from tcms_migrations import run_sql_file  # imported lazily: revision files must load without env.py

    run_sql_file("05_m6_requirement_refs.sql")


def downgrade() -> None:
    raise NotImplementedError("forward-only migration (ADR-014)")
