"""Strict JSON Schema validation at the publish boundary.

Generators produce structured content. Workshop drafts can hold work in
progress. But once a draft is published — i.e. promoted into the world
or script row a player will actually load — the payload must be runtime-
compatible. This module is the boundary that rejects payloads which
would crash or silently degrade at runtime.

Reject patterns (each was observed in 2026-05 smoke runs):
- Endings missing ending_type / title / soft_conditions / priority
- Events flagged disabled=true (DSL parse failure, invalid NPC name, etc.)
- Worlds with no base_setting

The validator does not auto-repair. It raises SchemaValidationError;
the caller (publish_service) surfaces this as a 400-equivalent to the
admin workshop, which must regenerate or hand-fix the offending field.
"""

from __future__ import annotations

from typing import Any

import jsonschema


_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "kind", "summary", "trigger", "effects"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "kind": {"enum": ["conditional", "npc_intent_driven"]},
        "summary": {"type": "string", "minLength": 1},
        "trigger": {"type": "object"},
        "effects": {"type": "object"},
        "rumors": {"type": "array"},
        "disabled": {"type": "boolean"},
    },
}

_ENDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["ending_type", "title", "description", "soft_conditions", "priority"],
    "properties": {
        "ending_type": {"enum": ["good", "normal", "bad", "hidden", "timeout"]},
        "title": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 20},
        "soft_conditions": {"type": "string", "minLength": 1},
        "priority": {"type": "integer"},
        "quality": {"type": "string"},
        # `name` mirror retained for legacy admin UI; not required.
        "name": {"type": "string"},
    },
}

_SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "events_data", "endings_data"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "script_setting": {"type": "string"},
        "script_type": {"type": "string"},
        "events_data": {"type": "array", "items": _EVENT_SCHEMA, "minItems": 3},
        "endings_data": {"type": "array", "items": _ENDING_SCHEMA, "minItems": 2},
    },
}

_WORLD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "base_setting"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "base_setting": {"type": "string", "minLength": 1},
        "free_setting": {"type": "string"},
    },
}


class SchemaValidationError(ValueError):
    """Raised when payload fails the publish-boundary schema."""


def _format_jsonschema_error(err: jsonschema.ValidationError) -> str:
    path = ".".join(str(p) for p in err.absolute_path) or "$"
    return f"{path}: {err.message}"


def validate_script_payload(payload: dict[str, Any]) -> None:
    """Raises SchemaValidationError on violation; returns None on success."""
    errors: list[str] = []
    for err in jsonschema.Draft202012Validator(_SCRIPT_SCHEMA).iter_errors(payload):
        errors.append(_format_jsonschema_error(err))

    # Reject scripts containing any `disabled` event — disabled means the
    # generator produced something the runtime cannot execute. The legacy
    # "audit-repair" path silently re-enabled these; we want them to fail
    # publish so the generator (or human) fixes the root cause.
    for idx, event in enumerate(payload.get("events_data") or []):
        if isinstance(event, dict) and event.get("disabled"):
            errors.append(
                f"events_data[{idx}].disabled is true: "
                f"{event.get('disabled_reason') or '(no reason)'}"
            )

    if errors:
        raise SchemaValidationError("; ".join(errors))


def validate_world_payload(payload: dict[str, Any]) -> None:
    errors: list[str] = []
    for err in jsonschema.Draft202012Validator(_WORLD_SCHEMA).iter_errors(payload):
        errors.append(_format_jsonschema_error(err))
    if errors:
        raise SchemaValidationError("; ".join(errors))
