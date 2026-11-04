"""US-003: the database enforces immutability (BR-01, BR-06, BR-26; docs/05 §4).

Runs as tcms_app inside a rolled-back transaction. 99_verify.sql covers the same invariants in SQL;
these tests keep them in the pytest suite with BR-named tests (docs/08 §6.5).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def fx(db_session: Session) -> dict[str, str]:
    """Org, project, folder, case with v1 (one step), cycle, run and a draft attempt."""
    ids = {
        k: _id()
        for k in ("org", "user", "project", "env", "folder", "case", "v1", "s1", "cycle", "run", "res")
    }
    s = db_session
    s.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:org, 'ACME', :slug)"),
        {**ids, "slug": "o" + ids["org"][:8]},
    )
    s.execute(
        text("INSERT INTO users (id, email, display_name) VALUES (:user, :email, 'Sana')"),
        {**ids, "email": f"{ids['user']}@t.test"},
    )
    s.execute(
        text(
            "INSERT INTO projects (id, organization_id, key, name) VALUES (:project, :org, 'SPARK', 'SPARK')"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO environments (id, organization_id, project_id, name) VALUES (:env, :org, :project, 'QA')"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO folders (id, organization_id, project_id, name, path, depth) VALUES (:folder, :org, :project, 'F', :path, 1)"
        ),
        {**ids, "path": f"/{ids['folder']}/"},
    )
    s.execute(
        text(
            "INSERT INTO test_cases (id, organization_id, project_id, key_num, key, folder_id, title, status, owner_id, latest_version_id)"
            " VALUES (:case, :org, :project, 1, 'SPARK-TC-1', :folder, 'Login', 'approved', :user, :v1)"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO test_case_versions (id, organization_id, project_id, test_case_id, version_no, format, title, content_hash, created_by)"
            " VALUES (:v1, :org, :project, :case, 1, 'steps', 'Login', '\\x01', :user)"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO test_case_steps (id, organization_id, project_id, version_id, position, action) VALUES (:s1, :org, :project, :v1, 1, 'Open')"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO test_cycles (id, organization_id, project_id, key_num, key, name, environment_id, owner_id)"
            " VALUES (:cycle, :org, :project, 1, 'SPARK-CY-1', 'Cycle', :env, :user)"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO test_runs (id, organization_id, project_id, cycle_id, test_case_id, test_case_version_id, position)"
            " VALUES (:run, :org, :project, :cycle, :case, :v1, 1)"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, executed_by, environment_id)"
            " VALUES (:res, :org, :project, :run, 1, :user, :env)"
        ),
        ids,
    )
    s.execute(
        text(
            "INSERT INTO test_step_results (id, organization_id, project_id, result_id, step_id, position, status)"
            " VALUES (:sr, :org, :project, :res, :s1, 1, 'passed')"
        ),
        {**ids, "sr": _id()},
    )
    s.flush()
    return ids


def _expect_db_error(session: Session, sql: str, params: dict[str, str], match: str) -> None:
    with pytest.raises(DBAPIError, match=match), session.begin_nested():
        session.execute(text(sql), params)


def test_br_06_final_result_immutable_sql(db_session: Session, fx: dict[str, str]) -> None:
    """AC-EXE-04: a finalized attempt and its step results cannot be updated or deleted."""
    db_session.execute(
        text("UPDATE test_results SET state='final', status='passed', finished_at=now() WHERE id=:res"), fx
    )
    _expect_db_error(db_session, "UPDATE test_results SET comment='x' WHERE id=:res", fx, "immutable_record")
    _expect_db_error(db_session, "DELETE FROM test_results WHERE id=:res", fx, "immutable_record")
    _expect_db_error(
        db_session,
        "UPDATE test_step_results SET status='failed' WHERE result_id=:res",
        fx,
        "immutable_record",
    )
    _expect_db_error(db_session, "DELETE FROM test_step_results WHERE result_id=:res", fx, "immutable_record")


def test_br_06_draft_result_is_editable(db_session: Session, fx: dict[str, str]) -> None:
    db_session.execute(text("UPDATE test_step_results SET actual_result='ok' WHERE result_id=:res"), fx)
    db_session.execute(text("UPDATE test_results SET comment='draft note' WHERE id=:res"), fx)


def test_br_01_version_content_immutable_sql(db_session: Session, fx: dict[str, str]) -> None:
    _expect_db_error(
        db_session, "UPDATE test_case_versions SET title='changed' WHERE id=:v1", fx, "immutable_record"
    )
    _expect_db_error(
        db_session, "UPDATE test_case_steps SET action='changed' WHERE id=:s1", fx, "immutable_record"
    )
    _expect_db_error(db_session, "DELETE FROM test_case_versions WHERE id=:v1", fx, "immutable_record")


def test_br_01_approval_columns_settable_once(db_session: Session, fx: dict[str, str]) -> None:
    db_session.execute(
        text(
            "UPDATE test_case_versions SET approved_by=:user, approved_at=now(), approval_mode='manual' WHERE id=:v1"
        ),
        fx,
    )
    _expect_db_error(
        db_session,
        "UPDATE test_case_versions SET approved_at=now() + interval '1 day' WHERE id=:v1",
        fx,
        "already set",
    )


def test_br_26_audit_append_only_sql(db_session: Session, fx: dict[str, str]) -> None:
    params = {**fx, "aid": _id()}
    db_session.execute(
        text(
            "INSERT INTO audit_events (id, organization_id, actor_type, action, entity_type) VALUES (:aid, :org, 'system', 'test.created', 'test')"
        ),
        params,
    )
    for sql in (
        "UPDATE audit_events SET summary='x' WHERE id=:aid",
        "DELETE FROM audit_events WHERE id=:aid",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), db_session.begin_nested():
            db_session.execute(text(sql), params)


def test_br_07_single_draft_per_run(db_session: Session, fx: dict[str, str]) -> None:
    _expect_db_error(
        db_session,
        "INSERT INTO test_results (id, organization_id, project_id, run_id, attempt_no, executed_by, environment_id)"
        " VALUES (gen_random_uuid(), :org, :project, :run, 2, :user, :env)",
        fx,
        "ux_test_results__run_draft",
    )
