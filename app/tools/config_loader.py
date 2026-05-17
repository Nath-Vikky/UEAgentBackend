from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolConfigOverlay:
    path: str
    status: str
    version: str = "tool_config_overlay_v1"
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    loaded_at_mtime: float | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "version": self.version,
            "tool_count": len(self.tools),
            "warnings": self.warnings,
            "errors": self.errors,
            "loaded_at_mtime": self.loaded_at_mtime,
        }


_CACHE: ToolConfigOverlay | None = None


def _default_config_path() -> Path:
    explicit_path = os.environ.get("TOOL_CONFIG_PATH")
    if explicit_path:
        return Path(explicit_path)
    storage_dir = Path(os.environ.get("STORAGE_DIR") or "storage")
    return storage_dir / "tools_config.json"


def load_tool_config_overlay(*, force_reload: bool = False) -> ToolConfigOverlay:
    global _CACHE
    path = _default_config_path()
    resolved = str(path)
    try:
        mtime = path.stat().st_mtime if path.exists() else None
    except OSError as exc:
        return ToolConfigOverlay(path=resolved, status="error", errors=[str(exc)])

    if (
        not force_reload
        and _CACHE is not None
        and _CACHE.path == resolved
        and _CACHE.loaded_at_mtime == mtime
    ):
        return _CACHE

    if not path.exists():
        _CACHE = ToolConfigOverlay(path=resolved, status="not_configured")
        return _CACHE

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _CACHE = ToolConfigOverlay(path=resolved, status="error", errors=[str(exc)], loaded_at_mtime=mtime)
        return _CACHE

    if not isinstance(raw, dict):
        _CACHE = ToolConfigOverlay(
            path=resolved,
            status="error",
            errors=["Tool config root must be a JSON object."],
            loaded_at_mtime=mtime,
        )
        return _CACHE

    raw_tools = raw.get("tools", {})
    warnings: list[str] = []
    tools: dict[str, dict[str, Any]] = {}
    if isinstance(raw_tools, list):
        for item in raw_tools:
            if not isinstance(item, dict) or not item.get("tool_id"):
                warnings.append("Ignored a list item without tool_id.")
                continue
            tools[str(item["tool_id"])] = dict(item)
    elif isinstance(raw_tools, dict):
        tools = {
            str(tool_id): dict(config)
            for tool_id, config in raw_tools.items()
            if isinstance(config, dict)
        }
    else:
        warnings.append("Ignored `tools` because it is neither object nor list.")

    _CACHE = ToolConfigOverlay(
        path=resolved,
        status="loaded",
        version=str(raw.get("version") or "tool_config_overlay_v1"),
        tools=tools,
        warnings=warnings,
        loaded_at_mtime=mtime,
    )
    return _CACHE


def reload_tool_config_overlay() -> ToolConfigOverlay:
    return load_tool_config_overlay(force_reload=True)
