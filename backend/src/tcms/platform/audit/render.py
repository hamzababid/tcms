"""Renders audit events as sentences for the activity feed (docs/02 §9.3).

Modules register specific renderers for their actions; the fallback produces
"<actor> <verb> <entity>" from the `entity.verb_past` action name.
"""

from __future__ import annotations

from collections.abc import Callable

from tcms.core.uow import AuditRecord

Renderer = Callable[[AuditRecord], str]
_renderers: dict[str, Renderer] = {}


def register(action: str) -> Callable[[Renderer], Renderer]:
    def deco(fn: Renderer) -> Renderer:
        _renderers[action] = fn
        return fn

    return deco


def render_summary(record: AuditRecord) -> str:
    fn = _renderers.get(record.action)
    if fn is not None:
        return fn(record)
    actor = record.actor_display or record.actor_type.value
    _, _, verb = record.action.partition(".")
    target = record.entity_key or record.entity_type.replace("_", " ")
    return f"{actor} {verb.replace('_', ' ')} {target}".strip()
