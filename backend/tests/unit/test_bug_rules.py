"""Bug-link rules (docs/02 §8; ADR-023): TCMS-101 validation, AC-BUG-02 URL template, AC-BUG-05 URL safety,
and the "Copy bug details" text."""

from __future__ import annotations

import pytest

from tcms.bugs import rules
from tcms.workspace.rules import bug_url_template_problem, merged_project_settings


@pytest.mark.parametrize("ref", ["SPK-431", "#1287", "AB#5521", "owner/repo#12", "x" * 100, "  SPK-1  "])
def test_tcms_101_valid_references(ref: str) -> None:
    assert rules.reference_problem(ref) is None
    assert rules.normalize_reference(ref) == ref.strip()


@pytest.mark.parametrize(
    ("ref", "code"),
    [
        ("", "field_required"),
        ("   ", "field_required"),
        ("SPK 431", "invalid_format"),
        ("x" * 101, "invalid_format"),
        ("SPK-1\u0007", "invalid_format"),
    ],
)
def test_tcms_101_invalid_references(ref: str, code: str) -> None:
    problem = rules.reference_problem(ref)
    assert problem is not None
    assert problem.code == code
    assert problem.field == "reference"


def test_reference_norm_is_case_insensitive() -> None:
    assert rules.reference_norm(" spk-431 ") == "SPK-431"


@pytest.mark.parametrize(
    "url", [None, "", "https://acme.atlassian.net/browse/SPK-431", "http://tracker.local:8080/issue/7?x=1"]
)
def test_ac_bug_05_accepted_urls(url: str | None) -> None:
    assert rules.url_problem(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "ftp://host/x",
        "data:text/html,hi",
        "https://",
        "//host/x",
        "https://a b.com",
        "https://ok.test/\n",
        "h" * 1990 + "https://x",
    ],
)
def test_ac_bug_05_rejected_urls(url: str) -> None:
    problem = rules.url_problem(url)
    assert problem is not None
    assert problem.code == "invalid_format"


def test_title_length() -> None:
    assert rules.title_problem("t" * 255) is None
    assert rules.title_problem("t" * 256) is not None
    assert rules.clean_title("  ") is None
    assert rules.clean_title(" Login ") == "Login"


def test_ac_bug_02_template_builds_and_encodes_the_url() -> None:
    template = "https://acme.atlassian.net/browse/{ref}"
    assert rules.link_url(None, template, "SPK-431") == "https://acme.atlassian.net/browse/SPK-431"
    assert rules.build_url("https://github.com/acme/app/issues/{ref}", "#12") == (
        "https://github.com/acme/app/issues/%2312"
    )
    assert rules.link_url("https://other.test/9", template, "SPK-431") == "https://other.test/9", (
        "given URL wins"
    )
    assert rules.link_url(None, None, "SPK-431") is None


@pytest.mark.parametrize(
    ("template", "ok"),
    [
        (None, True),
        ("", True),
        ("https://acme.atlassian.net/browse/{ref}", True),
        ("https://dev.azure.com/acme/_workitems/edit/{ref}/", True),
        ("https://acme.test/browse/", False),
        ("https://acme.test/{ref}/{ref}", False),
        ("javascript:{ref}", False),
        ("https://a b/{ref}", False),
    ],
)
def test_url_template_validation(template: str | None, ok: bool) -> None:
    assert (bug_url_template_problem(template) is None) is ok


def test_tracker_settings_defaults_and_clearing() -> None:
    merged = merged_project_settings({}, {})
    assert (merged["bug_tracker_name"], merged["bug_url_template"]) == ("tracker", None)
    assert merged["require_bug_link_for_failure"] is False
    cleared = merged_project_settings({"bug_url_template": "https://x.test/{ref}"}, {"bug_url_template": ""})
    assert cleared["bug_url_template"] is None


def _input(**overrides: object) -> rules.ReportInput:
    steps = [
        rules.ReportStep(1, "Open the login page", None, "The form shows", "passed", None),
        rules.ReportStep(
            2, "Sign in", "qa.user@acme.test", "The dashboard loads in 3 s", "failed", "Took 9 s"
        ),
        rules.ReportStep(3, "Open reports", None, "Reports list", "not_run", None),
    ]
    base: dict[str, object] = {
        "case_key": "SPARK-TC-12",
        "case_title": "Login",
        "version_no": 3,
        "preconditions": "User exists",
        "test_data": None,
        "steps": steps,
        "text_body": None,
        "cycle_key": "SPARK-CY-4",
        "cycle_name": "Regression",
        "environment": "QA",
        "build": "2.5.0-rc1",
        "attempt_no": 1,
        "attempt_status": "failed",
        "attempt_comment": None,
        "run_url": "http://localhost:5173/p/SPARK/cycles/SPARK-CY-4/run/abc",
    }
    base.update(overrides)
    return rules.ReportInput(**base)  # type: ignore[arg-type]


def test_bug_report_lists_steps_up_to_the_failing_one() -> None:
    text = rules.bug_report(_input(), 2)
    assert "**SPARK-TC-12 – Login** (v3)" in text
    assert "User exists" in text
    assert "1. Open the login page" in text
    assert "2. Sign in (data: qa.user@acme.test)" in text
    assert "3. Open reports" not in text
    assert "**Expected**\nThe dashboard loads in 3 s" in text
    assert "**Actual**\nTook 9 s" in text
    assert "QA · build 2.5.0-rc1" in text
    assert "attempt 1 (failed)" in text
    assert text.endswith("/run/abc")


def test_bug_report_without_step_uses_the_first_failed_step() -> None:
    assert rules.bug_report(_input(), None) == rules.bug_report(_input(), 2)


def test_bug_report_for_a_text_case_uses_the_comment() -> None:
    text = rules.bug_report(
        _input(
            steps=[], text_body="Try odd carts.", attempt_comment="Coupon applied twice", attempt_status=None
        ),
        None,
    )
    assert "**Test**\nTry odd carts." in text
    assert "**Actual**\nCoupon applied twice" in text
    assert "(in progress)" in text


def test_bug_report_with_test_data_and_nothing_failed_lists_every_step() -> None:
    passed = [rules.ReportStep(1, "Open", None, "Shown", "passed", None)]
    text = rules.bug_report(_input(steps=passed, test_data="Card 4242", build=None), None)
    assert "**Test data**\nCard 4242" in text
    assert "1. Open" in text
    assert "**Expected**" not in text
    assert "**Actual**" not in text
    assert "**Environment:** QA\n" in text


def test_bug_report_without_steps_or_text() -> None:
    text = rules.bug_report(_input(steps=[], text_body=None, preconditions=None), None)
    assert "**Steps to reproduce**" not in text
    assert "**Test**" not in text
