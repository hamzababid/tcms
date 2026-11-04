"""`tcms` command-line interface (docs/04 §1): migrate, worker, seed, openapi."""

from __future__ import annotations

import json
import signal
import sys
from pathlib import Path
from types import FrameType

import click

from tcms.core.config import get_settings
from tcms.core.logging import configure_logging


@click.group()
def main() -> None:
    """Assay backend commands."""


@main.command()
def migrate() -> None:
    """Apply database migrations (alembic upgrade head) as the schema owner."""
    from alembic import command
    from alembic.config import Config

    settings = get_settings()
    cfg = Config(str(settings.migrations_path.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(settings.migrations_path))
    command.upgrade(cfg, "head")
    click.echo("migrations: at head")


@main.command()
def worker() -> None:
    """Run background jobs and the scheduler."""
    from tcms.core.db import app_engine, session_factory
    from tcms.main import install_modules
    from tcms.platform.jobs.worker import Worker

    settings = get_settings()
    configure_logging(settings.log_level)
    install_modules()
    from tcms.platform import attachments, storage

    attachments.configure_gc(attachments.Storage(storage.make_client(settings), settings.s3_bucket))
    w = Worker(
        session_factory(app_engine(settings, worker=True)),
        concurrency=settings.worker_concurrency,
        poll_interval=settings.worker_poll_interval_seconds,
    )

    def _stop(signum: int, frame: FrameType | None) -> None:
        w.stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    w.run()


@main.command()
@click.option("--org", "org_name", required=True, help="Organization name, e.g. 'ACME Energy'")
@click.option("--slug", required=True, help="Immutable organization slug, e.g. 'acme'")
@click.option("--admin-email", required=True, help="Email of the first Org Admin")
def bootstrap(org_name: str, slug: str, admin_email: str) -> None:
    """Create the first organization and print a one-time setup link for its admin (US-020)."""
    from tcms.core.db import app_engine, session_factory
    from tcms.core.uow import unit_of_work
    from tcms.identity import service as identity
    from tcms.main import install_modules
    from tcms.workspace import service as workspace

    settings = get_settings()
    install_modules()
    with unit_of_work(session_factory(app_engine(settings))) as uow:
        org = workspace.create_organization(uow, name=org_name, slug=slug)
        created = identity.bootstrap_admin_invitation(
            uow, settings, organization_id=org.id, email=admin_email
        )
    click.echo(f"organization {org.name} ({org.slug}) created")
    click.echo(f"one-time setup link for {admin_email} (valid 7 days):")
    click.echo(created.accept_url)


@main.command("storage-init")
def storage_init() -> None:
    """Create the attachments bucket if it does not exist (local/dev object storage)."""
    from botocore.exceptions import ClientError

    from tcms.platform import storage

    settings = get_settings()
    client = storage.make_client(settings)
    try:
        storage.check_bucket(client, settings.s3_bucket)
        click.echo(f"storage: bucket {settings.s3_bucket} exists")
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)
        click.echo(f"storage: bucket {settings.s3_bucket} created")


@main.command()
@click.option("--profile", type=click.Choice(["dev", "e2e", "large"]), default="dev", show_default=True)
def seed(profile: str) -> None:
    """Load demo data for local development (never in production)."""
    from tcms.seed import run

    settings = get_settings()
    if settings.is_production:
        raise click.ClickException("seeding is disabled in production")
    configure_logging(settings.log_level)
    from tcms.main import install_modules

    install_modules()
    for line in run(profile):
        click.echo(line)


@main.command()
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), default=None)
def openapi(output: Path | None) -> None:
    """Print (or write) the OpenAPI document."""
    from tcms.main import create_app

    doc = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(doc)
    else:
        output.write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    main()
