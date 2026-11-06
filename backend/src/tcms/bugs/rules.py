"""Pure bug-link rules (docs/02 §8; ADR-023). Bugs live in the team's tracker; Assay stores references."""

from __future__ import annotations

from dataclasses import dataclass

from tcms.core.errors import FieldError
from tcms.core.references import (
    REFERENCE_MAX,
    TITLE_MAX,
    URL_MAX,
    build_url,
    clean_title,
    link_url,
    normalize_reference,
    reference_norm,
    reference_problem,
    title_problem,
    url_problem,
)

__all__ = [
    "REFERENCE_MAX",
    "TITLE_MAX",
    "URL_MAX",
    "build_url",
    "clean_title",
    "link_problems",
    "link_url",
    "normalize_reference",
    "reference_norm",
    "reference_problem",
    "title_problem",
    "url_problem",
]


def link_problems(reference: str, url: str | None, title: str | None) -> list[FieldError]:
    return [p for p in (reference_problem(reference), url_problem(url), title_problem(title)) if p]


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
