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
    result = execute_tool_with_context(ToolContext(tool_id="generate_code_draft"))

    assert result.ok is False
    assert result.error_code == "executor_not_configured"


def test_executor_runtime_blocks_invalid_input_before_dispatch() -> None:
    result = execute_tool_with_context(
        ToolContext(
            tool_id="read_project_file",
            payload={"file_path": "Source/Demo/Hero.cpp"},
        )
    )

    assert result.ok is False
    assert result.status == "blocked"
    assert result.error_code == "tool_preflight_failed"
    assert result.metadata["preflight"]["missing_fields"] == ["project_root"]


def test_execute_preflight_generated_code_with_tool_context() -> None:
    result = execute_tool_with_context(
        ToolContext(
            tool_id="preflight_generated_code",
            payload={
                "generated_items": [
                    {
                        "file_path": "Source/Demo/Public/Hero.h",
                        "code": "#pragma once\nUCLASS()\nclass AHero : public ACharacter { GENERATED_BODY() };",
                    }
                ],
                "requirement": "Generate an Enhanced Input character.",
            },
        )
    )

    assert result.ok is True
    assert result.output["preflight_report"]["summary"]["checked_item_count"] == 1
    assert result.metadata["preflight"]["ok"] is True


def test_execute_analyze_ue_log_with_tool_context() -> None:
    result = execute_tool_with_context(
        ToolContext(
            tool_id="analyze_ue_log",
            payload={"log_text": "LogTemp: Error: Failed to load /Game/MissingAsset"},
        )
    )

    assert result.ok is True
    assert result.output["log_summary"]["error_count"] == 1
    assert "asset_load_failure" in result.output["issue_families"]


def test_execute_inspect_asset_metadata_with_tool_context() -> None:
    result = execute_tool_with_context(
        ToolContext(
            tool_id="inspect_asset_metadata",
            active_context={"project_name": "Demo"},
            payload={
                "asset_items": [
                    {
                        "asset_path": "/Game/NewBlueprint",
                        "asset_name": "NewBlueprint",
                        "asset_type": "Blueprint",
                    }
                ]
            },
        )
    )

    assert result.ok is True
    assert result.output["summary"]["asset_count"] == 1
    assert result.output["rename_suggestions"]


def test_execute_review_ue_cpp_files_with_tool_context() -> None:
    result = execute_tool_with_context(
        ToolContext(
            tool_id="review_ue_cpp_files",
            payload={
                "user_query": "review this file",
                "code": "void AHero::Tick(float DeltaSeconds) { UObject* Obj = nullptr; }",
            },
        )
    )

    assert result.ok is True
    assert result.output["severity_summary"]["medium"] >= 1
    assert "tick_hot_path" in result.output["rule_hits"]
