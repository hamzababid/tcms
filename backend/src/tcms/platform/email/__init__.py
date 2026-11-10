"""Email delivery via the `email.send` job (docs/04 §10.4). Templates: platform/email/templates."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

import structlog
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from tcms.core.config import get_settings
from tcms.core.uow import UnitOfWork
from tcms.platform.jobs.queue import JobInfo, PermanentJobError, job_handler

log = structlog.get_logger()

_env_html = Environment(
    loader=PackageLoader("tcms.platform.email", "templates"),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)
_env_text = Environment(
    loader=PackageLoader("tcms.platform.email", "templates"),
    autoescape=False,  # noqa: S701 — plain-text bodies; the HTML environment autoescapes
    undefined=StrictUndefined,
)

SUBJECTS = {
    "invitation": "You're invited to {product}",
    "password_reset": "Reset your {product} password",
    "password_changed": "Your {product} password was changed",
    "mention": "You were mentioned in {product}",
    "digest": "Your {product} runs for today",
}


def render(template: str, context: dict[str, Any], product: str, base_url: str = "") -> tuple[str, str, str]:
    if template not in SUBJECTS:
        raise PermanentJobError(f"unknown email template {template!r}")
    # PNG logo (docs/brand/png/assay-logo-64h.png, served by the web app): email clients often block SVG.
    ctx = {**context, "product": product, "logo_url": f"{base_url.rstrip('/')}/brand/assay-logo-64h.png"}
    subject = SUBJECTS[template].format(product=product)
    text = _env_text.get_template(f"{template}.txt").render(ctx)
    html = _env_html.get_template(f"{template}.html").render(ctx)
    return subject, text, html


@job_handler("email.send")
def send_email(job: JobInfo, uow: UnitOfWork) -> None:
    settings = get_settings()
    to = job.payload.get("to")
    if not isinstance(to, str) or "@" not in to:
        raise PermanentJobError("email job without a valid recipient")
    subject, text, html = render(
        str(job.payload.get("template")),
        dict(job.payload.get("context") or {}),
        settings.tcms_product_name,
        settings.tcms_base_url,
    )
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            # Verify the server's certificate and host name: without a context, smtplib accepts any
            # certificate (ASVS 12.3.2; reset links and the SMTP password travel on this connection).
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)
    log.info("email.sent", template=job.payload.get("template"), job_id=str(job.id))
