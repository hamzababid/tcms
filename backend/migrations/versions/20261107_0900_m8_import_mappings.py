"""M8 import mapping templates (docs/schema/06_m8_import_mappings.sql).

Revision ID: 0005_m8_import_mappings
Revises: 0004_m6_requirement_refs
Create Date: 2026-11-07
"""

from collections.abc import Sequence

revision: str = "0005_m8_import_mappings"
down_revision: str | None = "0004_m6_requirement_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from tcms_migrations import run_sql_file  # imported lazily: revision files must load without env.py

    run_sql_file("06_m8_import_mappings.sql")


def downgrade() -> None:
    raise NotImplementedError("forward-only migration (ADR-014)")
