from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.tools.context import ToolContext
from app.tools.executor_runtime import execute_tool_with_context


def _runtime_root(name: str) -> Path:
    return Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"


def test_execute_read_project_file_with_tool_context() -> None:
    root = _runtime_root("tool-executor-read-file")
    try:
        source_dir = root / "Source" / "Demo"
        source_dir.mkdir(parents=True)
        (source_dir / "Hero.cpp").write_text("void AHero::BeginPlay() {}", encoding="utf-8")

        result = execute_tool_with_context(
            ToolContext(
                tool_id="read_project_file",
                payload={
                    "project_root": str(root.resolve()),
                    "file_path": "Source/Demo/Hero.cpp",
                    "max_bytes": 4000,
                },
            )
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.ok is True
    assert result.output["status"] == "completed"
    assert "BeginPlay" in result.output["text_excerpt"]
    assert result.to_debug_entry()["protocol_version"] == "tool_result_v1"


def test_execute_validate_design_config_with_tool_context() -> None:
    result = execute_tool_with_context(
        ToolContext(
            tool_id="validate_design_config",
            payload={
                "schema": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                },
                "config_json": {"name": "Goblin"},
            },
        )
    )

    assert result.ok is True
    assert result.output["validation_summary"]["is_valid"] is True
    assert result.output["errors"] == []


def test_execute_missing_executor_returns_failed_result() -> None:
    result = execute_tool_with_context(ToolContext(tool_id="analyze_ue_log"))

    assert result.ok is False
    assert result.error_code == "executor_not_configured"
