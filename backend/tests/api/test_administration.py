"""Administration API (M8b; docs/06 §4.2, §4.12): audit log, access review (TCMS-133), members with
project roles, system status and jobs (TCMS-139), audit retention (US-166)."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any
from uuid import UUID

import pytest
from openpyxl import load_workbook
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from tcms.core.uow import unit_of_work
from tcms.platform.jobs.queue import JobInfo
from tcms.workspace import access_review, retention
from tests.world import World

pytestmark = pytest.mark.integration


def _csv(body: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))


def _insert_event(
    engine: Engine, org_id: UUID, *, days_ago: int, action: str = "test.old", project_id: UUID | None = None
) -> UUID:
    event_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO audit_events (id, occurred_at, organization_id, project_id, actor_type, action,"
                " entity_type, context, summary) VALUES (:id, now() - make_interval(days => :d), :org, :p,"
                " 'system', :a, 'organization', '{}', 'Inserted by a test')"
            ),
            {"id": event_id, "d": days_ago, "org": org_id, "p": project_id, "a": action},
        )
    return event_id


def _insert_job(engine: Engine, org_id: UUID | None, status: str, error: str | None = None) -> UUID:
    job_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO jobs (id, organization_id, type, payload, status, run_at, attempts, max_attempts,"
                " last_error, created_at, finished_at) VALUES (:id, :org, 'probe.noop', '{\"secret\": 1}',"
                " :st, now(), 5, 5, :err, now(), now())"
            ),
            {"id": job_id, "org": org_id, "st": status, "err": error},
        )
    return job_id


def test_tcms_133_access_review_one_row_per_user_and_scope(world: World) -> None:
    org = world.org("Review org")
    pid = world.project(org, "REV")
    team = world.team(org, pid)
    admin = world.login(org.admin)

    rows = admin.get("/api/v1/organization/access-review").json()
    by_user: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_user.setdefault(r["email"], []).append(r)
    engineer = by_user[team["qa_engineer"].email]
    assert [r["role_code"] for r in engineer] == ["org_member", "qa_engineer"]
    assert engineer[1]["project_key"] == "REV"
    assert engineer[1]["granted_at"]
    assert engineer[1]["granted_by"] == "Admin"
    assert {r["mfa_enrolled"] for r in engineer} == {False}
    admin_rows = by_user[org.admin.email]
    assert admin_rows[0]["role_code"] == "org_admin"
    assert admin_rows[0]["mfa_enrolled"] is True
    # The creator of a project becomes its QA Manager (BR-22).
    assert [r["role_code"] for r in admin_rows[1:]] == ["qa_manager"]

    out = admin.get("/api/v1/organization/access-review?format=csv")
    assert out.status_code == 200
    assert out.headers["content-type"].startswith("text/csv")
    assert "attachment" in out.headers["content-disposition"]
    table = _csv(out.content)
    assert table[0] == access_review.HEADER
    assert len(table) == len(rows) + 1
    engineer_csv = [line for line in table if line[0] == team["qa_engineer"].email]
    assert engineer_csv[0][5] == "(organization)"
    assert engineer_csv[1][5] == "REV · REV project"

    xlsx = admin.get("/api/v1/organization/access-review?format=xlsx")
    sheet = load_workbook(io.BytesIO(xlsx.content), read_only=True).active
    assert sheet is not None
    assert [c for c in next(sheet.iter_rows(values_only=True))] == access_review.HEADER

    # Exports are audited; the JSON preview is not.
    events = admin.get("/api/v1/organization/audit-events?action=export.created").json()["items"]
    assert sorted(e["context"]["format"] for e in events) == ["csv", "xlsx"]

    # Deactivated users stay in the review.
    assert admin.post(f"/api/v1/organization/members/{team['viewer'].id}/deactivate").status_code == 204
    viewer = [
        r
        for r in admin.get("/api/v1/organization/access-review").json()
        if r["user_id"] == str(team["viewer"].id)
    ]
    assert {r["active"] for r in viewer} == {False}
    assert len(viewer) == 2

    lead = world.login(team["qa_lead"])
    assert lead.get("/api/v1/organization/access-review").status_code == 403


def test_us_164_members_list_project_roles(world: World) -> None:
    org = world.org("Members org")
    a = world.project(org, "MEMA")
    b = world.project(org, "MEMB")
    u = world.user(org, "Two projects")
    world.member(org, a, u, "qa_lead")
    world.member(org, b, u, "viewer")
    admin = world.login(org.admin)
    members = {m["user"]["id"]: m for m in admin.get("/api/v1/organization/members").json()}
    roles = members[str(u.id)]["project_roles"]
    assert [(r["project_key"], r["role_code"]) for r in roles] == [("MEMA", "qa_lead"), ("MEMB", "viewer")]
    assert members[str(u.id)]["projects"] == 2


def test_us_162_audit_log_filters_csv_and_project_scope(world: World, app_engine: Engine) -> None:
    org = world.org("Audit org")
    a = world.project(org, "AUDA")
    b = world.project(org, "AUDB")
    world.folder(org, a, "Folder in A")
    world.folder(org, b, "Folder in B")
    admin = world.login(org.admin)

    page = admin.get("/api/v1/organization/audit-events?page_size=200").json()
    assert page["total"] == len(page["items"]) > 0
    keys = {e["project_key"] for e in page["items"]}
    assert {"AUDA", "AUDB", None} <= keys
    created = [e for e in page["items"] if e["action"] == "folder.created" and e["project_key"] == "AUDA"]
    assert created
    assert created[0]["entity_key"] == "Folder in A"
    assert "request_id" in created[0]["context"]

    only_a = admin.get(f"/api/v1/organization/audit-events?project_id={a}&entity_type=folder").json()
    assert {e["project_key"] for e in only_a["items"]} == {"AUDA"}
    inverted = admin.get(
        "/api/v1/organization/audit-events?occurred_at__gte=2026-02-02&occurred_at__lte=2026-02-01"
    )
    assert inverted.status_code == 200
    assert inverted.json()["total"] == 0

    # The project log holds only that project's events, including admin-access markers the feed hides.
    proj = admin.get(f"/api/v1/projects/{b}/audit-events?page_size=200").json()
    assert proj["items"]
    assert {e["project_id"] for e in proj["items"]} == {str(b)}
    assert any(e["entity_key"] == "Folder in B" for e in proj["items"])

    out = admin.get(f"/api/v1/projects/{b}/audit-events?format=csv&entity_type=folder")
    table = _csv(out.content)
    assert table[0][:5] == ["When", "Project", "Actor", "Actor type", "Action"]
    assert [line[6] for line in table[1:]] == ["Folder in B"]
    assert table[1][1] == "AUDB"
    assert "AUDB-audit-log-" in out.headers["content-disposition"]

    # project.audit.view is a QA Manager permission; a QA Lead member gets 403, not the log.
    lead = world.user(org, "Lead")
    world.member(org, b, lead, "qa_lead")
    assert world.login(lead).get(f"/api/v1/projects/{b}/audit-events").status_code == 403


def test_tcms_139_dead_job_listed_and_retried(world: World, app_engine: Engine, clean_jobs: None) -> None:
    org = world.org("Jobs org")
    other = world.org("Other jobs org")
    admin = world.login(org.admin)
    dead = _insert_job(app_engine, org.id, "dead", "RuntimeError: SMTP down\n" + "x" * 5000)
    system = _insert_job(app_engine, None, "failed", "PermanentJobError: no handler")
    hidden = _insert_job(app_engine, other.id, "dead", "other org")
    _insert_job(app_engine, org.id, "succeeded")

    listed = admin.get("/api/v1/organization/jobs").json()
    ids = {j["id"] for j in listed["items"]}
    assert {str(dead), str(system)} <= ids
    assert str(hidden) not in ids
    row = next(j for j in listed["items"] if j["id"] == str(dead))
    assert row["last_error"].startswith("RuntimeError: SMTP down")
    assert len(row["last_error"]) <= 2001
    assert "payload" not in row
    assert next(j for j in listed["items"] if j["id"] == str(system))["system"] is True
    assert admin.get("/api/v1/organization/jobs?status=succeeded").json()["total"] >= 1

    status = admin.get("/api/v1/organization/system-status").json()
    assert status["version"]
    assert status["migration_current"] == status["migration_head"]
    assert all(c["ok"] for c in status["checks"].values()), status["checks"]
    assert status["jobs"]["counts"]["dead"] >= 1
    assert status["jobs"]["counts"]["failed"] >= 1
    assert status["audit_retention_years"] == 3

    retried = admin.post(f"/api/v1/organization/jobs/{dead}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempts"] == 0
    again = admin.post(f"/api/v1/organization/jobs/{dead}/retry")
    assert again.status_code == 409
    assert again.json()["code"] == "invalid_status"
    assert admin.post(f"/api/v1/organization/jobs/{hidden}/retry").status_code == 404
    events = admin.get("/api/v1/organization/audit-events?action=job.retried").json()["items"]
    assert [e["entity_key"] for e in events] == ["probe.noop"]
    assert events[0]["context"]["previous_status"] == "dead"


def test_us_166_audit_retention_purges_old_events_as_the_owner(
    world: World, app_engine: Engine, owner_engine: Engine
) -> None:
    org = world.org("Retention org")
    keeps = world.org("Long retention org")
    admin_keeps = world.login(keeps.admin)
    r = admin_keeps.get("/api/v1/organization")
    patched = admin_keeps.patch(
        "/api/v1/organization",
        json={"settings": {"audit_retention_years": 10}, "row_version": r.json()["row_version"]},
    )
    assert patched.status_code == 200, patched.text
    old = _insert_event(app_engine, org.id, days_ago=4 * 366)
    recent = _insert_event(app_engine, org.id, days_ago=2 * 365)
    kept_elsewhere = _insert_event(app_engine, keeps.id, days_ago=4 * 366)

    job = JobInfo(uuid.uuid4(), "audit.retention", {}, None, 1, 5)
    retention.configure(None)
    with pytest.raises(Exception, match="DATABASE_MAINTENANCE_URL"), unit_of_work(world.factory) as uow:
        retention.retention(job, uow)
    retention.configure(sessionmaker(bind=owner_engine, expire_on_commit=False))
    try:
        with unit_of_work(world.factory) as uow:
            retention.retention(job, uow)
    finally:
        retention.configure(None)

    with app_engine.connect() as c:
        left = set(
            c.execute(
                text("SELECT id FROM audit_events WHERE id IN (:a, :b, :c)"),
                {"a": old, "b": recent, "c": kept_elsewhere},
            ).scalars()
        )
        purged = c.execute(
            text(
                "SELECT actor_type, context FROM audit_events WHERE organization_id = :o AND action = 'audit.purged'"
            ),
            {"o": org.id},
        ).all()
        purged_elsewhere = c.execute(
            text("SELECT count(*) FROM audit_events WHERE organization_id = :o AND action = 'audit.purged'"),
            {"o": keeps.id},
        ).scalar_one()
    assert left == {recent, kept_elsewhere}
    assert len(purged) == 1
    assert str(purged[0][0]) == "system"
    assert purged[0][1]["count"] == 1
    assert purged[0][1]["before"]
    assert purged_elsewhere == 0  # nothing old enough: nothing written


@pytest.mark.parametrize(
    ("now", "years", "expected"),
    [("2030-06-15", 3, "2027-06-15"), ("2028-02-29", 1, "2027-02-28")],
)
def test_retention_cutoff_is_the_same_day_years_ago(now: str, years: int, expected: str) -> None:
    from datetime import UTC, datetime

    got = retention.cutoff(datetime.fromisoformat(now).replace(tzinfo=UTC), years)
    assert got.date().isoformat() == expected
