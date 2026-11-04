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
    from tcms import platform
    from tcms.core.db import app_engine, session_factory
    from tcms.platform.jobs.worker import Worker

    settings = get_settings()
    configure_logging(settings.log_level)
    platform.install()
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
