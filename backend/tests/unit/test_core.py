"""Core primitives: ids, clock, row_version, AccessContext, audit rendering, schedule buckets."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tcms.core import clock, ids
from tcms.core.concurrency import check_row_version
from tcms.core.context import AccessContext, ActorType, Principal
from tcms.core.errors import PermissionDenied, RowVersionRequired, StaleRowVersion
from tcms.core.uow import AuditRecord
from tcms.platform.audit.render import render_summary
from tcms.platform.jobs.worker import Schedule


def test_new_id_is_uuid7_and_time_ordered() -> None:
    a, b = ids.new_id(), ids.new_id()
    assert a.version == 7
    assert a < b


def test_clock_frozen() -> None:
    at = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    with clock.frozen(at):
        assert clock.now() == at
    assert clock.now() != at
    with pytest.raises(ValueError, match="timezone-aware"), clock.frozen(datetime(2026, 1, 1)):
        pass


def test_br_25_row_version_check() -> None:
    check_row_version(3, 3)
    with pytest.raises(StaleRowVersion) as exc:
        check_row_version(4, 3)
    assert exc.value.status == 409
    assert exc.value.extra["current_row_version"] == 4
    with pytest.raises(RowVersionRequired):
        check_row_version(4, None)


def test_access_context_require() -> None:
    p = Principal(user_id=uuid.uuid4(), organization_id=uuid.uuid4(), is_org_admin=False)
    ctx = AccessContext(principal=p, project_id=None, permissions=frozenset({"project.view"}), request_id="r")
    ctx.require("project.view")
    with pytest.raises(PermissionDenied) as exc:
        ctx.require("cycle.manage")
    assert exc.value.extra == {"required_permission": "cycle.manage"}


def test_fallback_audit_summary() -> None:
    record = AuditRecord(
        id=uuid.uuid4(),
        occurred_at=clock.now(),
        organization_id=uuid.uuid4(),
        project_id=None,
        actor_type=ActorType.user,
        actor_id=None,
        actor_display="Sana",
        action="test_case.version_created",
        entity_type="test_case",
        entity_id=None,
        entity_key="SPARK-TC-12",
        changes=None,
        context={},
        summary=None,
    )
    assert render_summary(record) == "Sana version created SPARK-TC-12"


def test_schedule_buckets() -> None:
    s = Schedule("x", period=timedelta(days=1), offset=timedelta(hours=3))
    day = datetime(2026, 11, 4, 2, 59, tzinfo=UTC)
    assert s.bucket(day) != s.bucket(day + timedelta(minutes=2))  # boundary at 03:00 UTC
    assert s.bucket(day + timedelta(minutes=2)) == s.bucket(day + timedelta(hours=20))
