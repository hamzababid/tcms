"""Digest timing per time zone and notification titles (docs/02 §2.7; M7 D12, D13)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from tcms.identity.queries import Recipient
from tcms.notifications.jobs import digest_due
from tcms.notifications.render import Lookups, render
from tcms.platform.notifications import NotificationView


def _person(tz: str, last: str | None = None) -> Recipient:
    return Recipient(uuid4(), "s@x.test", "Sana", tz, True, True, True, last, None)


def test_ac_ntf_03_digest_goes_out_at_seven_in_the_users_time_zone() -> None:
    at = datetime(2026, 11, 6, 2, 30, tzinfo=UTC)  # 07:30 in Karachi (UTC+5), 02:30 in London
    assert digest_due(_person("Asia/Karachi"), at) == "2026-11-06"
    assert digest_due(_person("Europe/London"), at) is None
    assert digest_due(_person("Asia/Karachi", last="2026-11-06"), at) is None, "once a day"
    assert digest_due(_person("Not/AZone"), datetime(2026, 11, 6, 7, 5, tzinfo=UTC)) == "2026-11-06", (
        "UTC fallback"
    )


def _n(
    type_: str, payload: dict[str, object], entity_type: str | None = None
) -> tuple[NotificationView, UUID]:
    pid = uuid4()
    view = NotificationView(
        uuid4(), uuid4(), uuid4(), pid, type_, entity_type, uuid4(), payload, datetime.now(UTC), None
    )
    return view, pid


def test_titles_and_links() -> None:
    n, pid = _n(
        "test_case.returned", {"key": "SPARK-TC-3", "version": 2, "by": "Bilal", "comment": "Add data"}
    )
    lk = Lookups({pid: "SPARK"}, {}, {})
    r = render(n, lk)
    assert (r.title, r.url) == ("Bilal returned SPARK-TC-3 v2: Add data", "/p/SPARK/cases/SPARK-TC-3")
    e, pid = _n("export.ready", {"title": "Cycle execution", "rows": 12000}, "data_transfer")
    r = render(e, Lookups({pid: "SPARK"}, {}, {}))
    assert r.title == "Cycle execution export is ready (12000 rows)"
    assert r.url == f"/api/v1/data-transfers/{e.entity_id}/download"
    u, pid = _n("something.new", {})
    assert render(u, Lookups({pid: "SPARK"}, {}, {})).title == "something · new"
