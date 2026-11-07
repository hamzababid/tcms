"""M7b — in-app notifications and email (docs/02 §2.7; M7 D11–D13): AC-NTF-01…03, US-170, US-171."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tcms.core import clock, ids
from tcms.core.uow import unit_of_work
from tcms.platform.jobs.worker import run_one
from tests.api.test_attempts import Exec, _done
from tests.api.test_execution import _rows
from tests.world import World

pytestmark = pytest.mark.integration


def _assign(ex: Exec, user: Any, n: int = 1) -> str:
    cases = [str(ex.case(f"Notify case {i} {ids.new_id().hex[-6:]}")[0]) for i in range(n)]
    cid = ex.create_cycle(name=f"Notify {ids.new_id().hex[-6:]}", selection={"case_ids": cases})["cycle"][
        "id"
    ]
    runs = [r["id"] for r in ex.runs(cid)]
    r = ex.admin.post(
        f"/api/v1/cycles/{cid}/runs/assign", json={"run_ids": runs, "assignee_id": str(user.id)}
    )
    assert r.status_code == 200, r.text
    return str(cid)


def _emails(world: World, template: str, to: str) -> list[dict[str, Any]]:
    rows = _rows(world, "SELECT payload FROM jobs WHERE type = 'email.send'")
    return [p for (p,) in rows if p.get("template") == template and p.get("to") == to]


def _drain(world: World) -> None:
    """Run queued jobs except email.send (no SMTP in tests); emails stay queued for inspection."""
    with world.factory() as s:
        s.execute(text("UPDATE jobs SET run_at = now() + interval '1 day' WHERE type = 'email.send'"))
        s.commit()
    while run_one(world.factory, "test-worker"):
        with world.factory() as s:
            s.execute(text("UPDATE jobs SET run_at = now() + interval '1 day' WHERE type = 'email.send'"))
            s.commit()


def test_ac_ntf_01_us_170_bell_count_list_and_mark_read(world: World) -> None:
    ex = Exec(world)
    _assign(ex, ex.sana_user, 2)
    _assign(ex, ex.sana_user, 1)
    assert ex.sana.get("/api/v1/me/notifications/unread-count").json() == {"count": 2}
    page = ex.sana.get("/api/v1/me/notifications").json()
    assert (page["total"], page["unread"]) == (2, 2)
    newest, older = page["items"]
    assert newest["title"].startswith("1 run assigned to you in SPARK-CY-")
    assert older["title"].startswith("2 runs assigned to you in SPARK-CY-")
    assert newest["url"].startswith("/p/SPARK/cycles/SPARK-CY-")
    assert newest["project_key"] == "SPARK"
    r = ex.sana.post("/api/v1/me/notifications/read", json={"ids": [newest["id"]]})
    assert r.json() == {"updated": 1, "unread": 1}
    assert [
        n["id"] for n in ex.sana.get("/api/v1/me/notifications", params={"unread": True}).json()["items"]
    ] == [older["id"]]
    assert (
        ex.omar.post("/api/v1/me/notifications/read", json={"ids": [older["id"]]}).json()["updated"] == 0
    ), "only my own notifications"
    assert ex.sana.post("/api/v1/me/notifications/read", json={"all": True}).json() == {
        "updated": 1,
        "unread": 0,
    }
    assert ex.sana.post("/api/v1/me/notifications/read", json={}).status_code == 422
    assert ex.omar.get("/api/v1/me/notifications").json()["total"] == 0


def test_l33_ready_for_retest_notifies_the_assignee(world: World) -> None:
    ex = Exec(world)
    cid = _assign(ex, ex.sana_user, 2)
    runs = [r["id"] for r in ex.runs(cid)]
    for run_id in runs:
        res = _done(ex.sana, run_id, "failed")
        ex.sana.post(f"/api/v1/results/{res['result']['id']}/bug-links", json={"reference": "SPK-77"})
    ex.sana.post("/api/v1/me/notifications/read", json={"all": True})
    r = ex.bilal.post(ex.purl("/bugs/retest"), json={"reference": "SPK-77", "dry_run": False})
    assert r.status_code == 200, r.text
    (n,) = ex.sana.get("/api/v1/me/notifications", params={"unread": True}).json()["items"]
    assert n["type"] == "bug.retest_requested"
    assert "flagged 2 runs of yours" in n["title"]
    assert "SPK-77" in n["title"]


def test_ac_ntf_02_mention_email_and_opt_out(world: World, clean_jobs: None) -> None:
    ex = Exec(world)
    case_id, _ = ex.case("Mention me")
    body = f"Please check @[Sana](user:{ex.sana_user.id})"
    assert (
        ex.bilal.post(
            "/api/v1/comments", json={"entity_type": "test_case", "entity_id": str(case_id), "body": body}
        ).status_code
        == 201
    )
    _drain(world)
    (mail,) = _emails(world, "mention", ex.sana_user.email)
    assert mail["context"]["title"] == "Bilal mentioned you on SPARK-TC-1"
    assert mail["context"]["url"].endswith("/p/SPARK/cases/SPARK-TC-1"), "absolute link from TCMS_BASE_URL"
    prefs = ex.sana.patch("/api/v1/me/notification-preferences", json={"mentions": False})
    assert prefs.json() == {"mentions": False, "digest": True}
    assert ex.sana.get("/api/v1/me/notification-preferences").json() == {"mentions": False, "digest": True}
    ex.bilal.post(
        "/api/v1/comments", json={"entity_type": "test_case", "entity_id": str(case_id), "body": body}
    )
    _drain(world)
    assert len(_emails(world, "mention", ex.sana_user.email)) == 1, "opted out: no second email"
    assert ex.sana.get("/api/v1/me/notifications/unread-count").json()["count"] == 2, "in-app stays"
    acts = [
        a
        for (a,) in _rows(
            world, "SELECT action FROM audit_events WHERE entity_id = :u", u=str(ex.sana_user.id)
        )
    ]
    assert "user.updated" in acts


def test_ac_ntf_03_daily_digest_at_seven_local_time(world: World, clean_jobs: None) -> None:
    from tcms.notifications.jobs import send_digests

    ex = Exec(world)
    _assign(ex, ex.sana_user, 3)

    def digest_at(at: datetime) -> None:
        with clock.frozen(at), unit_of_work(world.factory) as uow:
            send_digests(None, uow)  # type: ignore[arg-type]

    now = clock.now()
    seven = now.replace(hour=7, minute=10, second=0, microsecond=0)
    if seven < now:
        seven += timedelta(days=1)
    digest_at(seven.replace(hour=6))  # not 07:xx in Sana's time zone (UTC)
    assert _emails(world, "digest", ex.sana_user.email) == []
    digest_at(seven)
    (mail,) = _emails(world, "digest", ex.sana_user.email)
    assert mail["context"]["total"] == 3
    assert mail["context"]["items"][0]["title"].startswith("3 runs assigned to you in SPARK-CY-")
    digest_at(seven + timedelta(minutes=30))
    assert len(_emails(world, "digest", ex.sana_user.email)) == 1, "once a day"
    digest_at(seven + timedelta(days=1))
    assert len(_emails(world, "digest", ex.sana_user.email)) == 1, "nothing new: no email"
    _assign(ex, ex.sana_user, 1)
    ex.sana.patch("/api/v1/me/notification-preferences", json={"digest": False})
    digest_at(seven + timedelta(days=2))
    assert len(_emails(world, "digest", ex.sana_user.email)) == 1, "opted out"


def test_templates_render_with_the_brand_header() -> None:
    from tcms.platform.email import render

    subject, txt, html = render(
        "digest",
        {
            "display_name": "Sana",
            "items": [{"title": "2 runs assigned", "url": "https://x/p"}],
            "total": 2,
            "url": "https://x",
        },
        "Assay",
        "https://x",
    )
    assert subject == "Your Assay runs for today"
    assert "2 runs were assigned" in txt
    assert '<a href="https://x/p">2 runs assigned</a>' in html
    assert "assay-logo-64h.png" in html
    subject, txt, _ = render(
        "mention", {"display_name": "Sana", "title": "Bilal mentioned you", "url": "https://x"}, "Assay"
    )
    assert subject == "You were mentioned in Assay"
    assert "Bilal mentioned you" in txt


def test_old_notifications_are_purged(world: World) -> None:
    from tcms.platform.notifications import cleanup

    ex = Exec(world)
    _assign(ex, ex.sana_user)
    with world.factory() as s:
        s.execute(
            text("UPDATE notifications SET created_at = :t WHERE user_id = :u"),
            {"t": datetime.now(UTC) - timedelta(days=181), "u": str(ex.sana_user.id)},
        )
        s.commit()
    with unit_of_work(world.factory) as uow:
        cleanup(None, uow)  # type: ignore[arg-type]
    assert ex.sana.get("/api/v1/me/notifications").json()["total"] == 0
