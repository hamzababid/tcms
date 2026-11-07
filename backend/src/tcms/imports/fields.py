"""Import fields, header synonyms, auto-mapping and value normalisation (docs/02 §15.1; M8 D6).

Pure functions: no database. The same canonical headers are written by the case export, so an export
re-imports with the automatic mapping (AC-IMP-02).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from tcms.core.enums import AutomationStatus, CaseFormat, CaseType, DesignTechnique, PriorityLevel


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str  # canonical export header
    synonyms: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()  # enum fields
    step: bool = False  # belongs to a step, not to the case


CASE_FIELDS: Final[tuple[FieldSpec, ...]] = (
    FieldSpec("key", "Key", ("id", "case id", "test case id", "case key", "test key")),
    FieldSpec(
        "title", "Title", ("summary", "name", "test case", "test name", "case title", "test case title")
    ),
    FieldSpec("folder", "Folder", ("path", "folder path", "module", "section", "suite", "component")),
    FieldSpec("type", "Type", ("test type", "case type"), tuple(t.value for t in CaseType)),
    FieldSpec("priority", "Priority", ("prio", "severity"), tuple(p.value for p in PriorityLevel)),
    FieldSpec(
        "design_technique", "Design technique", ("technique",), tuple(d.value for d in DesignTechnique)
    ),
    FieldSpec("owner", "Owner", ("owner email", "author", "created by", "assignee")),
    FieldSpec("tags", "Tags", ("labels", "label", "tag")),
    FieldSpec(
        "automation_status",
        "Automation",
        ("automation status", "automated"),
        tuple(a.value for a in AutomationStatus),
    ),
    FieldSpec(
        "estimated_minutes", "Estimated minutes", ("estimate", "estimate minutes", "duration", "minutes")
    ),
    FieldSpec("description", "Description", ("objective", "purpose", "details")),
    FieldSpec(
        "preconditions",
        "Preconditions",
        ("precondition", "pre-conditions", "pre conditions", "prerequisites"),
    ),
    FieldSpec("test_data", "Test data", ("testdata",)),
    FieldSpec("expected_result", "Expected overall result", ("overall expected result", "overall expected")),
    FieldSpec("postconditions", "Postconditions", ("postcondition", "post-conditions", "post conditions")),
    FieldSpec("format", "Format", ("case format",), tuple(f.value for f in CaseFormat)),
    FieldSpec("text_body", "Procedure", ("text", "text body", "free text")),
    FieldSpec(
        "step_action", "Step", ("step action", "action", "steps", "step description", "test step"), step=True
    ),
    FieldSpec(
        "step_expected",
        "Step expected result",
        ("expected", "expected result", "expected results", "step expected"),
        step=True,
    ),
    FieldSpec("step_data", "Step data", ("data", "step test data", "input"), step=True),
)

REF_FIELDS: Final[tuple[FieldSpec, ...]] = (
    FieldSpec(
        "reference",
        "Reference",
        ("key", "id", "issue", "issue key", "requirement", "story", "requirement id"),
    ),
    FieldSpec("title", "Title", ("summary", "name", "requirement title")),
    FieldSpec("url", "Link", ("url", "address", "href")),
    FieldSpec("cases", "Linked cases", ("cases", "test cases", "case keys", "linked case keys", "tests")),
)

FIELDS: Final = {"test_case": CASE_FIELDS, "requirement": REF_FIELDS}
IGNORE: Final = ""


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", " ", text.strip().lower())


def automap(entity: str, headers: Sequence[str]) -> dict[str, str]:
    """header → field key by label or synonym (case-insensitive). Each field is used once, first wins."""
    by_name: dict[str, str] = {}
    # Step fields first: in most tools "Expected result" is a step column.
    ordered = sorted(FIELDS[entity], key=lambda f: not f.step)
    for f in ordered:
        for name in (f.label, *f.synonyms):
            by_name.setdefault(_norm(name), f.key)
    for f in ordered:
        by_name.setdefault(_norm(f.key), f.key)
    out: dict[str, str] = {}
    used: set[str] = set()
    for h in headers:
        key = by_name.get(_norm(h))
        if key and key not in used:
            out[h] = key
            used.add(key)
        else:
            out[h] = IGNORE
    return out


# Common spellings in other tools → our values (docs/07 §5.16 "P1→High").
_ALIASES: Final[dict[str, dict[str, str]]] = {
    "priority": {
        "p0": "critical",
        "blocker": "critical",
        "highest": "critical",
        "urgent": "critical",
        "p1": "high",
        "major": "high",
        "p2": "medium",
        "normal": "medium",
        "p3": "low",
        "minor": "low",
        "lowest": "low",
        "trivial": "low",
        "p4": "low",
    },
    "type": {
        "e2e": "end_to_end",
        "end to end": "end_to_end",
        "regression": "functional",
        "smoke": "functional",
    },
    "automation_status": {
        "yes": "automated",
        "true": "automated",
        "no": "manual",
        "false": "manual",
        "candidate": "to_be_automated",
        "to automate": "to_be_automated",
        "n/a": "not_automatable",
    },
    "design_technique": {"bva": "boundary_value", "ep": "equivalence_partitioning"},
}


def choice(
    field: str, value: str, choices: Sequence[str], value_map: dict[str, str] | None = None
) -> str | None:
    """A file value → an allowed value: the user's value map first, then exact (spaces/underscores and
    case ignored), then common aliases. None = unknown."""
    if value_map and value in value_map:
        mapped = value_map[value]
        return mapped if mapped in choices else None
    v = _norm(value)
    for c in choices:
        if _norm(c) == v:
            return c
    alias = _ALIASES.get(field, {}).get(v)
    return alias if alias in choices else None


_NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+", re.M)


def split_numbered(cell: str) -> list[str]:
    """ "1. Open\\n2. Click" → ["Open", "Click"]; text without numbers is one item."""
    text = cell.strip()
    if not text:
        return []
    marks = list(_NUMBERED.finditer(text))
    if not marks:
        return [text]
    parts = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        parts.append(text[m.end() : end].strip())
    return parts


def split_list(cell: str) -> list[str]:
    """Comma, semicolon or newline separated values."""
    return [x.strip() for x in re.split(r"[,;\n]", cell) if x.strip()]


def join_numbered(items: Sequence[str | None]) -> str:
    return "\n".join(f"{i}. {x or ''}".rstrip() for i, x in enumerate(items, start=1))
