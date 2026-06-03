from __future__ import annotations

from typing import Any

from app.schemas.requests import EditorOperationResultRequest

BLUEPRINT_GRAPH_RESULT_OPERATION_TYPES = {
    "add_blueprint_variable",
    "add_blueprint_component",
    "create_blueprint_event_stub",
    "add_blueprint_node_template",
    "connect_blueprint_nodes",
    "compile_blueprint",
}

BLUEPRINT_TEMPLATES_EXPECTING_LINKED_PINS = {
    "print_string",
    "branch_print_string",
    "enhanced_input_print_string",
    "sequence_print_strings",
    "set_variable",
    "call_function",
    "custom_event_print_string",
}


def collection_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return 1 if value else 0
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1 if str(value or "").strip() else 0


def first_non_empty_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def blueprint_graph_result_diagnostics(
    *,
    request: EditorOperationResultRequest,
    preview: dict[str, Any],
    result: dict[str, Any],
    dirty_packages: list[str],
) -> dict[str, Any]:
    operation_type = str(preview.get("operation_type") or request.operation_type or "")
    if operation_type not in BLUEPRINT_GRAPH_RESULT_OPERATION_TYPES:
        return {}

    payload = dict(preview.get("operation_payload") or {})
    template_id = first_non_empty_text(
        result.get("template_id"),
        payload.get("template_id"),
    )
    compile_status = first_non_empty_text(result.get("compile_status"))
    created_node_count = collection_count(result.get("created_nodes"))
    linked_node_count = collection_count(result.get("linked_nodes"))
    linked_pin_count = collection_count(result.get("linked_pins"))
    result_fields = list(dict(preview.get("expected_result_contract") or {}).get("operation_result_fields") or [])
    compile_requested = bool(payload.get("compile_after_edit"))
    expects_created_nodes = operation_type == "add_blueprint_node_template"
    expects_linked_pins = (
        operation_type == "connect_blueprint_nodes" or template_id in BLUEPRINT_TEMPLATES_EXPECTING_LINKED_PINS
    )

    diagnostic_flags: list[str] = []
    if request.success and expects_created_nodes and created_node_count == 0:
        diagnostic_flags.append("created_nodes_missing")
    if request.success and expects_linked_pins and linked_pin_count == 0:
        diagnostic_flags.append("expected_linked_pins_missing")
    if compile_requested and not compile_status:
        diagnostic_flags.append("compile_status_missing")
    if compile_status.lower() in {"failed", "error", "compile_failed", "blocked"}:
        diagnostic_flags.append("compile_failed")
    if request.success and "dirty_packages" in result_fields and not dirty_packages:
        diagnostic_flags.append("dirty_packages_missing")

    repair_advice = blueprint_graph_repair_advice(
        operation_type=operation_type,
        diagnostic_flags=diagnostic_flags,
        request=request,
        payload=payload,
        result=result,
        template_id=template_id,
        compile_status=compile_status,
    )
    return {
        "schema_version": "blueprint_graph_operation_diagnostics_v1",
        "category": "blueprint_graph",
        "operation_type": operation_type,
        "blueprint_path": first_non_empty_text(
            result.get("blueprint_path"),
            payload.get("blueprint_path"),
        ),
        "graph_name": first_non_empty_text(
            result.get("graph_name"),
            payload.get("graph_name"),
        ),
        "template_id": template_id,
        "entry_event": first_non_empty_text(
            result.get("entry_event"),
            payload.get("entry_event"),
        ),
        "compile_requested": compile_requested,
        "compile_status": compile_status,
        "created_node_count": created_node_count,
        "linked_node_count": linked_node_count,
        "linked_pin_count": linked_pin_count,
        "has_graph_changes": created_node_count > 0 or linked_pin_count > 0,
        "diagnostic_flags": diagnostic_flags,
        "needs_user_attention": (not request.success) or bool(diagnostic_flags),
        "repair_advice": repair_advice,
    }


def blueprint_graph_repair_advice(
    *,
    operation_type: str,
    diagnostic_flags: list[str],
    request: EditorOperationResultRequest,
    payload: dict[str, Any],
    result: dict[str, Any],
    template_id: str,
    compile_status: str,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    flag_set = set(diagnostic_flags)
    blueprint_path = first_non_empty_text(
        result.get("blueprint_path"),
        payload.get("blueprint_path"),
    )
    graph_name = first_non_empty_text(
        result.get("graph_name"),
        payload.get("graph_name"),
    )
    entry_event = first_non_empty_text(
        result.get("entry_event"),
        payload.get("entry_event"),
    )

    if not request.success:
        actions.append(
            {
                "action_id": "inspect_ue_execution_errors",
                "severity": "error",
                "title": "Inspect UE execution errors",
                "details": (
                    "UEAgentTool reported that the editor operation did not complete successfully. "
                    "Check result.errors, Unreal Output Log, and the selected target before retrying."
                ),
                "next_step": "Fix the UE-side error or select a valid target, then create a new proposal.",
            }
        )
    if "created_nodes_missing" in flag_set:
        actions.append(
            {
                "action_id": "verify_blueprint_graph_target",
                "severity": "warning",
                "title": "Verify Blueprint graph target",
                "details": (
                    "The backend expected a Blueprint node to be created, but the UE result did not "
                    "report any created_nodes."
                ),
                "next_step": "Open the target Blueprint graph and confirm the graph exists before retrying.",
                "context": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "template_id": template_id,
                },
            }
        )
    if "expected_linked_pins_missing" in flag_set:
        actions.append(
            {
                "action_id": "connect_expected_exec_pins",
                "severity": "warning",
                "title": "Connect expected execution pins",
                "details": (
                    "A graph template that normally connects execution pins reported zero linked_pins. "
                    "This usually means the entry node, graph name, or created node handle was not resolved."
                ),
                "next_step": (
                    "If UE returned node ids, create a connect_blueprint_nodes proposal; otherwise retry "
                    "after opening the graph and using an explicit event or graph name."
                ),
                "context": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "entry_event": entry_event,
                    "template_id": template_id,
                },
            }
        )
    if "compile_status_missing" in flag_set:
        actions.append(
            {
                "action_id": "report_compile_status",
                "severity": "warning",
                "title": "Report Blueprint compile status",
                "details": "The proposal requested compile_after_edit, but the UE result did not include compile_status.",
                "next_step": "Make the UE execution path report compile_status and compile messages after compile.",
            }
        )
    if "compile_failed" in flag_set:
        actions.append(
            {
                "action_id": "open_blueprint_compile_results",
                "severity": "error",
                "title": "Inspect Blueprint compile results",
                "details": f"Blueprint compile status was `{compile_status}`.",
                "next_step": (
                    "Open the Blueprint compiler messages, fix broken pins or missing references, then retry compile."
                ),
                "context": {
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                },
            }
        )
    if "dirty_packages_missing" in flag_set:
        actions.append(
            {
                "action_id": "report_dirty_packages",
                "severity": "info",
                "title": "Report dirty package paths",
                "details": (
                    "The operation succeeded, but UE did not report dirty_packages, so the backend cannot "
                    "tell which package needs saving."
                ),
                "next_step": "Return dirty_packages or an explicit save_policy from UEAgentTool.",
            }
        )

    known_flags = {
        "created_nodes_missing",
        "expected_linked_pins_missing",
        "compile_status_missing",
        "compile_failed",
        "dirty_packages_missing",
    }
    unknown_flags = sorted(flag_set - known_flags)
    if unknown_flags:
        actions.append(
            {
                "action_id": "inspect_unknown_diagnostic_flags",
                "severity": "warning",
                "title": "Inspect unknown diagnostic flags",
                "details": "The result included diagnostic flags without a dedicated repair rule.",
                "next_step": "Check Debug View and update backend repair advice rules if this case is common.",
                "context": {"unknown_flags": unknown_flags},
            }
        )

    if not actions:
        return {
            "schema_version": "blueprint_graph_repair_advice_v1",
            "status": "not_needed",
            "severity": "info",
            "can_auto_retry": False,
            "safe_next_step": "none",
            "actions": [],
        }

    severity = "error" if any(item["severity"] == "error" for item in actions) else "warning"
    return {
        "schema_version": "blueprint_graph_repair_advice_v1",
        "status": "suggested",
        "severity": severity,
        "can_auto_retry": False,
        "safe_next_step": "manual_review",
        "operation_type": operation_type,
        "actions": actions,
    }


__all__ = [
    "blueprint_graph_repair_advice",
    "blueprint_graph_result_diagnostics",
    "collection_count",
    "first_non_empty_text",
]
