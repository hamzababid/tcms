"""The migrated schema is exactly the documented baseline (M0 acceptance, TM-1, docs/05)."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import Engine, text

from tcms.core.permissions import ROLE_PERMISSIONS, SYSTEM_ROLE_IDS
from tests.conftest import OWNER_PASSWORD, Database, _alembic

pytestmark = pytest.mark.integration

APPEND_ONLY = {"audit_events", "defect_status_history", "release_decisions"}


def _normalized_dump(db: Database, dbname: str) -> str:
    result = db.container.exec(  # type: ignore[attr-defined]
        [
            "env",
            "PGPASSWORD=test",
            "pg_dump",
            "-h",
            "localhost",
            "-U",
            "postgres",
            "--schema-only",
            "--no-comments",
            "--exclude-table=alembic_version",
            dbname,
        ]
    )
    assert result.exit_code == 0, result.output.decode()
    lines = []
    for line in result.output.decode().splitlines():
        if (
            line.startswith(("--", "SET ", "SELECT pg_catalog.set_config", "\\restrict", "\\unrestrict"))
            or not line.strip()
        ):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_alembic_check_is_clean(database: Database) -> None:
    """`alembic check`: the ORM models match the migrated schema."""
    result = _alembic(database.owner_url, "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No new upgrade operations detected" in result.stdout + result.stderr


def test_migrated_schema_matches_docs_baseline(database: Database) -> None:
    """pg_dump of the Alembic-migrated DB equals a DB built directly from docs/schema/0[1-9]_*.sql."""
    database.psql("-q", "-c", "DROP DATABASE IF EXISTS tcms_reference")
    database.psql("-q", "-c", "CREATE DATABASE tcms_reference OWNER tcms_owner")
    for name in (
        "01_baseline.sql",
        "02_seed_system.sql",
        "03_m1_additions.sql",
        "04_m5_bug_links.sql",
        "05_m6_requirement_refs.sql",
    ):
        database.psql(
            "-q", "-f", f"/schema/{name}", user="tcms_owner", db="tcms_reference", password=OWNER_PASSWORD
        )
    try:
        migrated = _normalized_dump(database, "tcms")
        reference = _normalized_dump(database, "tcms_reference")
    finally:
        database.psql("-q", "-c", "DROP DATABASE tcms_reference")
    assert migrated == reference


def test_verify_sql_passes_as_app_role(database: Database) -> None:
    """docs/schema/99_verify.sql (35 invariant checks) passes as tcms_app."""
    output = database.psql(
        "-f", "/schema/99_verify.sql", user="tcms_app", db="tcms", password="change-me-app"
    )
    passes = re.findall(r"PASS ", output)
    assert "FAIL" not in output
    assert len(passes) == 35, output


def test_app_role_privileges(app_engine: Engine) -> None:
    """tcms_app has full DML on every table except INSERT/SELECT-only on append-only tables (05 §4)."""
    with app_engine.connect() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) == 55  # docs/schema/01_baseline.sql + 03_m1_additions.sql + 04/05 milestone files
        for table in tables:
            privs = {
                p: conn.execute(
                    text("SELECT has_table_privilege('tcms_app', :t, :p)"), {"t": table, "p": p}
                ).scalar_one()
                for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            if table in APPEND_ONLY:
                assert privs == {"SELECT": True, "INSERT": True, "UPDATE": False, "DELETE": False}, table
            else:
                assert all(privs.values()), (table, privs)


def test_seeded_role_permissions_match_code_registry(app_engine: Engine) -> None:
    """02_seed_system.sql and tcms.core.permissions.ROLE_PERMISSIONS describe the same matrix (G11)."""
    with app_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT r.id::text, r.code, rp.permission FROM roles r JOIN role_permissions rp ON rp.role_id = r.id"
            )
        ).all()
    seeded: dict[str, set[str]] = {}
    for role_id, code, permission in rows:
        assert SYSTEM_ROLE_IDS[code] == role_id  # type: ignore[index]
        seeded.setdefault(code, set()).add(permission)
    assert seeded == {code.value: set(perms) for code, perms in ROLE_PERMISSIONS.items()}
