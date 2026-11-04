"""Baseline: every MVP table, enum, index, trigger, grant and the system roles (docs/05 §8.2).

Executes docs/schema/01_baseline.sql and docs/schema/02_seed_system.sql verbatim. Those two files are
frozen once released: later schema changes go into new migrations (and new docs/schema/NN_*.sql files).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-04
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from tcms_migrations import run_sql_file  # imported lazily: revision files must load without env.py

    run_sql_file("01_baseline.sql")
    run_sql_file("02_seed_system.sql")


def downgrade() -> None:
    raise NotImplementedError("forward-only migration (ADR-014)")
