"""Email templates render with the brand logo (docs/brand) and escape user content."""

from __future__ import annotations

import pytest

from tcms.platform.email import render
from tcms.platform.jobs.queue import PermanentJobError


def test_invitation_email_has_logo_and_link() -> None:
    subject, text, html = render(
        "invitation",
        {
            "inviter": "Zain",
            "url": "https://assay.example/invite/abc",
            "project_name": "SPARK",
            "expires_at": "2026-11-11T00:00:00Z",
        },
        "Assay",
        "https://assay.example/",
    )
    assert subject == "You're invited to Assay"
    assert '<img src="https://assay.example/brand/assay-logo-64h.png" alt="Assay"' in html
    assert "https://assay.example/invite/abc" in text
    assert "2026-11-11" in text


def test_html_escapes_user_content() -> None:
    _, _, html = render("password_changed", {"display_name": "<script>x</script>"}, "Assay", "https://a.test")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_unknown_template_is_permanent_failure() -> None:
    with pytest.raises(PermanentJobError):
        render("nope", {}, "Assay")
