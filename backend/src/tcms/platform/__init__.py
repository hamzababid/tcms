"""Platform services: audit, jobs, attachments, comments, notifications, saved views, transfers."""

from __future__ import annotations


def install() -> None:
    """Wire platform writers into the UnitOfWork and register platform job handlers.

    Called once by the API app factory, the worker and the CLI.
    """
    from tcms.core.uow import install_writers
    from tcms.platform.audit.recorder import write_audit
    from tcms.platform.jobs import maintenance  # noqa: F401 — registers handlers and schedules
    from tcms.platform.jobs.queue import write_jobs

    install_writers(audit=write_audit, jobs=write_jobs)
