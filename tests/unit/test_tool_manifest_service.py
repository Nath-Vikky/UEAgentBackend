from __future__ import annotations

from app.services.tool_manifest_service import build_tool_manifest


def _tool_by_annotation_tool_id(manifest: dict, tool_id: str) -> dict:
    for tool in manifest["tools"]:
        annotations = tool.get("annotations") or {}
        if annotations.get("tool_id") == tool_id:
            return tool
    raise AssertionError(f"Tool `{tool_id}` not found in manifest")


def test_tool_manifest_exports_mcp_compatible_tool_shape() -> None:
    manifest = build_tool_manifest()

    assert manifest["protocol_version"] == "tool_manifest_v1"
    assert manifest["schema_version"] == "mcp_tools_list_compatible_v1"
    assert manifest["mode"] == "http_primary_mcp_compatible_manifest"
    assert manifest["summary"]["tool_count"] >= 25
    assert manifest["routes"]["local_readonly_tool_call"] == "POST /api/v1/mcp/tool-registry/tools/{tool}/call"
    assert manifest["routes"]["confirmed_write_proposal"] == "POST /api/v1/editor-operations/proposals"
    assert manifest["safety_policy"]["read_only_local_tool_registry_call_allowed"] is True

    sample = manifest["tools"][0]
    assert set(sample) == {"name", "description", "inputSchema", "annotations"}
    assert "tool_id" in sample["annotations"]
    assert "execution_boundary" in sample["annotations"]


def test_tool_manifest_marks_confirmed_write_as_proposal_only() -> None:
    manifest = build_tool_manifest(side_effect_level="confirmed_write")
    tool = _tool_by_annotation_tool_id(manifest, "editor_arrange_actors_pattern")
    annotations = tool["annotations"]
    boundary = annotations["execution_boundary"]

    assert annotations["requires_confirmation"] is True
    assert annotations["side_effect_level"] == "confirmed_write"
    assert boundary["mode"] == "confirmed_write_proposal"
    assert boundary["direct_mcp_call_allowed"] is False
    assert boundary["write_path"] == "POST /api/v1/editor-operations/proposals"
    assert manifest["safety_policy"]["confirmed_write_direct_mcp_call_allowed"] is False


def test_tool_manifest_uses_mcp_tool_name_for_mcp_transports() -> None:
    manifest = build_tool_manifest(transport="mcp_tcp")
    blueprint_graph = _tool_by_annotation_tool_id(manifest, "mcp_get_blueprint_graph")

    assert blueprint_graph["name"] == "get_blueprint_graph"
    assert blueprint_graph["annotations"]["transport"] == "mcp_tcp"
    assert blueprint_graph["annotations"]["operation_family"] == "blueprint"
    assert blueprint_graph["annotations"]["frontend_executor_id"] == "get_blueprint_graph"
    assert blueprint_graph["annotations"]["bridge_kind"] == "mcp_readonly_or_inventory_fallback"
    assert blueprint_graph["annotations"]["execution_boundary"]["mode"] == "readonly_tool"
    assert blueprint_graph["annotations"]["execution_boundary"]["local_tool_registry_call_allowed"] is True


def test_tool_manifest_adds_frontend_executor_metadata_for_editor_tools() -> None:
    manifest = build_tool_manifest()
    arrange = _tool_by_annotation_tool_id(manifest, "editor_arrange_actors_pattern")
    material_detail = _tool_by_annotation_tool_id(manifest, "editor_inspect_material_instance_detail")

    assert arrange["annotations"]["operation_family"] == "level"
    assert arrange["annotations"]["frontend_executor_id"] == "arrange_actors_pattern"
    assert arrange["annotations"]["operation_type"] == "arrange_actors_pattern"
    assert arrange["annotations"]["bridge_kind"] == "editor_operation_proposal"
    assert material_detail["annotations"]["operation_family"] == "material"
    assert material_detail["annotations"]["frontend_executor_id"] == "inspect_material_instance_detail"
    assert material_detail["annotations"]["bridge_kind"] == "inventory_readonly"


def test_tool_manifest_filters_category_and_enabled_tools() -> None:
    manifest = build_tool_manifest(include_disabled=False, category="write")

    assert manifest["filters"]["include_disabled"] is False
    assert manifest["filters"]["category"] == "write"
    assert manifest["summary"]["tool_count"] == manifest["summary"]["enabled_tool_count"]
    assert all(tool["annotations"]["category"] == "write" for tool in manifest["tools"])
