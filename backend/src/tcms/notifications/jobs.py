"""Email delivery of notifications (docs/02 §2.7; M7 D13).

- `notifications.email`: mention emails, enqueued by `platform.notifications.notify` in the same
  transaction as the in-app row; skipped for users who opted out or are inactive.
- `notifications.digest`: hourly; at 07:xx in each user's time zone, one email listing the runs assigned
  to them since the last digest (or the last 24 h). Nothing new or opted out → no email. The dedupe key
  `digest:{user}:{local date}` and `last_digest_on` make it once a day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from tcms.core import clock
from tcms.core.config import get_settings
from tcms.core.uow import UnitOfWork
from tcms.identity import queries as identity_queries
from tcms.identity import service as identity
from tcms.notifications import render
from tcms.platform import notifications
from tcms.platform.jobs.queue import JobInfo, job_handler
from tcms.platform.jobs.worker import schedule

log = structlog.get_logger()
DIGEST_HOUR = 7


def _absolute(url: str | None) -> str:
    base = get_settings().tcms_base_url.rstrip("/")
    return f"{base}{url}" if url else base


@job_handler("notifications.email")
def send_mentions(job: JobInfo, uow: UnitOfWork) -> None:
    rows = notifications.by_ids(uow, [UUID(i) for i in job.payload.get("ids", [])])
    people = identity_queries.recipients(uow.session, {r.user_id for r in rows})
    lk = render.lookups(uow.session, rows)
    for n in rows:
        person = people.get(n.user_id)
        if person is None or not person.is_active or not person.email_mentions:
            continue
        r = render.render(n, lk)
        uow.enqueue_job(
            "email.send",
            {
                "to": person.email,
                "template": "mention",
                "context": {"display_name": person.display_name, "title": r.title, "url": _absolute(r.url)},
            },
            organization_id=n.organization_id,
            dedupe_key=f"email:mention:{n.id}",
        )


def _local_now(tz: str, now: datetime) -> datetime:
    try:
        return now.astimezone(ZoneInfo(tz))
    except (ZoneInfoNotFoundError, ValueError):
        return now.astimezone(UTC)


def digest_due(person: identity_queries.Recipient, now: datetime) -> str | None:
    """The local date to send for, or None when this hour is not 07:xx locally or today's digest went out."""
    local = _local_now(person.time_zone, now)
    if local.hour != DIGEST_HOUR:
        return None
    day = local.date().isoformat()
    return None if person.last_digest_on == day else day


@job_handler("notifications.digest")
def send_digests(job: JobInfo, uow: UnitOfWork) -> None:
    del job
    now = clock.now()
    for person in identity_queries.digest_candidates(uow.session):
        day = digest_due(person, now)
        if day is None:
            continue
        since = (
            datetime.fromisoformat(person.last_digest_at)
            if person.last_digest_at
            else now - timedelta(hours=24)
        )
        rows = notifications.of_type_since(uow, person.id, "runs.assigned", since)
        identity.mark_digest_sent(uow, person.id, local_date=day, at=now.isoformat())
        if not rows:
            continue
        lk = render.lookups(uow.session, rows)
        items = [{"title": r.title, "url": _absolute(r.url)} for r in (render.render(n, lk) for n in rows)]
        total = sum(int(n.payload.get("count", 1)) for n in rows)
        uow.enqueue_job(
            "email.send",
            {
                "to": person.email,
                "template": "digest",
                "context": {
                    "display_name": person.display_name,
                    "items": items,
                    "total": total,
                    "url": _absolute("/my-work"),
                },
            },
            organization_id=rows[0].organization_id,
            dedupe_key=f"digest:{person.id}:{day}",
        )
        log.info("notifications.digest_queued", user_id=str(person.id), runs=total)


schedule("notifications.digest", period=timedelta(hours=1), offset=timedelta(minutes=5))
