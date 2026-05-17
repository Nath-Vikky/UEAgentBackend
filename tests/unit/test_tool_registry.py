from __future__ import annotations

from app.tools.contracts import (
    validate_tool_call_input,
    validate_tool_registry,
    validate_tool_result,
)
from app.tools.registry import candidate_tools_for_text, detect_tool_for_text, get_tool_spec


def test_tool_registry_detects_chinese_project_inventory_query() -> None:
    tools = candidate_tools_for_text("当前项目有哪些蓝图资产？")

    assert tools[0] == "query_project_inventory"
    assert detect_tool_for_text("当前项目有哪些蓝图资产？") == "query_project_inventory"


def test_tool_capability_card_exposes_schema_and_policy() -> None:
    spec = get_tool_spec("analyze_ue_log")

    assert spec is not None
    card = spec.capability_card()
    assert card["protocol_version"] == "tool_protocol_v2"
    assert card["category"] == "analysis"
    assert card["transport"] == "local_python"
    assert card["side_effect_level"] == "read_only"
    assert card["requires_confirmation"] is False
    assert "log" in card["active_context_keys"]
    assert card["owned_by_skill"] == "LogsAnalyzeSkill"
    assert card["executor"] is None
    assert "log_file_path" in card["optional_payload_fields"]
    assert card["input_schema"]["type"] == "object"


def test_web_search_tool_is_read_only_and_budget_gated() -> None:
    spec = get_tool_spec("web_search_knowledge")

    assert spec is not None
    card = spec.capability_card()
    assert card["category"] == "retrieval"
    assert card["side_effect_level"] == "read_only"
    assert card["allowed_in_free_chat"] is True
    assert card["permission_gate"] == "read_only_web_budget"
    assert card["input_schema"]["required"] == ["query"]


def test_web_memory_tool_is_read_only_local_recall() -> None:
    spec = get_tool_spec("recall_web_memory")

    assert spec is not None
    card = spec.capability_card()
    assert card["category"] == "retrieval"
    assert card["side_effect_level"] == "read_only"
    assert card["allowed_in_free_chat"] is True
    assert card["permission_gate"] == "read_only_local_memory"
    assert card["input_schema"]["required"] == ["query"]


def test_confirmed_write_tool_requires_permission_gate() -> None:
    spec = get_tool_spec("execute_asset_operation")

    assert spec is not None
    card = spec.capability_card()
    assert card["category"] == "write"
    assert card["side_effect_level"] == "confirmed_write"
    assert card["requires_confirmation"] is True
    assert card["permission_gate"] == "proposal_confirmed"


def test_code_write_tool_is_confirmed_write() -> None:
    spec = get_tool_spec("write_code_files")

    assert spec is not None
    card = spec.capability_card()
    assert card["owned_by_skill"] == "CodeGenerateSkill"
    assert card["side_effect_level"] == "confirmed_write"
    assert card["category"] == "write"
    assert card["requires_confirmation"] is True
    assert card["allowed_in_free_chat"] is False


def test_code_preflight_tool_is_read_only() -> None:
    spec = get_tool_spec("preflight_generated_code")

    assert spec is not None
    card = spec.capability_card()
    assert card["owned_by_skill"] == "CodeGenerateSkill"
    assert card["side_effect_level"] == "read_only"
    assert card["category"] == "analysis"
    assert card["requires_confirmation"] is False
    assert card["required_payload_fields"] == ["generated_items"]


def test_tool_registry_contracts_are_valid() -> None:
    report = validate_tool_registry()

    assert report["ok"] is True
    assert report["issue_count"] == 0


def test_tool_debug_policy_card_exposes_executor_metadata() -> None:
    spec = get_tool_spec("analyze_ue_log")

    assert spec is not None
    card = spec.debug_policy_card()
    assert "executor" in card
    assert card["executor"] is None


def test_migrated_read_only_tools_expose_context_executors() -> None:
    read_file = get_tool_spec("read_project_file")
    config_validate = get_tool_spec("validate_design_config")

    assert read_file is not None
    assert config_validate is not None
    assert read_file.executor == "app.tools.project_file:read_project_file_executor"
    assert config_validate.executor == "app.tools.config_validate:validate_design_config_executor"


def test_tool_call_contract_reports_missing_required_input() -> None:
    result = validate_tool_call_input("read_project_file", {"file_path": "Source/Demo.cpp"})

    assert result["ok"] is False
    assert result["status"] == "invalid_input"
    assert result["missing_fields"] == ["project_root"]


def test_tool_result_contract_accepts_project_file_result() -> None:
    result = validate_tool_result(
        "read_project_file",
        {
            "status": "completed",
            "reason": "read_completed",
            "file_path": "Source/Demo.cpp",
            "resolved_path": "D:/Project/Source/Demo.cpp",
            "bytes_read": 120,
            "truncated": False,
            "text_excerpt": "void Foo() {}",
        },
    )

    assert result["ok"] is True
    assert result["status"] == "ok"
