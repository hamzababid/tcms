"""Notification API schemas (docs/06 §4.1; M7 D11, D13)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NotificationRead(BaseModel):
    id: UUID
    type: str
    title: str
    url: str | None = Field(description="App path (or API download path for exports)")
    project_key: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    page: int
    page_size: int
    total: int
    unread: int


class UnreadCount(BaseModel):
    count: int


class MarkRead(_Model):
    ids: list[UUID] | None = Field(default=None, max_length=200)
    all: bool = False


class MarkedRead(BaseModel):
    updated: int
    unread: int


class EmailPreferences(BaseModel):
    mentions: bool = Field(description="Email when someone mentions me (in-app always)")
    digest: bool = Field(description="Daily 07:00 email of runs newly assigned to me")


class EmailPreferencesPatch(_Model):
    mentions: bool | None = None
    digest: bool | None = None
