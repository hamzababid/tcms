"""CSV and XLSX reading and writing shared by report exports and the import/export of cases and
requirement references (docs/02 §11.5, §15; docs/03 A03).

Writing: text cells that a spreadsheet would read as a formula get a leading `'` (OWASP CSV injection);
CSV is UTF-8 with a BOM so Excel opens it correctly. Reading: openpyxl read-only mode (no formulas are
evaluated, cached values only) or the csv module with dialect sniffing; every cell becomes trimmed text.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from openpyxl import Workbook, load_workbook

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def safe(value: Any) -> Any:
    """Neutralise formula injection in text cells; numbers and dates pass through."""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def cell(value: Any, kind: str = "text") -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None) if kind == "datetime" else value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return safe(value)


def write_csv(
    header: Sequence[str], rows: Iterable[Sequence[Any]], kinds: Sequence[str] | None = None
) -> bytes:
    kinds = kinds or ["text"] * len(header)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow([safe(h) for h in header])
    for row in rows:
        values = []
        for v, kind in zip(row, kinds, strict=False):
            c = cell(v, kind)
            values.append(c.isoformat(sep=" ", timespec="seconds") + "Z" if isinstance(c, datetime) else c)
        w.writerow(values)
    return buf.getvalue().encode("utf-8")


def write_xlsx(
    header: Sequence[str], rows: Iterable[Sequence[Any]], title: str, kinds: Sequence[str] | None = None
) -> bytes:
    kinds = kinds or ["text"] * len(header)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title=title[:31])
    ws.append([safe(h) for h in header])
    for row in rows:
        ws.append([cell(v, k) for v, k in zip(row, kinds, strict=False)])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# -- reading ----------------------------------------------------------------------------------------


class UnreadableFile(Exception):
    """The file is not a CSV or XLSX we can read."""


@dataclass(frozen=True)
class Sheet:
    name: str
    rows: list[list[str]]  # header first; trailing empty rows removed

    @property
    def header(self) -> list[str]:
        return self.rows[0] if self.rows else []

    @property
    def data(self) -> list[list[str]]:
        return self.rows[1:]


def unescape(text: str) -> str:
    """Undo `safe()` so an exported file re-imports to the same values (AC-IMP-02)."""
    return text[1:] if len(text) > 1 and text[0] == "'" and text[1] in FORMULA_START else text


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return unescape(str(v).strip())


def _trim(rows: list[list[str]]) -> list[list[str]]:
    while rows and not any(rows[-1]):
        rows.pop()
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def read_tables(data: bytes, file_name: str, *, max_rows: int) -> list[Sheet]:
    """Every sheet (XLSX) or the single table (CSV). More than `max_rows` data rows → UnreadableFile."""
    name = file_name.lower()
    if name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # zip/xml errors from a damaged or foreign file
            raise UnreadableFile("This is not a readable Excel (.xlsx) file") from exc
        sheets = []
        for ws in wb.worksheets:
            grid: list[list[str]] = []
            for r in ws.iter_rows(values_only=True):
                grid.append([_text(v) for v in r])
                if len(grid) > max_rows + 1:
                    raise UnreadableFile(f"The sheet {ws.title} has more than {max_rows:,} rows")
            sheets.append(Sheet(ws.title, _trim(grid)))
        wb.close()
        return sheets
    if name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
        try:
            dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        table: list[list[str]] = []
        for line in csv.reader(io.StringIO(text), dialect):
            table.append([unescape(str(c).strip()) for c in line])
            if len(table) > max_rows + 1:
                raise UnreadableFile(f"The file has more than {max_rows:,} rows")
        return [Sheet("CSV", _trim(table))]
    raise UnreadableFile("Upload a .csv or .xlsx file")
