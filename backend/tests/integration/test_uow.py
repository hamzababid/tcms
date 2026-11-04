"""Unit of Work: audit in the same transaction (BR-26, ADR-008) and read-only GET transactions."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import InternalError
from sqlalchemy.orm import Session, sessionmaker

from tcms.core.context import AccessContext, Principal
from tcms.core.uow import AuditTarget, ReadOnlyViolation, unit_of_work

pytestmark = pytest.mark.integration


def _ctx(org_id: uuid.UUID) -> AccessContext:
    principal = Principal(
        user_id=uuid.uuid4(), organization_id=org_id, is_org_admin=False, display_name="Tester"
    )
    return AccessContext(principal=principal, project_id=None, permissions=frozenset(), request_id="req_test")


def _count(engine: Engine, sql: str, **params: object) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


def test_br_26_audit_committed_with_the_change(
    session_factory: sessionmaker[Session], app_engine: Engine
) -> None:
    org_id, entity_id = uuid.uuid4(), uuid.uuid4()
    with unit_of_work(session_factory) as uow:
        uow.session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Audit Org', :slug)"),
            {"id": org_id, "slug": f"a{org_id.hex[:12]}"},
        )
        uow.audit(
            _ctx(org_id),
            "organization.updated",
            AuditTarget("organization", entity_id),
            changes={"name": ["a", "b"]},
        )
    assert _count(app_engine, "SELECT count(*) FROM organizations WHERE id = :id", id=org_id) == 1
    with app_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT action, actor_display, context->>'request_id', summary FROM audit_events WHERE entity_id = :e"
            ),
            {"e": entity_id},
        ).one()
    assert row == ("organization.updated", "Tester", "req_test", "Tester updated organization")


def test_br_26_rolled_back_operation_leaves_no_audit(
    session_factory: sessionmaker[Session], app_engine: Engine
) -> None:
    """TCMS-132: a failure after audit was recorded leaves neither the change nor the audit row."""
    org_id, entity_id = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(RuntimeError, match="boom"), unit_of_work(session_factory) as uow:
        uow.session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Rollback Org', :slug)"),
            {"id": org_id, "slug": f"r{org_id.hex[:12]}"},
        )
        uow.audit(_ctx(org_id), "organization.updated", AuditTarget("organization", entity_id))
        raise RuntimeError("boom")
    assert _count(app_engine, "SELECT count(*) FROM organizations WHERE id = :id", id=org_id) == 0
    assert _count(app_engine, "SELECT count(*) FROM audit_events WHERE entity_id = :e", e=entity_id) == 0


def test_secrets_are_redacted_in_audit_changes(
    session_factory: sessionmaker[Session], app_engine: Engine
) -> None:
    org_id, entity_id = uuid.uuid4(), uuid.uuid4()
    with unit_of_work(session_factory) as uow:
        uow.audit(
            _ctx(org_id),
            "auth.password_changed",
            AuditTarget("user", entity_id),
            changes={"password_hash": ["x", "y"]},
        )
    with app_engine.connect() as conn:
        changes = conn.execute(
            text("SELECT changes FROM audit_events WHERE entity_id = :e"), {"e": entity_id}
        ).scalar_one()
    assert changes == {"password_hash": ["[redacted]", "[redacted]"]}


def test_read_only_uow_rejects_writes(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(ReadOnlyViolation), unit_of_work(session_factory, read_only=True) as uow:
        uow.audit(_ctx(uuid.uuid4()), "x.y", AuditTarget("x"))
    with (
        pytest.raises(InternalError, match="read-only transaction"),
        unit_of_work(session_factory, read_only=True) as uow,
    ):
        uow.session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (gen_random_uuid(), 'n', 'ro-test')")
        )
