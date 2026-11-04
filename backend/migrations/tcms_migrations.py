"""Helpers shared by migrations (docs/ops/migrations.md)."""

from __future__ import annotations

import re
from pathlib import Path

from alembic import op

# backend/migrations/tcms_migrations.py -> repository root; the container image keeps the same layout.
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "docs" / "schema"

APPEND_ONLY_TABLES = frozenset({"audit_events", "defect_status_history", "release_decisions"})

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def run_sql_file(name: str) -> None:
    """Execute one of docs/schema/*.sql verbatim inside the migration's transaction.

    Only the file's own outer `BEGIN;` / `COMMIT;` lines are removed (Alembic owns the transaction).
    The raw psycopg connection is used so that `%` in the SQL is not treated as a placeholder.
    """
    sql = (SCHEMA_DIR / name).read_text(encoding="utf-8")
    lines = [ln for ln in sql.splitlines() if ln.strip().upper() not in ("BEGIN;", "COMMIT;")]
    raw = op.get_bind().connection.driver_connection
    raw.execute("\n".join(lines))  # type: ignore[union-attr]


def grant_app(table: str, *, append_only: bool = False) -> None:
    """Grant the application role its privileges on a table created after the baseline (G7)."""
    if not _IDENT.match(table):
        raise ValueError(f"invalid table name {table!r}")
    privileges = (
        "SELECT, INSERT" if append_only or table in APPEND_ONLY_TABLES else "SELECT, INSERT, UPDATE, DELETE"
    )
    op.execute(f"GRANT {privileges} ON {table} TO tcms_app")
    op.execute(f"GRANT SELECT ON {table} TO tcms_readonly")
