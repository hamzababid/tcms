"""Alembic environment. Runs as the schema owner (DATABASE_MAINTENANCE_URL)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tcms_migrations helpers

# The ORM metadata of every module: needed for `alembic check`. Importing models here (outside the
# tcms package) keeps each module's models private to its own package (import-linter contracts).
import tcms.bugs.models
import tcms.defects.models
import tcms.execution.models
import tcms.identity.models
import tcms.planning.models
import tcms.platform.models
import tcms.reporting.models
import tcms.requirements.models
import tcms.testdesign.models
import tcms.workspace.models  # noqa: F401
from tcms.core.config import get_settings
from tcms.core.db import Base

target_metadata = Base.metadata

# Indexes Alembic cannot express or compare (expression or operator-class indexes). They exist in the
# baseline SQL and are verified by the schema diff (`make schema-check`), not by `alembic check`.
SQL_ONLY_INDEXES = frozenset(
    {
        "ux_roles__organization_id_code",
        "ux_projects__organization_id_lower_name",
        "ux_environments__project_lower_name",
        "ux_releases__project_lower_name",
        "ux_folders__project_parent_lower_name",
        "ix_folders__project_id_path",
        "ux_defect_links__target",
        "ux_bug_links__target",
        "ix_requirement_refs__reference_trgm",
        "ix_requirement_refs__title_trgm",
        "ix_bug_links__reference_trgm",
        "ix_test_cycles__name_trgm",
        "ix_test_plans__name_trgm",
        "ux_saved_views__owner_name",
        "ux_metric_snapshots__scope_day",
    }
)


def include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    if type_ == "index" and name in SQL_ONLY_INDEXES:
        return False
    return not (type_ == "table" and name == "alembic_version")


def _url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_maintenance_url


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        user = connection.execute(text("select current_user")).scalar_one()
        if user != "tcms_owner":
            raise RuntimeError(f"migrations must run as tcms_owner, not {user}")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")
run_migrations_online()
