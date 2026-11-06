"""M5 bug links, settings rename, max_open_defects → max_failed (docs/schema/04_m5_bug_links.sql).

Revision ID: 0003_m5_bug_links
Revises: 0002_m1_auth_additions
Create Date: 2026-11-06
"""

from collections.abc import Sequence

revision: str = "0003_m5_bug_links"
down_revision: str | None = "0002_m1_auth_additions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from tcms_migrations import run_sql_file  # imported lazily: revision files must load without env.py

    run_sql_file("04_m5_bug_links.sql")


def downgrade() -> None:
    raise NotImplementedError("forward-only migration (ADR-014)")
