"""Pure test design rules (docs/02 §5; BR-01, BR-13, BR-15, BR-17, BR-18). No I/O."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Final, Literal

from tcms.core.enums import CaseFormat, CaseStatus
from tcms.core.errors import FieldError

MAX_DEPTH: Final = 10
MAX_STEPS: Final = 100
MAX_TAGS: Final = 20
MAX_LINKS: Final = 50
MD_MAX: Final = 20_000
TAG_RE: Final = re.compile(r"^[a-z0-9._-]{1,40}$")
SYSTEM_TAGS: Final = ("smoke", "sanity", "regression")

MARKDOWN_FIELDS: Final = (
    "description",
    "preconditions",
    "test_data",
    "expected_result",
    "postconditions",
    "text_body",
)


# -- content --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StepContent:
    action: str
    expected_result: str | None = None
    data: str | None = None


@dataclass(frozen=True)
class Content:
    """The versioned part of a test case (BR-01)."""

    format: CaseFormat
    title: str
    description: str | None = None
    preconditions: str | None = None
    test_data: str | None = None
    expected_result: str | None = None
    postconditions: str | None = None
    text_body: str | None = None
    steps: tuple[StepContent, ...] = field(default_factory=tuple)


def normalize_md(value: str | None) -> str | None:
    """docs/04 §4.1: `\\r\\n` → `\\n`, trailing whitespace per line removed, outer blank lines removed."""
    if value is None:
        return None
    lines = [ln.rstrip() for ln in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    text = "\n".join(lines)
    return text or None


def normalize_content(c: Content) -> Content:
    steps = tuple(
        StepContent(
            action=normalize_md(s.action) or "",
            expected_result=normalize_md(s.expected_result),
            data=normalize_md(s.data),
        )
        for s in c.steps
    )
    if c.format is CaseFormat.text:
        steps = ()  # step data is discarded when switching to text (docs/02 §5.2)
    return Content(
        format=c.format,
        title=c.title.strip(),
        description=normalize_md(c.description),
        preconditions=normalize_md(c.preconditions),
        test_data=normalize_md(c.test_data),
        expected_result=normalize_md(c.expected_result),
        postconditions=normalize_md(c.postconditions),
        text_body=normalize_md(c.text_body),
        steps=steps,
    )


def content_problems(c: Content) -> list[FieldError]:
    """Validation of normalized content (docs/02 §5.2)."""
    problems: list[FieldError] = []
    if not 3 <= len(c.title) <= 255:
        problems.append(FieldError("content.title", "invalid_length", "Title must be 3–255 characters"))
    for f in MARKDOWN_FIELDS:
        value = getattr(c, f)
        if value is not None and len(value) > MD_MAX:
            problems.append(FieldError(f"content.{f}", "too_long", f"At most {MD_MAX:,} characters"))
    if c.format is CaseFormat.text:
        if not c.text_body:
            problems.append(FieldError("content.text_body", "required", "Text format needs a procedure"))
        return problems
    if not c.steps:
        problems.append(FieldError("content.steps", "required", "Add at least one step"))
    if len(c.steps) > MAX_STEPS:
        problems.append(FieldError("content.steps", "too_many", f"At most {MAX_STEPS} steps"))
    for i, s in enumerate(c.steps):
        if not s.action:
            problems.append(
                FieldError(f"content.steps[{i}].action", "required", f"Step {i + 1} needs an action")
            )
        elif len(s.action) > 5000:
            problems.append(FieldError(f"content.steps[{i}].action", "too_long", "At most 5,000 characters"))
        if s.expected_result is not None and len(s.expected_result) > 5000:
            problems.append(
                FieldError(f"content.steps[{i}].expected_result", "too_long", "At most 5,000 characters")
            )
        if s.data is not None and len(s.data) > 2000:
            problems.append(FieldError(f"content.steps[{i}].data", "too_long", "At most 2,000 characters"))
    return problems


def content_hash(c: Content) -> bytes:
    """docs/04 §4.1: SHA-256 over canonical JSON of the content fields."""
    doc = {
        "format": c.format.value,
        "title": c.title,
        **{f: getattr(c, f) for f in MARKDOWN_FIELDS},
        "steps": [
            {"action": s.action, "expected_result": s.expected_result, "data": s.data} for s in c.steps
        ],
    }
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).digest()


# -- status workflow (docs/02 §5.4) ---------------------------------------------------------------


@dataclass(frozen=True)
class VersionOutcome:
    status: CaseStatus
    auto_approve: bool  # approve this version immediately (approval disabled)


def status_for_new_case(approval_required: bool) -> VersionOutcome:
    return (
        VersionOutcome(CaseStatus.draft, False)
        if approval_required
        else VersionOutcome(CaseStatus.approved, True)
    )


def status_after_new_version(current: CaseStatus, approval_required: bool) -> VersionOutcome:
    """docs/04 §4.3 (BR-17): approval off → auto-approved; on → approved/deprecated go back to draft."""
    if not approval_required:
        return VersionOutcome(current if current is CaseStatus.deprecated else CaseStatus.approved, True)
    if current in (CaseStatus.approved, CaseStatus.deprecated):
        return VersionOutcome(CaseStatus.draft, False)
    return VersionOutcome(current, False)  # draft stays draft; in_review stays in_review


Action = Literal["submit", "approve", "return", "deprecate", "archive", "restore"]


def transition_allowed(action: Action, status: CaseStatus, *, approval_required: bool) -> bool:
    if action == "submit":
        return approval_required and status is CaseStatus.draft
    if action in ("approve", "return"):
        return approval_required and status is CaseStatus.in_review
    if action == "deprecate":
        return status is CaseStatus.approved
    if action == "archive":
        return status is not CaseStatus.archived
    return status in (CaseStatus.deprecated, CaseStatus.archived)  # restore


def status_after_restore(*, approval_required: bool, latest_is_approved: bool) -> CaseStatus:
    """No previous status is stored: approved when the latest version is approved (or approval is off)."""
    if not approval_required or latest_is_approved:
        return CaseStatus.approved
    return CaseStatus.draft


def self_approval_blocked(*, author_id: object, approver_id: object, allow_self_approval: bool) -> bool:
    """BR-18."""
    return author_id == approver_id and not allow_self_approval


def status_when_approval_toggled(status: CaseStatus, *, now_required: bool) -> tuple[CaseStatus, bool]:
    """US-067: turning approval on grandfathers cases (no change); turning it off auto-approves
    draft/in_review cases at their latest version. Returns (status, approve_latest)."""
    if not now_required and status in (CaseStatus.draft, CaseStatus.in_review):
        return CaseStatus.approved, True
    return status, False


# -- folders (docs/02 §5.1, BR-15) ----------------------------------------------------------------


def folder_name_problem(name: str) -> FieldError | None:
    if not 1 <= len(name) <= 120:
        return FieldError("name", "invalid_length", "1–120 characters")
    if "/" in name:
        return FieldError("name", "invalid_character", "Folder names cannot contain /")
    return None


def child_path(parent_path: str | None, folder_id: object) -> str:
    return f"{parent_path or '/'}{folder_id}/"


def move_problem(
    *, source_path: str, source_depth: int, subtree_max_depth: int, target_path: str | None, target_depth: int
) -> Literal["cycle", "too_deep"] | None:
    """AC-TD-01/02: no move into the own subtree; the whole subtree must stay within depth 10."""
    if target_path is not None and target_path.startswith(source_path):
        return "cycle"
    new_depth = target_depth + 1
    if new_depth + (subtree_max_depth - source_depth) > MAX_DEPTH:
        return "too_deep"
    return None


# -- tags, keys, links ----------------------------------------------------------------------------


def tag_problems(tags: list[str]) -> list[FieldError]:
    problems = [
        FieldError("tags", "invalid_tag", f"'{t}': 1–40 of a-z 0-9 . _ -")
        for t in tags
        if not TAG_RE.match(t)
    ]
    if len(set(tags)) > MAX_TAGS:
        problems.append(FieldError("tags", "too_many", f"At most {MAX_TAGS} tags per case"))
    return problems


def automation_key_problems(keys: list[str]) -> list[FieldError]:
    problems = [
        FieldError("automation_keys", "invalid_length", "Each key is 1–500 characters")
        for k in keys
        if not 1 <= len(k) <= 500
    ]
    if len(set(keys)) != len(keys):
        problems.append(FieldError("automation_keys", "duplicate", "Keys must be unique"))
    return problems


def duplicate_title(title: str, *, same_folder: bool) -> str:
    """docs/02 §5.5: "Copy of " prefix unless the copy goes to another folder."""
    if not same_folder:
        return title
    return ("Copy of " + title)[:255]


def ordered_pair(a: object, b: object) -> tuple[object, object]:
    """'related' links are stored once with source < target (05 §3.3)."""
    return (a, b) if str(a) < str(b) else (b, a)


# -- compare (FR-TD-004, AC-TD-12) ----------------------------------------------------------------


@dataclass(frozen=True)
class FieldDiff:
    field: str
    before: str | None
    after: str | None

    @property
    def changed(self) -> bool:
        return self.before != self.after


StepChange = Literal["unchanged", "changed", "added", "removed"]


@dataclass(frozen=True)
class StepDiff:
    position: int
    change: StepChange
    before: StepContent | None
    after: StepContent | None


def compare(a: Content, b: Content) -> tuple[list[FieldDiff], list[StepDiff]]:
    """Field diffs and steps aligned by position (docs/02 §5.3)."""
    fields = [FieldDiff("format", a.format.value, b.format.value), FieldDiff("title", a.title, b.title)]
    fields += [FieldDiff(f, getattr(a, f), getattr(b, f)) for f in MARKDOWN_FIELDS]
    steps: list[StepDiff] = []
    for i in range(max(len(a.steps), len(b.steps))):
        before = a.steps[i] if i < len(a.steps) else None
        after = b.steps[i] if i < len(b.steps) else None
        if before is None:
            change: StepChange = "added"
        elif after is None:
            change = "removed"
        else:
            change = "unchanged" if before == after else "changed"
        steps.append(StepDiff(i + 1, change, before, after))
    return fields, steps
