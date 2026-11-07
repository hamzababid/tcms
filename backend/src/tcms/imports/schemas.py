"""Import / export API schemas (docs/06 §4.13; M8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Entity = Literal["test_case", "requirement"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldInfo(BaseModel):
    key: str
    label: str
    choices: list[str]
    step: bool


class SheetRead(BaseModel):
    name: str
    columns: list[str]
    rows: int
    sample: list[list[str]]
    suggested_mapping: dict[str, str] = Field(description="column → field key ('' = ignore)")
    values: dict[str, list[str]] = Field(description="Distinct values of columns with 30 values or fewer")


class ImportUploaded(BaseModel):
    transfer_id: UUID
    entity: Entity
    file_name: str
    sheets: list[SheetRead]
    fields: list[FieldInfo]


class ImportOptions(_Model):
    mode: Literal["upsert", "create_only"] = "upsert"
    target_folder_id: UUID | None = None
    steps_layout: Literal["row_per_step", "single_cell"] = "row_per_step"
    skip_error_rows: bool = False


class ValidateRequest(_Model):
    sheet: str | None = None
    mapping: dict[str, str] = Field(description="column header → field key; '' ignores the column")
    value_maps: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="field → file value → value"
    )
    options: ImportOptions = Field(default_factory=ImportOptions)


class TemplateRead(BaseModel):
    id: UUID
    entity: Entity
    name: str
    mapping: dict[str, Any]
    created_at: datetime


class TemplateCreate(_Model):
    entity: Entity
    name: str = Field(min_length=1, max_length=100)
    mapping: dict[str, Any] = Field(description="{columns: {header: field}, value_maps, options}")


class ExportCreate(_Model):
    entity: Entity
    format: Literal["csv", "xlsx"] = "xlsx"
    filters: dict[str, str] = Field(default_factory=dict, description="Repository list filters (test cases)")
    case_ids: list[UUID] | None = Field(
        default=None, max_length=5000, description="Selected cases instead of filters"
    )
    version: Literal["latest", "approved"] = "latest"
    include_archived: bool = False
