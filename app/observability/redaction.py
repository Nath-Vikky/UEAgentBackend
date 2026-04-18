from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SECRET_KEYS = {"api_key", "token", "secret", "password", "database_url"}
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\\\[^\\s]+")


def _mask_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    lowered = key.lower()
    if any(secret in lowered for secret in SECRET_KEYS):
        return "***REDACTED***"
    if isinstance(value, str):
        masked = WINDOWS_PATH_RE.sub("<redacted_path>", value)
        try:
            candidate = Path(masked)
            if candidate.is_absolute():
                return "<redacted_path>"
        except OSError:
            return masked
        return masked
    return value


def redact_payload(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {key: redact_payload(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item, parent_key) for item in value]
    return _mask_value(parent_key, value)

