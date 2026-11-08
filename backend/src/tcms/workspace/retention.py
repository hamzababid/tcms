"""Audit retention (US-166, NFR-CMP-01, docs/02 §13.2, M8 D9).

Daily at 02:30 UTC: for every organization, audit events older than `audit_retention_years` are deleted
in batches. The append-only trigger lets only `tcms_owner` delete (docs/schema/01_baseline.sql), so the
purge runs on a separate session from `DATABASE_MAINTENANCE_URL`; the `audit.purged` event is written in
the same transaction, so a purge is never left unrecorded. Nothing is written when nothing is old enough.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tcms.core import clock
from tcms.core.context import AccessContext, Principal, RequestMeta
from tcms.core.policy import OrgPolicy
from tcms.core.uow import AuditTarget, UnitOfWork, unit_of_work
from tcms.platform.audit import retention as audit_retention
from tcms.platform.jobs.queue import JobInfo, PermanentJobError, job_handler
from tcms.platform.jobs.worker import schedule
from tcms.workspace.models import Organization

log = structlog.get_logger()

_factory: sessionmaker[Session] | None = None


def configure(factory: sessionmaker[Session] | None) -> None:
    """The worker passes a session factory on the maintenance (owner) database URL."""
    global _factory
    _factory = factory


def cutoff(now: datetime, years: int) -> datetime:
    """The same calendar day `years` ago (29 February → 28 February)."""
    try:
        return now.replace(year=now.year - years)
    except ValueError:
        return (now - timedelta(days=1)).replace(year=now.year - years)


def purge_organization(
    factory: sessionmaker[Session], org_id: UUID, org_name: str, before: datetime, *, job_id: UUID | None
) -> int:
    """Delete one organization's events older than `before`; returns how many were deleted."""
    with unit_of_work(factory) as uow:
        total = audit_retention.purge(uow.session, org_id, before)
        if total:
            _record(uow, org_id, org_name, before, total, job_id)
    return total


def _record(
    uow: UnitOfWork, org_id: UUID, org_name: str, before: datetime, count: int, job_id: UUID | None
) -> None:
    ctx = AccessContext.for_principal(
        Principal.system(org_id, "Audit retention"), RequestMeta(f"job:{job_id or 'audit.retention'}")
    )
    uow.audit(
        ctx,
        "audit.purged",
        AuditTarget("organization", org_id, org_name),
        summary=f"Audit retention deleted {count:,} events from before {before:%Y-%m-%d}",
        extra={"before": before.isoformat(), "count": count},
    )


@job_handler("audit.retention")
def retention(job: JobInfo, uow: UnitOfWork) -> None:
    if _factory is None:
        raise PermanentJobError("audit retention needs DATABASE_MAINTENANCE_URL (the worker configures it)")
    now = clock.now()
    orgs = uow.session.execute(select(Organization.id, Organization.name, Organization.settings)).all()
    for org_id, name, settings in orgs:
        years = OrgPolicy.from_settings(settings).audit_retention_years
        before = cutoff(now, years)
        n = purge_organization(_factory, org_id, name, before, job_id=job.id)
        if n:
            log.info("audit.purged", organization_id=str(org_id), count=n, before=before.isoformat())


schedule("audit.retention", period=timedelta(days=1), offset=timedelta(hours=2, minutes=30))
