"""JSON utilities to sanitize common LLM mistakes like trailing commas."""

from __future__ import annotations

import json
import re
from typing import Any


class JsonPayloadParseError(ValueError):
    """Raised when a JSON payload cannot be parsed safely."""


_TRAILING_COMMA_PATTERN = re.compile(r",\s*([}\]])")


def sanitize_trailing_commas(payload: str) -> str:
    """Remove trailing commas that appear before a closing } or ]."""

    return _TRAILING_COMMA_PATTERN.sub(r"\1", payload)


def parse_json_payload(payload: str) -> Any:
    """Parse JSON with one fallback pass after removing trailing commas."""

    try:
        return json.loads(payload)
    except json.JSONDecodeError as original_err:
        sanitized = sanitize_trailing_commas(payload)
        if sanitized != payload:
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                pass
        raise JsonPayloadParseError(str(original_err)) from original_err
