"""Pure bug-link rules (docs/02 §8; ADR-023). Bugs live in the team's tracker; Assay stores references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote, urlsplit

from tcms.core.errors import FieldError

REFERENCE_MAX: Final = 100
URL_MAX: Final = 2000
TITLE_MAX: Final = 255
_REFERENCE_RE: Final = re.compile(r"^\S{1,100}$")
_CONTROL_RE: Final = re.compile(r"[\x00-\x1f\x7f]")


def normalize_reference(raw: str) -> str:
    """What the team writes (`SPK-431`, `#1287`, `AB#5521`), trimmed. Compared upper-cased."""
    return raw.strip()


def reference_norm(reference: str) -> str:
    return normalize_reference(reference).upper()


def reference_problem(reference: str) -> FieldError | None:
    ref = normalize_reference(reference)
    if not ref:
        return FieldError("reference", "field_required", "Enter the bug's reference, e.g. SPK-431")
    if len(ref) > REFERENCE_MAX or not _REFERENCE_RE.match(ref) or _CONTROL_RE.search(ref):
        return FieldError("reference", "invalid_format", f"Up to {REFERENCE_MAX} characters, no spaces")
    return None


def url_problem(url: str | None) -> FieldError | None:
    """AC-BUG-05: only http(s) addresses with a host are stored and rendered."""
    if url is None or url == "":
        return None
    msg = "Use an address starting with http:// or https://"
    if len(url) > URL_MAX or _CONTROL_RE.search(url) or any(c.isspace() for c in url):
        return FieldError("url", "invalid_format", msg)
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return FieldError("url", "invalid_format", msg)
    return None


def title_problem(title: str | None) -> FieldError | None:
    if title is not None and len(title.strip()) > TITLE_MAX:
        return FieldError("title", "invalid_length", f"At most {TITLE_MAX} characters")
    return None


def link_problems(reference: str, url: str | None, title: str | None) -> list[FieldError]:
    return [p for p in (reference_problem(reference), url_problem(url), title_problem(title)) if p]


def build_url(template: str | None, reference: str) -> str | None:
    """AC-BUG-02: `{ref}` in the project template, URL-encoded (`#1287` → `%231287`)."""
    if not template:
        return None
    return template.replace("{ref}", quote(normalize_reference(reference), safe="-._~"))


def link_url(given: str | None, template: str | None, reference: str) -> str | None:
    """A given URL is kept as given; otherwise the template builds one (stored, not recomputed)."""
    given = (given or "").strip()
    return given or build_url(template, reference)


def clean_title(title: str | None) -> str | None:
    return (title or "").strip() or None


# -- "Copy bug details" (docs/02 §8.2) ------------------------------------------------------------


@dataclass(frozen=True)
class ReportStep:
    position: int
    action: str
    data: str | None
    expected: str | None
    status: str
    actual: str | None


@dataclass(frozen=True)
class ReportInput:
    case_key: str
    case_title: str
    version_no: int
    preconditions: str | None
    test_data: str | None
    steps: list[ReportStep]
    text_body: str | None
    cycle_key: str
    cycle_name: str
    environment: str
    build: str | None
    attempt_no: int
    attempt_status: str | None
    attempt_comment: str | None
    run_url: str


def bug_report(data: ReportInput, step_position: int | None) -> str:
    """Markdown to paste into the tracker: steps 1..n of the pinned version, expected and actual of step n
    (or of the first failed step, or the whole attempt for text cases)."""
    steps = data.steps
    target = next((st for st in steps if st.position == step_position), None) if step_position else None
    if target is None and step_position is None:
        target = next((st for st in steps if st.status == "failed"), None)
    shown = [st for st in steps if target is None or st.position <= target.position]
    lines = [f"**{data.case_key} – {data.case_title}** (v{data.version_no})", ""]
    if data.preconditions:
        lines += ["**Preconditions**", data.preconditions.strip(), ""]
    if data.test_data:
        lines += ["**Test data**", data.test_data.strip(), ""]
    if shown:
        lines.append("**Steps to reproduce**")
        for st in shown:
            line = f"{st.position}. {st.action.strip()}"
            if st.data:
                line += f" (data: {st.data.strip()})"
            lines.append(line)
        lines.append("")
    elif data.text_body:
        lines += ["**Test**", data.text_body.strip(), ""]
    expected = target.expected if target else None
    actual = (target.actual if target else None) or (data.attempt_comment if target is None else None)
    if expected:
        lines += ["**Expected**", expected.strip(), ""]
    if actual:
        lines += ["**Actual**", actual.strip(), ""]
    status = (data.attempt_status or "in progress").replace("_", " ")
    lines += [
        f"**Environment:** {data.environment}" + (f" · build {data.build}" if data.build else ""),
        f"**Cycle:** {data.cycle_key} – {data.cycle_name} · attempt {data.attempt_no} ({status})",
        f"**Run:** {data.run_url}",
    ]
    return "\n".join(lines)
