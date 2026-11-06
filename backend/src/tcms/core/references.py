"""External references (bugs, ADR-023; requirements, ADR-024): the team's own identifiers with an optional
http(s) URL, built from a project template with `{ref}`. Pure helpers shared by the bugs and requirements
modules."""

from __future__ import annotations

import re
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


def reference_problem(reference: str, field: str = "reference") -> FieldError | None:
    ref = normalize_reference(reference)
    if not ref:
        return FieldError(field, "field_required", "Enter the reference, e.g. SPK-431")
    if len(ref) > REFERENCE_MAX or not _REFERENCE_RE.match(ref) or _CONTROL_RE.search(ref):
        return FieldError(field, "invalid_format", f"Up to {REFERENCE_MAX} characters, no spaces")
    return None


def url_problem(url: str | None, field: str = "url") -> FieldError | None:
    """Only http(s) addresses with a host are stored and rendered (AC-BUG-05)."""
    if url is None or url == "":
        return None
    msg = "Use an address starting with http:// or https://"
    if len(url) > URL_MAX or _CONTROL_RE.search(url) or any(c.isspace() for c in url):
        return FieldError(field, "invalid_format", msg)
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return FieldError(field, "invalid_format", msg)
    return None


def title_problem(title: str | None, field: str = "title") -> FieldError | None:
    if title is not None and len(title.strip()) > TITLE_MAX:
        return FieldError(field, "invalid_length", f"At most {TITLE_MAX} characters")
    return None


def build_url(template: str | None, reference: str) -> str | None:
    """`{ref}` in the project template, URL-encoded (`#1287` → `%231287`)."""
    if not template:
        return None
    return template.replace("{ref}", quote(normalize_reference(reference), safe="-._~"))


def link_url(given: str | None, template: str | None, reference: str) -> str | None:
    """A given URL is kept as given; otherwise the template builds one (stored, not recomputed)."""
    given = (given or "").strip()
    return given or build_url(template, reference)


def clean_title(title: str | None) -> str | None:
    return (title or "").strip() or None


_SPLIT_RE: Final = re.compile(r"[\s,;]+")


def parse_many(text: str) -> list[str]:
    """ "Paste many" (docs/02 §10.1): comma, semicolon, space or newline separated; order kept, duplicates
    (case-insensitive) dropped."""
    seen: set[str] = set()
    out = []
    for part in _SPLIT_RE.split(text):
        ref = normalize_reference(part)
        if ref and ref.upper() not in seen:
            seen.add(ref.upper())
            out.append(ref)
    return out


_NUM_RE: Final = re.compile(r"(\d+)")


def natural_key(reference: str) -> tuple[tuple[int, int | str], ...]:
    """SPK-2 before SPK-10."""
    return tuple((0, int(p)) if p.isdigit() else (1, p.upper()) for p in _NUM_RE.split(reference) if p)
