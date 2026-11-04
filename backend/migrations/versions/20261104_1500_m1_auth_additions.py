"""M1 auth additions: sessions.mfa_failed_attempts, auth_rate_limits (docs/schema/03_m1_additions.sql).

Revision ID: 0002_m1_auth_additions
Revises: 0001_baseline
Create Date: 2026-11-04
"""

from collections.abc import Sequence

revision: str = "0002_m1_auth_additions"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from tcms_migrations import run_sql_file  # imported lazily: revision files must load without env.py

    run_sql_file("03_m1_additions.sql")


def downgrade() -> None:
    raise NotImplementedError("forward-only migration (ADR-014)")
