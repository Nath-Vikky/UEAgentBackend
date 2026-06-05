from __future__ import annotations

import re
import uuid
from typing import Any

from app.schemas.requests import EditorOperationProposalRequest, UnifiedTaskRequest
from app.services.editor_operation_service import EditorOperationService
from app.services.editor_operations.catalog import OPERATION_SPECS

WORKFLOW_PLAN_SCHEMA_VERSION = "editor_workflow_plan_v1"
WORKFLOW_STEP_MATERIALIZATION_SCHEMA_VERSION = "editor_workflow_step_materialization_v1"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _plan_asset_path(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    try:
        return EditorOperationService._normalize_asset_path(text)
    except Exception:
        return text


def _quoted_text(goal: str) -> str:
    match = re.search(r"[\"'“”‘’](.+?)[\"'“”‘’]", goal)
    return match.group(1).strip() if match else ""


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def _workflow_completed_step_ids(*contexts: dict[str, Any]) -> set[str]:
    completed: set[str] = set()
    for context in contexts:
        safe_context = _as_dict(context)
        candidates = [
            safe_context.get("completed_step_ids"),
            safe_context.get("workflow_completed_step_ids"),
            _as_dict(safe_context.get("workflow_state")).get("completed_step_ids"),
            _as_dict(safe_context.get("workflow_materialization")).get("completed_step_ids"),
        ]
        for candidate in candidates:
            for item in _as_string_list(candidate):
                completed.add(item)
    return completed


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _context_section(context: dict[str, Any], *path: str) -> dict[str, Any]:
    current: Any = context
    for key in path:
        current = _as_dict(current).get(key)
    return _as_dict(current)


def _context_value(context: dict[str, Any], *paths: tuple[str, ...]) -> str:
    for path in paths:
        current: Any = context
        for key in path:
            current = _as_dict(current).get(key)
        text = _clean_text(current)
        if text:
            return text
    return ""


def _blueprint_edit_context(context: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(context.get("blueprint_edit_context"))
    if direct:
        return direct
    nested = _context_section(context, "active_context", "blueprint_edit_context")
    if nested:
        return nested
    context_pack = _context_section(context, "context_pack", "active_layer", "blueprint_edit_context")
    if context_pack:
        return context_pack
    return {}


def _umg_edit_context(context: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(context.get("umg_edit_context"))
    if direct:
        return direct
    nested = _context_section(context, "active_context", "umg_edit_context")
    if nested:
        return nested
    context_pack = _context_section(context, "context_pack", "active_layer", "umg_edit_context")
    if context_pack:
        return context_pack
    return {}


def _active_widget_blueprint_path(context: dict[str, Any]) -> str:
    edit_context = _umg_edit_context(context)
    return _first_non_empty(
        edit_context.get("widget_blueprint_path"),
        edit_context.get("blueprint_path"),
        _context_value(
            context,
            ("active_context", "umg", "current_widget_blueprint_path"),
            ("active_context", "umg", "widget_blueprint_path"),
            ("active_context", "editor_focus", "current_widget_blueprint_path"),
            ("editor_context", "current_widget_blueprint_path"),
            ("editor_context", "widget_blueprint_path"),
            ("editor_state", "current_widget_blueprint_path"),
            ("editor_state", "widget_blueprint_path"),
            ("context_pack", "active_layer", "umg", "current_widget_blueprint_path"),
        ),
    )


def _active_umg_parent_widget_name(context: dict[str, Any]) -> str:
    edit_context = _umg_edit_context(context)
    cursor_widget = _as_dict(edit_context.get("cursor_widget"))
    return _first_non_empty(
        cursor_widget.get("widget_name"),
        cursor_widget.get("name"),
        cursor_widget.get("id"),
        edit_context.get("root_widget_name"),
        _context_value(
            context,
            ("active_context", "umg", "current_widget_summary", "widget_name"),
            ("active_context", "umg", "current_widget_summary", "name"),
            ("active_context", "umg", "root_widget_name"),
            ("context_pack", "active_layer", "umg", "root_widget_name"),
        ),
    )


def _active_blueprint_path(context: dict[str, Any]) -> str:
    blueprint = _context_section(context, "active_context", "blueprint")
    last_operation = _as_dict(blueprint.get("last_successful_operation"))
    last_target = _as_dict(last_operation.get("target"))
    edit_context = _blueprint_edit_context(context)
    return _first_non_empty(
        edit_context.get("blueprint_path"),
        _context_value(
            context,
            ("active_context", "blueprint", "current_blueprint_path"),
            ("active_context", "blueprint", "blueprint_path"),
            ("active_context", "editor_focus", "current_blueprint_path"),
            ("editor_context", "current_blueprint_path"),
            ("editor_context", "blueprint_path"),
            ("editor_state", "current_blueprint_path"),
            ("editor_state", "blueprint_path"),
            ("context_pack", "active_layer", "blueprint", "current_blueprint_path"),
        ),
        last_target.get("blueprint_path"),
        last_operation.get("blueprint_path"),
    )


def _active_graph_name(context: dict[str, Any]) -> str:
    blueprint = _context_section(context, "active_context", "blueprint")
    last_operation = _as_dict(blueprint.get("last_successful_operation"))
    last_target = _as_dict(last_operation.get("target"))
    edit_context = _blueprint_edit_context(context)
    return _first_non_empty(
        edit_context.get("graph_name"),
        edit_context.get("edit_function"),
        _context_value(
            context,
            ("active_context", "blueprint", "current_graph_name"),
            ("active_context", "blueprint", "graph_name"),
            ("active_context", "editor_focus", "current_graph_name"),
            ("editor_context", "current_graph_name"),
            ("editor_context", "graph_name"),
            ("editor_state", "current_graph_name"),
            ("editor_state", "graph_name"),
            ("context_pack", "active_layer", "blueprint", "current_graph_name"),
        ),
        last_target.get("graph_name"),
        last_operation.get("graph_name"),
    )


def _active_current_node_summary(context: dict[str, Any]) -> dict[str, Any]:
    edit_context = _blueprint_edit_context(context)
    cursor_node = _as_dict(edit_context.get("cursor_node"))
    return cursor_node or _context_section(context, "active_context", "blueprint", "current_node_summary")


def _active_current_graph_summary(context: dict[str, Any]) -> dict[str, Any]:
    graph_summary = _context_section(context, "active_context", "blueprint", "current_graph_summary")
    if graph_summary:
        return graph_summary
    edit_context = _blueprint_edit_context(context)
    graph_name = _first_non_empty(edit_context.get("graph_name"), edit_context.get("edit_function"))
    if not graph_name:
        return {}
    return {"graph_name": graph_name, "nodes": []}


def _node_reference(value: Any) -> str:
    return _clean_text(value).lower().replace("_", " ")


def _node_matches_reference(node: dict[str, Any], reference: str) -> bool:
    expected = _node_reference(reference)
    if not expected:
        return False
    for value in (
        node.get("node_id"),
        node.get("id"),
        node.get("node_name"),
        node.get("name"),
        node.get("title"),
        node.get("node_class"),
    ):
        candidate = _node_reference(value)
        if candidate and (expected == candidate or expected in candidate or candidate in expected):
            return True
    return False


def _find_graph_node(
    graph: dict[str, Any],
    *,
    reference: str = "",
    goal: str = "",
    exclude_node_id: str = "",
) -> dict[str, Any]:
    nodes = [item for item in list(graph.get("nodes") or []) if isinstance(item, dict)]
    if not nodes:
        return {}
    excluded = _clean_text(exclude_node_id).lower()
    for node in nodes:
        node_id = _clean_text(node.get("node_id") or node.get("id")).lower()
        if excluded and node_id == excluded:
            continue
        if _node_matches_reference(node, reference):
            return dict(node)
    goal_lower = goal.lower()
    for node in nodes:
        node_id = _clean_text(node.get("node_id") or node.get("id")).lower()
        if excluded and node_id == excluded:
            continue
        title = _clean_text(node.get("title") or node.get("node_name") or node.get("node_class")).lower()
        if title and title in goal_lower:
            return dict(node)
        if "print string" in goal_lower and "print" in title and "string" in title:
            return dict(node)
    return {}


def _node_identifier(node: dict[str, Any]) -> str:
    return _first_non_empty(node.get("node_id"), node.get("id"), node.get("node_name"), node.get("name"))


def _pin_name_from_node(node: dict[str, Any], *, direction: str) -> str:
    expected_direction = direction.lower()
    pins = [item for item in list(node.get("pins") or []) if isinstance(item, dict)]
    for pin in pins:
        pin_direction = _clean_text(pin.get("direction")).lower()
        pin_category = _clean_text(pin.get("category") or pin.get("pin_category") or pin.get("pin_type")).lower()
        if pin_direction == expected_direction and (pin_category == "exec" or not pin_category):
            return _first_non_empty(pin.get("pin_name"), pin.get("name"), pin.get("pin_id"), pin.get("id"))
    return ""


def _goal_mentions_graph_target(goal: str) -> bool:
    lower = str(goal or "").lower()
    compact = lower.replace("_", "").replace("-", "").replace(" ", "")
    return any(
        token in lower or token in compact
        for token in (
            "eventgraph",
            "event graph",
            "constructionscript",
            "construction script",
            "userconstructionscript",
        )
    )


def _resolve_blueprint_graph_name(
    *,
    goal: str,
    payload: dict[str, Any],
    context: dict[str, Any],
    detected_graph_name: str = "",
) -> str:
    payload_graph = _clean_text(payload.get("graph_name"))
    active_graph = _active_graph_name(context)
    detected_graph = _clean_text(detected_graph_name)
    goal_has_graph = _goal_mentions_graph_target(goal)

    for candidate in (payload_graph, detected_graph):
        if not candidate:
            continue
        if candidate != "EventGraph" or goal_has_graph or not active_graph:
            return candidate
    return _first_non_empty(active_graph, payload_graph, detected_graph, "EventGraph")


class EditorWorkflowPlannerService:
    """Builds multi-step editor workflow plans without executing writes."""

    @staticmethod
    def prepare_step_proposal_request(
        *,
        step: dict[str, Any] | None = None,
        create_request: dict[str, Any] | None = None,
        workflow_plan_id: str | None = None,
        requested_by: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_step = dict(step or {})
        if isinstance(safe_step.get("steps"), list) or isinstance(create_request, list):
            raise ValueError("workflow_step_materialization_accepts_one_step_only")

        missing_inputs = list(safe_step.get("missing_inputs") or [])
        if safe_step and (safe_step.get("proposal_ready") is False or missing_inputs):
            raise ValueError("workflow_step_not_ready_for_proposal")

        hint = dict(safe_step.get("create_request_hint") or {})
        request_json = dict(create_request or hint.get("json") or {})
        if not request_json:
            raise ValueError("workflow_step_create_request_missing")

        operation_type = _clean_text(request_json.get("operation_type"))
        if operation_type not in OPERATION_SPECS:
            raise ValueError("workflow_step_operation_type_invalid")

        payload = request_json.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("workflow_step_payload_must_be_object")

        step_context = dict(request_json.get("context") or {})
        external_context = dict(context or {})
        depends_on_step_ids = _as_string_list(safe_step.get("depends_on_step_ids"))
        completed_step_ids = _workflow_completed_step_ids(step_context, external_context)
        unmet_dependencies = [step_id for step_id in depends_on_step_ids if step_id not in completed_step_ids]
        if unmet_dependencies:
            raise ValueError("workflow_step_dependencies_not_satisfied")

        workflow_step_id = _clean_text(safe_step.get("step_id") or step_context.get("workflow_step_id"))
        materialized_context = {
            **step_context,
            **external_context,
            "workflow_materialization": {
                "schema_version": WORKFLOW_STEP_MATERIALIZATION_SCHEMA_VERSION,
                "workflow_plan_id": _clean_text(workflow_plan_id),
                "workflow_step_id": workflow_step_id,
                "source": "editor_workflow_step_materialization",
                "auto_execute": False,
                "depends_on_step_ids": depends_on_step_ids,
                "completed_step_ids": sorted(completed_step_ids),
            },
        }
        proposal_request = EditorOperationProposalRequest(
            operation_type=operation_type,  # type: ignore[arg-type]
            payload=dict(payload),
            reason=_clean_text(request_json.get("reason")) or "Create a Proposal from one workflow step.",
            source_task_id=_clean_text(request_json.get("source_task_id")) or None,
            requested_by=requested_by or _clean_text(request_json.get("requested_by")) or "workflow_step_materialization",
            context=materialized_context,
        )
        return {
            "schema_version": WORKFLOW_STEP_MATERIALIZATION_SCHEMA_VERSION,
            "workflow_plan_id": _clean_text(workflow_plan_id),
            "workflow_step_id": workflow_step_id,
            "operation_type": operation_type,
            "tool_id": OPERATION_SPECS[operation_type]["tool_id"],
            "proposal_ready": True,
            "auto_execute": False,
            "requires_user_confirmation": True,
            "proposal_request": proposal_request.model_dump(mode="json"),
        }

    @staticmethod
    def detect_chat_workflow_request(
        request: UnifiedTaskRequest,
        context_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payload = dict(request.payload or {})
        explicit_workflow_type = _clean_text(
            payload.get("workflow_type")
            or payload.get("editor_workflow_type")
            or payload.get("workflow_plan_type")
        )
        goal = _clean_text(
            payload.get("goal")
            or payload.get("user_query")
            or payload.get("requirement_description")
            or (request.session.messages[-1].content if request.session.messages else "")
        )
        if not goal and not explicit_workflow_type:
            return None

        query_lower = goal.lower()
        has_multistep_signal = explicit_workflow_type or any(
            token in query_lower or token in goal
            for token in (
                "workflow",
                "plan",
                "multi-step",
                "step by step",
                "then",
                "after that",
                "and then",
                "先",
                "然后",
                "再",
                "步骤",
                "流程",
                "计划",
            )
        )
        if not has_multistep_signal:
            return None

        workflow_type = explicit_workflow_type or EditorWorkflowPlannerService._detect_workflow_type(goal, payload)
        if not workflow_type:
            return None

        safe_context = request.context.model_dump(mode="json")
        active_context = dict((context_bundle or {}).get("active_context") or {})
        editor_context = dict((context_bundle or {}).get("editor_context_structured") or {})
        workflow_context = {
            **safe_context,
            "active_context": active_context,
            "editor_context": editor_context,
        }
        plan_payload = dict(payload)
        if workflow_type == "blueprint_print_then_compile":
            detected_graph = EditorOperationService._detect_blueprint_graph_name_from_request(request, goal)
            plan_payload.setdefault(
                "blueprint_path",
                _plan_asset_path(
                    EditorOperationService._detect_blueprint_path_from_request(request, goal, context_bundle)
                    or _active_blueprint_path(workflow_context)
                    or ""
                ),
            )
            plan_payload.setdefault(
                "graph_name",
                _resolve_blueprint_graph_name(
                    goal=goal,
                    payload=plan_payload,
                    context=workflow_context,
                    detected_graph_name=detected_graph,
                ),
            )
        elif workflow_type == "blueprint_connect_then_compile":
            active_node = _active_current_node_summary(workflow_context)
            active_graph = _active_current_graph_summary(workflow_context)
            detected_graph = EditorOperationService._detect_blueprint_graph_name_from_request(request, goal)
            plan_payload.setdefault(
                "blueprint_path",
                _plan_asset_path(
                    EditorOperationService._detect_blueprint_path_from_request(request, goal, context_bundle)
                    or _active_blueprint_path(workflow_context)
                    or ""
                ),
            )
            plan_payload.setdefault(
                "graph_name",
                _resolve_blueprint_graph_name(
                    goal=goal,
                    payload=plan_payload,
                    context=workflow_context,
                    detected_graph_name=detected_graph or _clean_text(active_graph.get("graph_name")),
                ),
            )
            plan_payload.setdefault("source_node_id", _node_identifier(active_node))
            if not plan_payload.get("source_pin_name"):
                source_pin = _pin_name_from_node(active_node, direction="output")
                if source_pin:
                    plan_payload["source_pin_name"] = source_pin
            target_reference = _first_non_empty(
                plan_payload.get("target_node_id"),
                plan_payload.get("target_node_name"),
                plan_payload.get("target_node_title"),
            )
            target_node = _find_graph_node(
                active_graph,
                reference=target_reference,
                goal=goal,
                exclude_node_id=_node_identifier(active_node),
            )
            if target_node:
                plan_payload.setdefault("target_node_id", _node_identifier(target_node))
                if not plan_payload.get("target_pin_name"):
                    target_pin = _pin_name_from_node(target_node, direction="input")
                    if target_pin:
                        plan_payload["target_pin_name"] = target_pin
        elif workflow_type == "blueprint_enhanced_input_print_then_compile":
            detected_graph = EditorOperationService._detect_blueprint_graph_name_from_request(request, goal)
            plan_payload.setdefault(
                "blueprint_path",
                _plan_asset_path(
                    EditorOperationService._detect_blueprint_path_from_request(request, goal, context_bundle)
                    or _active_blueprint_path(workflow_context)
                    or ""
                ),
            )
            plan_payload.setdefault(
                "graph_name",
                _resolve_blueprint_graph_name(
                    goal=goal,
                    payload=plan_payload,
                    context=workflow_context,
                    detected_graph_name=detected_graph,
                ),
            )
            plan_payload.setdefault(
                "input_action_path",
                _plan_asset_path(
                    EditorOperationService._detect_input_action_path_from_request(request, goal, context_bundle)
                ),
            )
        elif workflow_type == "umg_hud_group":
            plan_payload.setdefault(
                "widget_blueprint_path",
                _plan_asset_path(
                    EditorOperationService._detect_widget_blueprint_path_from_request(request, goal, context_bundle)
                    or _active_widget_blueprint_path(workflow_context)
                    or ""
                ),
            )
            parent_widget_name = EditorOperationService._detect_new_parent_widget_name_from_request(request, goal)
            detected_text = EditorOperationService._detect_umg_text_from_request(request, goal)
            if parent_widget_name:
                plan_payload.setdefault("parent_widget_name", parent_widget_name)
            if detected_text:
                plan_payload.setdefault("label_text", detected_text)
        elif workflow_type == "umg_text_widget":
            plan_payload.setdefault(
                "widget_blueprint_path",
                _plan_asset_path(
                    EditorOperationService._detect_widget_blueprint_path_from_request(request, goal, context_bundle)
                    or _active_widget_blueprint_path(workflow_context)
                    or ""
                ),
            )
            detected_widget_name = EditorOperationService._detect_widget_name_from_request(request, goal)
            detected_text = EditorOperationService._detect_umg_text_from_request(request, goal)
            detected_layout = EditorOperationService._detect_umg_layout_from_request(request, goal)
            detected_visibility = EditorOperationService._detect_umg_visibility_from_request(request, goal)
            active_parent_widget_name = _active_umg_parent_widget_name(workflow_context)
            if detected_widget_name:
                plan_payload.setdefault("widget_name", detected_widget_name)
            if active_parent_widget_name:
                plan_payload.setdefault("parent_widget_name", active_parent_widget_name)
            if detected_text:
                plan_payload.setdefault("text", detected_text)
            if detected_layout:
                plan_payload.setdefault("layout", detected_layout)
            if detected_visibility:
                plan_payload.setdefault("visibility", detected_visibility)
        elif workflow_type == "arrange_and_tag_actors":
            plan_payload.setdefault(
                "actor_references",
                EditorOperationService._detect_actor_references_from_request(request, goal, context_bundle),
            )
            plan_payload.setdefault("pattern", EditorOperationService._detect_arrange_pattern_from_request(request, goal))
            metadata = EditorOperationService._detect_actor_metadata_from_request(request, goal)
            if metadata:
                plan_payload.setdefault("metadata", metadata)

        return {
            "goal": goal,
            "workflow_type": workflow_type,
            "payload": plan_payload,
            "context": workflow_context,
            "requested_by": "agent_chat_workflow_planner",
        }

    @staticmethod
    def workflow_templates() -> dict[str, Any]:
        return {
            "schema_version": "editor_workflow_templates_v1",
            "mode": "plan_only_confirmed_step_workflows",
            "auto_execute": False,
            "requires_user_confirmation_per_step": True,
            "template_count": 6,
            "templates": [
                {
                    "workflow_type": "blueprint_enhanced_input_print_then_compile",
                    "title": "Enhanced Input Print String Then Compile",
                    "description": "Create a bounded Enhanced Input Triggered -> Print String template, then compile the Blueprint as a second Proposal step.",
                    "required_payload_fields": ["blueprint_path", "input_action_path"],
                    "optional_payload_fields": ["graph_name", "message"],
                    "emitted_operation_types": ["add_blueprint_node_template", "compile_blueprint"],
                    "boundary": "Existing UInputAction asset only; no input mapping context edits or arbitrary graph wiring.",
                },
                {
                    "workflow_type": "blueprint_connect_then_compile",
                    "title": "Blueprint Connect Pins Then Compile",
                    "description": "Connect two explicit Blueprint pins, then compile the Blueprint as a second Proposal step.",
                    "required_payload_fields": [
                        "blueprint_path",
                        "graph_name",
                        "source_node_id",
                        "source_pin_name",
                        "target_node_id",
                        "target_pin_name",
                    ],
                    "optional_payload_fields": ["target_node_name", "target_node_title"],
                    "emitted_operation_types": ["connect_blueprint_nodes", "compile_blueprint"],
                    "boundary": "Requires explicit node/pin identifiers or current graph focus; does not guess arbitrary Blueprint wiring.",
                },
                {
                    "workflow_type": "blueprint_print_then_compile",
                    "title": "Blueprint Print String Then Compile",
                    "description": "Add a BeginPlay Print String or Delay -> PrintString template, then compile the Blueprint as a second Proposal step.",
                    "required_payload_fields": ["blueprint_path"],
                    "optional_payload_fields": ["graph_name", "message", "delay_seconds"],
                    "emitted_operation_types": ["add_blueprint_node_template", "compile_blueprint"],
                    "boundary": "Template-based graph edit only; does not create arbitrary Blueprint nodes.",
                },
                {
                    "workflow_type": "umg_text_widget",
                    "title": "UMG Text Widget",
                    "description": "Add a TextBlock, set its text, and optionally apply safe CanvasPanelSlot layout or visibility.",
                    "required_payload_fields": ["widget_blueprint_path", "text"],
                    "optional_payload_fields": [
                        "widget_name",
                        "widget_class",
                        "parent_widget_name",
                        "layout",
                        "visibility",
                    ],
                    "emitted_operation_types": [
                        "add_umg_widget",
                        "set_umg_widget_text",
                        "set_umg_widget_layout",
                        "set_umg_widget_visibility",
                    ],
                    "boundary": "Safe UMG widget/template fields only; no animations, bindings, or complex widget-tree rewrites.",
                },
                {
                    "workflow_type": "umg_hud_group",
                    "title": "UMG HUD Group",
                    "description": "Plan a small HUD group under an existing panel using add_umg_widget steps: HorizontalBox, Image, TextBlock, and Button.",
                    "required_payload_fields": ["widget_blueprint_path"],
                    "optional_payload_fields": [
                        "parent_widget_name",
                        "group_name",
                        "icon_widget_name",
                        "label_widget_name",
                        "button_widget_name",
                        "label_text",
                    ],
                    "emitted_operation_types": ["add_umg_widget"],
                    "boundary": "Plan-only simple widget-tree scaffolding; no bindings, animations, button behavior, or responsive layout generation.",
                },
                {
                    "workflow_type": "arrange_and_tag_actors",
                    "title": "Arrange And Tag Actors",
                    "description": "Arrange existing Level Actors, then optionally apply the same metadata to each Actor.",
                    "required_payload_fields": ["actor_references"],
                    "optional_payload_fields": ["pattern", "metadata"],
                    "emitted_operation_types": ["arrange_actors_pattern", "set_actor_metadata"],
                    "boundary": "Existing Actors only; no create/delete/attach/stream/save operations.",
                },
            ],
            "safety_policy": {
                "planner_creates_proposals": False,
                "planner_executes_editor_writes": False,
                "step_submission_endpoint": "POST /api/v1/editor-operations/proposals",
                "ue_execution_requires_user_confirmation": True,
            },
        }

    def plan_workflow(
        self,
        *,
        goal: str,
        workflow_type: str | None = None,
        payload: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        requested_by: str = "workflow_planner",
    ) -> dict[str, Any]:
        safe_payload = dict(payload or {})
        safe_context = dict(context or {})
        safe_goal = _clean_text(goal)
        resolved_type = _clean_text(workflow_type) or self._detect_workflow_type(safe_goal, safe_payload)
        if resolved_type == "blueprint_print_then_compile":
            return self._blueprint_print_then_compile(
                goal=safe_goal,
                payload=safe_payload,
                context=safe_context,
                requested_by=requested_by,
            )
        if resolved_type == "blueprint_connect_then_compile":
            return self._blueprint_connect_then_compile(
                goal=safe_goal,
                payload=safe_payload,
                context=safe_context,
                requested_by=requested_by,
            )
        if resolved_type == "blueprint_enhanced_input_print_then_compile":
            return self._blueprint_enhanced_input_print_then_compile(
                goal=safe_goal,
                payload=safe_payload,
                context=safe_context,
                requested_by=requested_by,
            )
        if resolved_type == "umg_text_widget":
            return self._umg_text_widget(
                goal=safe_goal,
                payload=safe_payload,
                context=safe_context,
                requested_by=requested_by,
            )
        if resolved_type == "umg_hud_group":
            return self._umg_hud_group(
                goal=safe_goal,
                payload=safe_payload,
                context=safe_context,
                requested_by=requested_by,
            )
        if resolved_type == "arrange_and_tag_actors":
            return self._arrange_and_tag_actors(
                goal=safe_goal,
                payload=safe_payload,
                context=safe_context,
                requested_by=requested_by,
            )
        return self._plan_envelope(
            workflow_type=resolved_type or "unsupported",
            goal=safe_goal,
            steps=[],
            status="unsupported",
            reason="workflow_type_not_supported_or_not_detected",
            safety_notes=[
                "The planner did not create proposals.",
                "Use explicit operation proposals for unsupported workflows.",
            ],
        )

    @staticmethod
    def _detect_workflow_type(goal: str, payload: dict[str, Any]) -> str:
        explicit = _clean_text(payload.get("workflow_type"))
        if explicit:
            return explicit
        lower = goal.lower()
        if ("connect" in lower or "wire" in lower or "link" in lower or "连接" in lower or "连线" in lower) and (
            "compile" in lower or "编译" in lower or "then" in lower or "然后" in lower
        ):
            return "blueprint_connect_then_compile"
        if (
            "compile" in lower
            or "then" in lower
            or "然后" in lower
            or "编译" in lower
        ) and (
            "enhanced input" in lower
            or "input action" in lower
            or "ia_" in lower
            or "增强输入" in goal
        ):
            return "blueprint_enhanced_input_print_then_compile"
        if "print string" in lower or ("beginplay" in lower and "compile" in lower):
            return "blueprint_print_then_compile"
        if any(token in lower for token in ("hud group", "hud panel", "ui group", "status hud", "status group")):
            return "umg_hud_group"
        if any(token in lower for token in ("umg", "widget", "textblock", "hud", "ui")):
            return "umg_text_widget"
        if any(token in lower for token in ("arrange", "layout actors", "grid", "circle", "排列", "阵列")) and (
            "tag" in lower or "folder" in lower or "label" in lower or "actor" in lower
        ):
            return "arrange_and_tag_actors"
        return ""

    def _blueprint_print_then_compile(
        self,
        *,
        goal: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        blueprint_path = _first_non_empty(
            payload.get("blueprint_path"),
            context.get("blueprint_path"),
            context.get("current_blueprint_path"),
            _active_blueprint_path(context),
        )
        blueprint_path = _plan_asset_path(blueprint_path)
        graph_name = _resolve_blueprint_graph_name(goal=goal, payload=payload, context=context)
        entry_event = _first_non_empty(
            payload.get("entry_event"),
            context.get("entry_event"),
            "BeginPlay" if graph_name == "EventGraph" else "",
        )
        message = _first_non_empty(payload.get("message"), _quoted_text(goal), "Hello from UEAgentCraft")
        goal_lower = goal.lower()
        delay_requested = bool(
            _clean_text(payload.get("delay_seconds"))
            or _clean_text(payload.get("delay"))
            or any(
                token in goal_lower or token in goal
                for token in (
                    "delay",
                    "wait",
                    "after",
                    "later",
                    "延迟",
                    "等待",
                    "秒后",
                    "之后",
                )
            )
        )
        template_id = "delay_print_string" if delay_requested else "print_string"
        node_title = "Add BeginPlay Delay -> Print String nodes" if delay_requested else "Add BeginPlay Print String node"
        node_payload: dict[str, Any] = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "template_id": template_id,
            "entry_event": entry_event,
            "message": message,
            "compile_after_edit": False,
        }
        if delay_requested:
            node_payload["delay_seconds"] = (
                payload.get("delay_seconds")
                or payload.get("delay")
                or EditorOperationService._extract_delay_seconds_from_text(goal, default=1.0)
            )
        steps = [
            self._step(
                index=0,
                operation_type="add_blueprint_node_template",
                title=node_title,
                payload=node_payload,
                missing_inputs=["blueprint_path"] if not blueprint_path else [],
                reason="Create the Blueprint graph node first, without auto-executing the write.",
                requested_by=requested_by,
            ),
            self._step(
                index=1,
                operation_type="compile_blueprint",
                title="Compile Blueprint after graph edit",
                payload={"blueprint_path": blueprint_path, "compile_mode": "default"},
                missing_inputs=["blueprint_path"] if not blueprint_path else [],
                reason="Compile is a separate confirmed step so users can inspect the graph edit first.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_add_blueprint_node_template"],
            ),
        ]
        return self._plan_envelope(
            workflow_type="blueprint_print_then_compile",
            goal=goal,
            steps=steps,
            status=self._status_for_steps(steps),
            reason="planned_blueprint_print_then_compile",
        )

    def _blueprint_connect_then_compile(
        self,
        *,
        goal: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        active_node = _active_current_node_summary(context)
        active_graph = _active_current_graph_summary(context)
        blueprint_path = _first_non_empty(
            payload.get("blueprint_path"),
            context.get("blueprint_path"),
            context.get("current_blueprint_path"),
            _active_blueprint_path(context),
        )
        blueprint_path = _plan_asset_path(blueprint_path)
        graph_name = _resolve_blueprint_graph_name(
            goal=goal,
            payload=payload,
            context=context,
            detected_graph_name=_clean_text(active_graph.get("graph_name")),
        )
        source_node_id = _first_non_empty(
            payload.get("source_node_id"),
            payload.get("source_node_name"),
            _node_identifier(active_node),
        )
        source_pin_name = _first_non_empty(
            payload.get("source_pin_name"),
            _pin_name_from_node(active_node, direction="output"),
        )
        target_reference = _first_non_empty(
            payload.get("target_node_id"),
            payload.get("target_node_name"),
            payload.get("target_node_title"),
        )
        target_node = _find_graph_node(
            active_graph,
            reference=target_reference,
            goal=goal,
            exclude_node_id=source_node_id,
        )
        target_node_id = _first_non_empty(
            payload.get("target_node_id"),
            _node_identifier(target_node),
            payload.get("target_node_name"),
        )
        target_pin_name = _first_non_empty(
            payload.get("target_pin_name"),
            _pin_name_from_node(target_node, direction="input"),
        )
        connect_payload = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "source_node_id": source_node_id,
            "source_pin_name": source_pin_name,
            "target_node_id": target_node_id,
            "target_pin_name": target_pin_name,
            "compile_after_edit": False,
        }
        missing_connect = [key for key, value in connect_payload.items() if key != "compile_after_edit" and not value]
        steps = [
            self._step(
                index=0,
                operation_type="connect_blueprint_nodes",
                title="Connect explicit Blueprint pins",
                payload=connect_payload,
                missing_inputs=missing_connect,
                reason=(
                    "Connect explicit pins as a confirmed Proposal step. The planner only uses "
                    "provided node/pin ids or current graph focus; it does not guess arbitrary wiring."
                ),
                requested_by=requested_by,
            ),
            self._step(
                index=1,
                operation_type="compile_blueprint",
                title="Compile Blueprint after pin connection",
                payload={"blueprint_path": blueprint_path, "compile_mode": "default"},
                missing_inputs=["blueprint_path"] if not blueprint_path else [],
                reason="Compile is a separate confirmed step after the pin connection proposal.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_connect_blueprint_nodes"],
            ),
        ]
        return self._plan_envelope(
            workflow_type="blueprint_connect_then_compile",
            goal=goal,
            steps=steps,
            status=self._status_for_steps(steps),
            reason="planned_blueprint_connect_then_compile",
        )

    def _blueprint_enhanced_input_print_then_compile(
        self,
        *,
        goal: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        blueprint_path = _first_non_empty(
            payload.get("blueprint_path"),
            context.get("blueprint_path"),
            context.get("current_blueprint_path"),
            _active_blueprint_path(context),
        )
        blueprint_path = _plan_asset_path(blueprint_path)
        graph_name = _resolve_blueprint_graph_name(goal=goal, payload=payload, context=context)
        input_action_path = _plan_asset_path(payload.get("input_action_path"))
        input_action_name = input_action_path.rstrip("/").rsplit("/", 1)[-1].split(".")[-1] if input_action_path else ""
        message = _first_non_empty(
            payload.get("message"),
            _quoted_text(goal),
            f"{input_action_name} triggered" if input_action_name else "",
            "Enhanced Input triggered",
        )
        node_payload = {
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "template_id": "enhanced_input_print_string",
            "entry_event": "",
            "input_action_path": input_action_path,
            "message": message,
            "compile_after_edit": False,
        }
        missing_node = [
            key
            for key, value in {
                "blueprint_path": blueprint_path,
                "input_action_path": input_action_path,
            }.items()
            if not value
        ]
        steps = [
            self._step(
                index=0,
                operation_type="add_blueprint_node_template",
                title="Add Enhanced Input Triggered -> Print String nodes",
                payload=node_payload,
                missing_inputs=missing_node,
                reason=(
                    "Create the Enhanced Input Print String template first. The template only uses an "
                    "existing UInputAction asset and does not edit input mapping contexts."
                ),
                requested_by=requested_by,
            ),
            self._step(
                index=1,
                operation_type="compile_blueprint",
                title="Compile Blueprint after Enhanced Input graph edit",
                payload={"blueprint_path": blueprint_path, "compile_mode": "default"},
                missing_inputs=["blueprint_path"] if not blueprint_path else [],
                reason="Compile is a separate confirmed step so users can inspect the graph edit first.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_add_blueprint_node_template"],
            ),
        ]
        return self._plan_envelope(
            workflow_type="blueprint_enhanced_input_print_then_compile",
            goal=goal,
            steps=steps,
            status=self._status_for_steps(steps),
            reason="planned_blueprint_enhanced_input_print_then_compile",
        )

    def _umg_text_widget(
        self,
        *,
        goal: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        widget_blueprint_path = _first_non_empty(
            payload.get("widget_blueprint_path"),
            _active_widget_blueprint_path(context),
            context.get("widget_blueprint_path"),
            context.get("current_widget_blueprint_path"),
        )
        widget_blueprint_path = _plan_asset_path(widget_blueprint_path)
        widget_name = _first_non_empty(payload.get("widget_name"), payload.get("name"), "AgentText")
        widget_class = _first_non_empty(payload.get("widget_class"), "TextBlock")
        text = _first_non_empty(payload.get("text"), _quoted_text(goal))
        parent_widget_name = _first_non_empty(payload.get("parent_widget_name"), payload.get("parent"), _active_umg_parent_widget_name(context))
        missing_base = [key for key, value in {"widget_blueprint_path": widget_blueprint_path, "text": text}.items() if not value]
        steps = [
            self._step(
                index=0,
                operation_type="add_umg_widget",
                title="Add TextBlock widget",
                payload={
                    "widget_blueprint_path": widget_blueprint_path,
                    "widget_name": widget_name,
                    "widget_class": widget_class,
                    "parent_widget_name": parent_widget_name,
                    "text": text,
                    "is_variable": True,
                },
                missing_inputs=missing_base,
                reason="Create the widget as a confirmed Proposal step.",
                requested_by=requested_by,
            ),
            self._step(
                index=1,
                operation_type="set_umg_widget_text",
                title="Set TextBlock text",
                payload={
                    "widget_blueprint_path": widget_blueprint_path,
                    "widget_name": widget_name,
                    "text": text,
                },
                missing_inputs=missing_base,
                reason="Set final visible copy as a separate inspectable step.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_add_umg_widget"],
            ),
        ]
        if isinstance(payload.get("layout"), dict):
            steps.append(
                self._step(
                    index=len(steps),
                    operation_type="set_umg_widget_layout",
                    title="Apply CanvasPanelSlot layout",
                    payload={
                        "widget_blueprint_path": widget_blueprint_path,
                        "widget_name": widget_name,
                        "layout": dict(payload["layout"]),
                    },
                    missing_inputs=["widget_blueprint_path"] if not widget_blueprint_path else [],
                    reason="Apply layout only when the caller supplies explicit safe layout fields.",
                    requested_by=requested_by,
                    depends_on_step_ids=["step_0_add_umg_widget"],
                )
            )
        if _clean_text(payload.get("visibility")):
            steps.append(
                self._step(
                    index=len(steps),
                    operation_type="set_umg_widget_visibility",
                    title="Set widget visibility",
                    payload={
                        "widget_blueprint_path": widget_blueprint_path,
                        "widget_name": widget_name,
                        "visibility": _clean_text(payload.get("visibility")),
                    },
                    missing_inputs=["widget_blueprint_path"] if not widget_blueprint_path else [],
                    reason="Visibility remains a separate confirmed step.",
                    requested_by=requested_by,
                    depends_on_step_ids=["step_0_add_umg_widget"],
                )
            )
        return self._plan_envelope(
            workflow_type="umg_text_widget",
            goal=goal,
            steps=steps,
            status=self._status_for_steps(steps),
            reason="planned_umg_text_widget",
        )

    def _umg_hud_group(
        self,
        *,
        goal: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        widget_blueprint_path = _first_non_empty(
            payload.get("widget_blueprint_path"),
            _active_widget_blueprint_path(context),
            context.get("widget_blueprint_path"),
            context.get("current_widget_blueprint_path"),
        )
        widget_blueprint_path = _plan_asset_path(widget_blueprint_path)
        parent_widget_name = _first_non_empty(payload.get("parent_widget_name"), payload.get("parent"), _active_umg_parent_widget_name(context))
        group_name = _first_non_empty(payload.get("group_name"), "AgentHUDGroup")
        icon_name = _first_non_empty(payload.get("icon_widget_name"), "AgentHUDIcon")
        label_name = _first_non_empty(payload.get("label_widget_name"), payload.get("widget_name"), "AgentHUDText")
        button_name = _first_non_empty(payload.get("button_widget_name"), "AgentHUDButton")
        label_text = _first_non_empty(payload.get("label_text"), payload.get("text"), _quoted_text(goal), "Ready")
        missing_base = ["widget_blueprint_path"] if not widget_blueprint_path else []
        steps = [
            self._step(
                index=0,
                operation_type="add_umg_widget",
                title="Add HUD HorizontalBox group",
                payload={
                    "widget_blueprint_path": widget_blueprint_path,
                    "widget_name": group_name,
                    "widget_class": "HorizontalBox",
                    "parent_widget_name": parent_widget_name,
                    "text": "",
                    "is_variable": True,
                },
                missing_inputs=missing_base,
                reason="Create a bounded HUD container as the first confirmed Proposal step.",
                requested_by=requested_by,
            ),
            self._step(
                index=1,
                operation_type="add_umg_widget",
                title="Add HUD icon Image",
                payload={
                    "widget_blueprint_path": widget_blueprint_path,
                    "widget_name": icon_name,
                    "widget_class": "Image",
                    "parent_widget_name": group_name,
                    "text": "",
                    "is_variable": True,
                },
                missing_inputs=missing_base,
                reason="Add a simple icon placeholder under the HUD group.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_add_umg_widget"],
            ),
            self._step(
                index=2,
                operation_type="add_umg_widget",
                title="Add HUD label TextBlock",
                payload={
                    "widget_blueprint_path": widget_blueprint_path,
                    "widget_name": label_name,
                    "widget_class": "TextBlock",
                    "parent_widget_name": group_name,
                    "text": label_text,
                    "is_variable": True,
                },
                missing_inputs=missing_base,
                reason="Add a visible HUD label under the HUD group.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_add_umg_widget"],
            ),
            self._step(
                index=3,
                operation_type="add_umg_widget",
                title="Add HUD action Button",
                payload={
                    "widget_blueprint_path": widget_blueprint_path,
                    "widget_name": button_name,
                    "widget_class": "Button",
                    "parent_widget_name": group_name,
                    "text": "",
                    "is_variable": True,
                },
                missing_inputs=missing_base,
                reason="Add a simple Button placeholder; behavior binding remains out of scope.",
                requested_by=requested_by,
                depends_on_step_ids=["step_0_add_umg_widget"],
            ),
        ]
        return self._plan_envelope(
            workflow_type="umg_hud_group",
            goal=goal,
            steps=steps,
            status=self._status_for_steps(steps),
            reason="planned_umg_hud_group",
        )

    def _arrange_and_tag_actors(
        self,
        *,
        goal: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        actor_references = _as_string_list(payload.get("actor_references") or context.get("actor_references"))
        pattern = dict(payload.get("pattern") or {"type": "line", "spacing": 200})
        metadata = dict(payload.get("metadata") or {})
        missing_arrange = ["actor_references"] if len(actor_references) < 2 else []
        steps = [
            self._step(
                index=0,
                operation_type="arrange_actors_pattern",
                title="Arrange existing Level Actors",
                payload={"actor_references": actor_references, "pattern": pattern},
                missing_inputs=missing_arrange,
                reason="Arrange the bounded Actor set first.",
                requested_by=requested_by,
            )
        ]
        if metadata:
            for actor_reference in actor_references[:12]:
                steps.append(
                    self._step(
                        index=len(steps),
                        operation_type="set_actor_metadata",
                        title=f"Apply metadata to {actor_reference}",
                        payload={"actor_reference": actor_reference, "metadata": metadata},
                        missing_inputs=[],
                        reason="Apply actor metadata as one confirmed Proposal per Actor.",
                        requested_by=requested_by,
                        depends_on_step_ids=["step_0_arrange_actors_pattern"],
                    )
                )
        return self._plan_envelope(
            workflow_type="arrange_and_tag_actors",
            goal=goal,
            steps=steps,
            status=self._status_for_steps(steps),
            reason="planned_arrange_and_tag_actors",
        )

    @staticmethod
    def _step(
        *,
        index: int,
        operation_type: str,
        title: str,
        payload: dict[str, Any],
        missing_inputs: list[str],
        reason: str,
        requested_by: str,
        depends_on_step_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        step_id = f"step_{index}_{operation_type}"
        spec = OPERATION_SPECS.get(operation_type, {})
        proposal_ready = not missing_inputs
        request_json = {
            "operation_type": operation_type,
            "payload": payload,
            "reason": reason,
            "requested_by": requested_by,
            "context": {"workflow_step_id": step_id},
        }
        return {
            "step_index": index,
            "step_id": step_id,
            "title": title,
            "operation_type": operation_type,
            "tool_id": spec.get("tool_id", ""),
            "risk_flags": spec.get("risk_flags", ""),
            "proposal_ready": proposal_ready,
            "missing_inputs": missing_inputs,
            "payload": payload,
            "depends_on_step_ids": list(depends_on_step_ids or []),
            "requires_confirmation": True,
            "auto_execute": False,
            "create_request_hint": {
                "method": "POST",
                "path": "/api/v1/editor-operations/proposals",
                "json": request_json,
            },
        }

    @staticmethod
    def _status_for_steps(steps: list[dict[str, Any]]) -> str:
        if not steps:
            return "unsupported"
        if all(bool(step.get("proposal_ready")) for step in steps):
            return "planned"
        if any(bool(step.get("proposal_ready")) for step in steps):
            return "partial"
        return "needs_more_input"

    @staticmethod
    def _dependency_state_for_step(step: dict[str, Any]) -> str:
        if step.get("missing_inputs") or not bool(step.get("proposal_ready")):
            return "needs_more_input"
        if step.get("depends_on_step_ids"):
            return "waiting_dependency"
        return "ready"

    @staticmethod
    def _dependency_graph_for_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        entry_step_ids: list[str] = []
        ready_step_ids: list[str] = []
        waiting_step_ids: list[str] = []
        missing_input_step_ids: list[str] = []

        for step in steps:
            step_id = _clean_text(step.get("step_id"))
            depends_on_step_ids = _as_string_list(step.get("depends_on_step_ids"))
            dependency_state = EditorWorkflowPlannerService._dependency_state_for_step(step)
            nodes.append(
                {
                    "step_id": step_id,
                    "step_index": step.get("step_index"),
                    "operation_type": step.get("operation_type"),
                    "proposal_ready": bool(step.get("proposal_ready")),
                    "depends_on_step_ids": depends_on_step_ids,
                    "dependency_state": dependency_state,
                    "missing_inputs": list(step.get("missing_inputs") or []),
                }
            )
            if not depends_on_step_ids:
                entry_step_ids.append(step_id)
            if dependency_state == "ready":
                ready_step_ids.append(step_id)
            elif dependency_state == "waiting_dependency":
                waiting_step_ids.append(step_id)
            else:
                missing_input_step_ids.append(step_id)
            for dependency_id in depends_on_step_ids:
                edges.append({"from_step_id": dependency_id, "to_step_id": step_id})

        return {
            "schema_version": "editor_workflow_dependency_graph_v1",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "has_dependencies": bool(edges),
            "entry_step_ids": entry_step_ids,
            "ready_step_ids": ready_step_ids,
            "waiting_step_ids": waiting_step_ids,
            "missing_input_step_ids": missing_input_step_ids,
            "nodes": nodes,
            "edges": edges,
        }

    @staticmethod
    def _plan_envelope(
        *,
        workflow_type: str,
        goal: str,
        steps: list[dict[str, Any]],
        status: str,
        reason: str,
        safety_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        ready_step_count = sum(1 for step in steps if bool(step.get("proposal_ready")))
        plan_id = f"workflow_plan_{uuid.uuid4().hex}"
        dependency_graph = EditorWorkflowPlannerService._dependency_graph_for_steps(steps)
        return {
            "schema_version": WORKFLOW_PLAN_SCHEMA_VERSION,
            "plan_id": plan_id,
            "workflow_type": workflow_type,
            "goal": goal,
            "status": status,
            "reason": reason,
            "step_count": len(steps),
            "ready_step_count": ready_step_count,
            "auto_execute": False,
            "requires_user_confirmation_per_step": True,
            "program_counter": {
                "workflow_id": plan_id,
                "current_step_index": 0 if steps else None,
                "state": status,
                "next_action": "create_ready_proposal_step" if ready_step_count else "collect_missing_inputs",
            },
            "dependency_graph": dependency_graph,
            "safety_notes": safety_notes
            or [
                "This is a plan only; it does not create proposals automatically.",
                "Each step must be submitted as a separate Proposal and confirmed by the user.",
                "UEAgentTool remains the only layer that executes Unreal Editor writes.",
            ],
            "steps": steps,
        }
