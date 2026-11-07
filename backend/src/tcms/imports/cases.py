"""Test case import: from table rows to an import plan, and the plan's commit (docs/02 §15.1; M8 D4).

`build_plan` is pure: it takes the rows, the mapping and a `Context` snapshot of the project (existing
cases by key, folders by path, members by email) and returns every case with its action and its errors.
`commit` writes a plan through the testdesign services, so rules, keys and audit apply; the caller runs
it in one transaction (AC-IMP-03).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from uuid import UUID

from tcms.core.context import AccessContext
from tcms.core.enums import AutomationStatus, CaseFormat, CaseType, DesignTechnique, PriorityLevel
from tcms.core.errors import FieldError
from tcms.core.uow import UnitOfWork
from tcms.imports import fields as F
from tcms.testdesign import queries as td_queries
from tcms.testdesign import rules as td_rules
from tcms.testdesign import service as testdesign

MAX_CASES: Final = 5_000
MAX_ROWS: Final = 50_000
MAX_ERRORS: Final = 1_000
FOLDER_SEPARATORS: Final = ("/",)

Action = Literal["create", "update", "unchanged", "error"]


@dataclass(frozen=True)
class Options:
    mode: Literal["upsert", "create_only"] = "upsert"
    target_folder_id: UUID | None = None
    steps_layout: Literal["row_per_step", "single_cell"] = "row_per_step"
    skip_error_rows: bool = False


@dataclass(frozen=True)
class Problem:
    row: int  # 1-based spreadsheet row (the header is row 1)
    column: str | None
    code: str
    message: str

    def as_json(self) -> dict[str, Any]:
        return {"row": self.row, "column": self.column, "code": self.code, "message": self.message}


@dataclass
class Context:
    """What the planner needs to know about the project."""

    existing: dict[str, td_queries.CaseSnapshot]  # upper(key) → case
    folders: dict[tuple[str, ...], UUID]  # lower-cased names from the top → folder
    archived_folders: set[UUID]
    members: dict[str, UUID]  # lower(email) → user
    importer: UUID
    target_folder: tuple[str, ...] | None = None  # path of the default folder


@dataclass
class PlannedCase:
    row: int
    action: Action
    key: str | None  # existing key for updates
    content: td_rules.Content | None
    meta: dict[str, Any]  # folder_path (tuple) and metadata fields given in the file
    problems: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)


@dataclass
class Plan:
    cases: list[PlannedCase]
    file_problems: list[Problem]
    folders_to_create: list[tuple[str, ...]]

    @property
    def counts(self) -> dict[str, int]:
        out = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
        for c in self.cases:
            out[c.action] += 1
        out["warnings"] = sum(len(c.warnings) for c in self.cases)
        out["folders_to_create"] = len(self.folders_to_create)
        return out

    @property
    def problems(self) -> list[Problem]:
        return self.file_problems + [p for c in self.cases for p in c.problems]

    def committable(self, skip_error_rows: bool) -> bool:
        if self.file_problems:
            return False
        if not any(c.action in ("create", "update") for c in self.cases):
            return False
        return skip_error_rows or not any(c.action == "error" for c in self.cases)


_ENUMS: Final = {
    "type": tuple(t.value for t in CaseType),
    "priority": tuple(p.value for p in PriorityLevel),
    "design_technique": tuple(d.value for d in DesignTechnique),
    "automation_status": tuple(a.value for a in AutomationStatus),
    "format": tuple(f.value for f in CaseFormat),
}
_TEXT_FIELDS: Final = (
    "description",
    "preconditions",
    "test_data",
    "expected_result",
    "postconditions",
    "text_body",
)
_META_FIELDS: Final = ("type", "priority", "design_technique", "automation_status", "estimated_minutes")


def folder_path(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.strip().split("/") if p.strip())


def _lower(path: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(p.lower() for p in path)


def build_plan(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    mapping: dict[str, str],
    value_maps: dict[str, dict[str, str]],
    options: Options,
    ctx: Context,
) -> Plan:
    columns: dict[str, int] = {}
    for i, h in enumerate(header):
        f = mapping.get(h, F.IGNORE)
        if f and f not in columns:
            columns[f] = i
    file_problems: list[Problem] = []
    if "title" not in columns and "key" not in columns:
        file_problems.append(Problem(1, None, "field_required", "Map a column to Title (or Key for updates)"))
    if len(rows) > MAX_ROWS:
        file_problems.append(Problem(1, None, "too_many_rows", f"At most {MAX_ROWS:,} rows per file"))
    if file_problems:
        return Plan([], file_problems, [])

    def get(row: Sequence[str], f: str) -> str:
        i = columns.get(f)
        return row[i].strip() if i is not None and i < len(row) else ""

    # 1. Group rows into cases (docs/02 §15.1 row model).
    groups: list[tuple[int, list[Sequence[str]]]] = []
    orphan_steps: list[int] = []
    for n, row in enumerate(rows, start=2):
        if not any(c.strip() for c in row):
            continue
        starts = bool(get(row, "key") or get(row, "title"))
        if starts or options.steps_layout == "single_cell":
            groups.append((n, [row]))
        elif groups:
            groups[-1][1].append(row)
        else:
            orphan_steps.append(n)
    file_problems += [
        Problem(n, None, "step_without_case", "This row has no Key or Title and no case above it")
        for n in orphan_steps
    ]
    if len(groups) > MAX_CASES:
        return Plan([], [Problem(1, None, "too_many_cases", f"At most {MAX_CASES:,} cases per file")], [])

    step_mapped = any(f in columns for f in ("step_action", "step_expected", "step_data"))
    seen_keys: dict[str, int] = {}
    planned: list[PlannedCase] = []
    new_folders: dict[tuple[str, ...], tuple[str, ...]] = {}
    for first_row, group in groups:
        head = group[0]
        problems: list[Problem] = []
        warnings: list[Problem] = []

        def err(
            col: str | None, code: str, msg: str, row: int = first_row, out: list[Problem] = problems
        ) -> None:
            out.append(Problem(row, col, code, msg))

        key = get(head, "key")
        existing = ctx.existing.get(key.upper()) if key else None
        if key:
            if key.upper() in seen_keys:
                err("key", "duplicate_key", f"{key} appears again (first on row {seen_keys[key.upper()]})")
            seen_keys.setdefault(key.upper(), first_row)
            if existing and options.mode == "create_only":
                err("key", "key_exists", f"{key} exists and the mode is Create only")
            if existing and existing.status == "archived":
                err("key", "case_archived", f"{existing.key} is archived; restore it before importing")
            if not existing:
                warnings.append(
                    Problem(
                        first_row,
                        "key",
                        "unknown_key",
                        f"{key} is not in this project; a new case is created",
                    )
                )
        base = existing.content if existing else None

        # Enums and numbers.
        meta: dict[str, Any] = {}
        for f in ("type", "priority", "design_technique", "automation_status", "format"):
            raw = get(head, f)
            if not raw:
                continue
            value = F.choice(f, raw, _ENUMS[f], value_maps.get(f))
            if value is None:
                err(f, "invalid_value", f'"{raw}" is not allowed; use one of: {", ".join(_ENUMS[f])}')
            else:
                meta[f] = value
        raw_minutes = get(head, "estimated_minutes")
        if raw_minutes:
            try:
                minutes = int(float(raw_minutes))
                if not 0 <= minutes <= 1440:
                    raise ValueError
                meta["estimated_minutes"] = minutes
            except ValueError:
                err("estimated_minutes", "invalid_value", "Give a whole number of minutes from 0 to 1440")
        if "tags" in columns:
            tags = sorted({t.lower() for t in F.split_list(get(head, "tags"))})
            tag_problems = td_rules.tag_problems(tags)
            if tag_problems:
                err("tags", "invalid_value", tag_problems[0].message)
            else:
                meta["tags"] = tags
        owner = get(head, "owner")
        if owner:
            uid = ctx.members.get(owner.lower())
            if uid is None:
                warnings.append(
                    Problem(
                        first_row,
                        "owner",
                        "unknown_owner",
                        f"{owner} is not a project member; you become the owner",
                    )
                )
                if not existing:
                    meta["owner_id"] = ctx.importer
            else:
                meta["owner_id"] = uid

        # Folder.
        raw_folder = get(head, "folder")
        path = folder_path(raw_folder) if raw_folder else None
        if path is not None:
            if len(path) > td_rules.MAX_DEPTH:
                err("folder", "folder_too_deep", f"At most {td_rules.MAX_DEPTH} folder levels")
            elif any(td_rules.folder_name_problem(p) for p in path):
                err("folder", "invalid_value", "A folder name is empty or longer than 120 characters")
            else:
                meta["folder_path"] = path
                folder_id = ctx.folders.get(_lower(path))
                if folder_id is not None and folder_id in ctx.archived_folders:
                    err("folder", "folder_archived", f"The folder {'/'.join(path)} is archived")
        elif not existing and ctx.target_folder is None:
            err("folder", "field_required", "Give a Folder or choose a target folder")

        # Content: file values over the existing content.
        title = get(head, "title") or (base.title if base else "")
        fmt = CaseFormat(meta.get("format") or (base.format.value if base else CaseFormat.steps.value))
        texts = {f: get(head, f) or None for f in _TEXT_FIELDS if f in columns}
        steps: tuple[td_rules.StepContent, ...] | None
        if step_mapped:
            if options.steps_layout == "single_cell":
                actions = F.split_numbered(get(head, "step_action"))
                expected = F.split_numbered(get(head, "step_expected"))
                data = F.split_numbered(get(head, "step_data"))
                width = max(len(actions), len(expected), len(data))
                items = [
                    (
                        actions[i] if i < len(actions) else "",
                        expected[i] if i < len(expected) else None,
                        data[i] if i < len(data) else None,
                    )
                    for i in range(width)
                ]
                step_rows = [first_row] * len(items)
            else:
                items = [
                    (get(r, "step_action"), get(r, "step_expected") or None, get(r, "step_data") or None)
                    for r in group
                ]
                items_rows = list(range(first_row, first_row + len(group)))
                keep = [(it, n) for it, n in zip(items, items_rows, strict=True) if any(it)]
                items = [it for it, _ in keep]
                step_rows = [n for _, n in keep]
            for (step_action, exp, dat), n in zip(items, step_rows, strict=True):
                if not step_action and (exp or dat):
                    err(
                        "step_action",
                        "field_required",
                        "This step has an expected result or data but no action",
                        row=n,
                    )
            steps = tuple(td_rules.StepContent(a, e, d) for a, e, d in items if a)
        else:
            steps = base.steps if base else ()
        content = td_rules.Content(
            format=fmt,
            title=title,
            description=texts.get("description", base.description if base else None),
            preconditions=texts.get("preconditions", base.preconditions if base else None),
            test_data=texts.get("test_data", base.test_data if base else None),
            expected_result=texts.get("expected_result", base.expected_result if base else None),
            postconditions=texts.get("postconditions", base.postconditions if base else None),
            text_body=texts.get("text_body", base.text_body if base else None),
            steps=steps if fmt is CaseFormat.steps else (),
        )
        content = td_rules.normalize_content(content)
        if not title:
            err("title", "field_required", "The title is missing")
        else:
            for p in td_rules.content_problems(content):
                err(_column_of(p), p.code, p.message)

        action: Action
        if problems:
            action = "error"
        elif existing is None:
            action = "create"
        elif td_rules.content_hash(content) == existing.content_hash and _same_meta(existing, meta, ctx):
            action = "unchanged"
        else:
            action = "update"
        if action != "error" and "folder_path" in meta:  # only the folders that imported cases use
            fpath = meta["folder_path"]
            for i in range(1, len(fpath) + 1):
                if _lower(fpath[:i]) not in ctx.folders:
                    new_folders.setdefault(_lower(fpath[:i]), fpath[:i])
        planned.append(
            PlannedCase(
                first_row, action, existing.key if existing else None, content, meta, problems, warnings
            )
        )
    folders = [p for k, p in sorted(new_folders.items(), key=lambda kv: (len(kv[0]), kv[0]))]
    return Plan(planned, file_problems, folders)


def _column_of(p: FieldError) -> str:
    f = p.field.removeprefix("content.")
    if f.startswith("steps"):
        return "step_action"
    return f


def _same_meta(c: td_queries.CaseSnapshot, meta: dict[str, Any], ctx: Context) -> bool:
    for f in _META_FIELDS:
        if f in meta and meta[f] != getattr(c, f):
            return False
    if "tags" in meta and tuple(meta["tags"]) != tuple(sorted(c.tags)):
        return False
    if "owner_id" in meta and meta["owner_id"] != c.owner_id:
        return False
    return not ("folder_path" in meta and ctx.folders.get(_lower(meta["folder_path"])) != c.folder_id)


# -- context and commit -----------------------------------------------------------------------------


def load_context(
    uow: UnitOfWork,
    ctx: AccessContext,
    keys: list[str],
    members: dict[str, UUID],
    target_folder_id: UUID | None,
) -> Context:
    s = uow.session
    paths = td_queries.folder_paths(s, ctx)
    folders = {_lower(p): fid for fid, p in paths.items()}
    archived = {fid for fid, a in td_queries.folder_archived(s, ctx).items() if a}
    existing = {c.key.upper(): c for c in td_queries.case_snapshots(s, ctx, keys=keys)} if keys else {}
    assert ctx.principal.user_id is not None
    return Context(
        existing=existing,
        folders=folders,
        archived_folders=archived,
        members=members,
        importer=ctx.principal.user_id,
        target_folder=paths.get(target_folder_id) if target_folder_id else None,
    )


def keys_in(header: Sequence[str], rows: Sequence[Sequence[str]], mapping: dict[str, str]) -> list[str]:
    col = next((i for i, h in enumerate(header) if mapping.get(h) == "key"), None)
    if col is None:
        return []
    return sorted({r[col].strip() for r in rows if col < len(r) and r[col].strip()})


@dataclass(frozen=True)
class CommitResult:
    created: int
    updated: int
    unchanged: int
    skipped: int
    folders_created: int
    report: list[tuple[int, str, str, str]]  # row, result, key, message


def commit(
    uow: UnitOfWork, ctx: AccessContext, plan: Plan, options: Options, context: Context
) -> CommitResult:
    """Write the plan (caller's transaction). Raises on any failure so nothing of the file remains."""
    folder_ids = dict(context.folders)
    created_folders = 0
    for path in plan.folders_to_create:
        parent = folder_ids.get(_lower(path[:-1])) if len(path) > 1 else None
        f = testdesign.create_folder(uow, ctx, name=path[-1], parent_id=parent, description=None)
        folder_ids[_lower(path)] = f.id
        created_folders += 1
    target = folder_ids.get(_lower(context.target_folder)) if context.target_folder else None
    report: list[tuple[int, str, str, str]] = []
    counts = {"create": 0, "update": 0, "unchanged": 0, "skipped": 0}
    for i, pc in enumerate(plan.cases, start=1):
        if pc.action == "error":
            counts["skipped"] += 1
            report.append((pc.row, "skipped", pc.key or "", "; ".join(p.message for p in pc.problems)))
            continue
        assert pc.content is not None
        folder = folder_ids.get(_lower(pc.meta["folder_path"])) if "folder_path" in pc.meta else None
        note = "; ".join(w.message for w in pc.warnings)
        if pc.action == "unchanged":
            counts["unchanged"] += 1
            report.append((pc.row, "unchanged", pc.key or "", note))
            continue
        if pc.action == "create":
            meta = testdesign.CaseMetadata(
                folder_id=folder or target,  # type: ignore[arg-type]
                type=CaseType(pc.meta.get("type", "functional")),
                design_technique=DesignTechnique(pc.meta["design_technique"])
                if pc.meta.get("design_technique")
                else None,
                priority=PriorityLevel(pc.meta.get("priority", "medium")),
                tags=list(pc.meta.get("tags", [])),
                owner_id=pc.meta.get("owner_id"),
                automation_status=AutomationStatus(pc.meta.get("automation_status", "manual")),
                estimated_minutes=pc.meta.get("estimated_minutes"),
            )
            result = testdesign.create_case(uow, ctx, content=pc.content, meta=meta)
            counts["create"] += 1
            report.append((pc.row, "created", result.case.key, note))
        else:
            snap = context.existing[(pc.key or "").upper()]
            saved = testdesign.update_content(
                uow, ctx, snap.id, content=pc.content, change_note="Imported", row_version=snap.row_version
            )
            fields: dict[str, Any] = {}
            for fname in _META_FIELDS:
                if fname in pc.meta:
                    value = pc.meta[fname]
                    enum = {
                        "type": CaseType,
                        "priority": PriorityLevel,
                        "design_technique": DesignTechnique,
                        "automation_status": AutomationStatus,
                    }.get(fname)
                    fields[fname] = enum(value) if enum and value is not None else value
            if "tags" in pc.meta:
                fields["tags"] = list(pc.meta["tags"])
            if "owner_id" in pc.meta:
                fields["owner_id"] = pc.meta["owner_id"]
            if folder is not None:
                fields["folder_id"] = folder
            if fields:
                testdesign.update_metadata(uow, ctx, snap.id, row_version=None, fields=fields, bulk=True)
            counts["update"] += 1
            msg = "new version" if saved.version_created else "metadata updated"
            report.append((pc.row, "updated", snap.key, f"{msg}; {note}" if note else msg))
        if i % 500 == 0:
            uow.session.flush()
    return CommitResult(
        counts["create"], counts["update"], counts["unchanged"], counts["skipped"], created_folders, report
    )
