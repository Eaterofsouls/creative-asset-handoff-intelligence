"""JSON Schema for AI cluster-analysis responses + validator.

This is deliberately a plain JSON Schema + `jsonschema` validation call —
NOT a LangChain output parser and NOT implicit trust in model text. The same
schema (hand-ported to a JS object) is used inside the n8n Code node that
validates the HTTP Request response, so both the Python demo path and the
live n8n workflow enforce the identical contract. See
docs/architecture-decision.md §4 and docs/deterministic-vs-ai.md.
"""
from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, ValidationError

AI_CLUSTER_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "cluster_id", "relationship", "confidence", "creative_type",
        "visual_summary", "reason", "recommended_review", "members",
    ],
    "additionalProperties": False,
    "properties": {
        "cluster_id": {"type": "string", "minLength": 1},
        "relationship": {
            "type": "string",
            "enum": ["likely_version_family", "likely_duplicate_set", "unrelated_similar", "unclear"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "creative_type": {"type": "string", "minLength": 1, "maxLength": 60},
        "visual_summary": {"type": "string", "minLength": 1, "maxLength": 400},
        "reason": {"type": "string", "minLength": 1, "maxLength": 400},
        "recommended_review": {"type": "boolean"},
        "members": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["asset_id", "likely_role", "role_confidence", "differs_visually"],
                "additionalProperties": False,
                "properties": {
                    "asset_id": {"type": "string", "minLength": 1},
                    "likely_role": {
                        "type": "string",
                        "enum": ["final", "intermediate", "source", "duplicate", "unknown"],
                    },
                    "role_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "differs_visually": {"type": "boolean"},
                },
            },
        },
    },
}

_validator = Draft7Validator(AI_CLUSTER_ANALYSIS_SCHEMA)


def validate_ai_response(payload: Any) -> tuple[bool, str | None]:
    """Returns (is_valid, error_message). Never raises."""
    errors = sorted(_validator.iter_errors(payload), key=lambda e: e.path)
    if not errors:
        return True, None
    first = errors[0]
    location = "/".join(str(p) for p in first.path) or "<root>"
    return False, f"schema violation at '{location}': {first.message}"
