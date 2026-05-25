from __future__ import annotations

import re
import uuid
from typing import Any

from app.schemas.requests import EditorOperationProposalRequest, UnifiedTaskRequest
from app.services.editor_operation_service import EditorOperationService, OPERATION_SPECS

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
        plan_payload = dict(payload)
        if workflow_type == "blueprint_print_then_compile":
            plan_payload.setdefault(
                "blueprint_path",
                EditorOperationService._detect_blueprint_path_from_request(request, goal, context_bundle) or "",
            )
            plan_payload.setdefault("graph_name", EditorOperationService._detect_blueprint_graph_name_from_request(request, goal))
        elif workflow_type == "umg_text_widget":
            plan_payload.setdefault(
                "widget_blueprint_path",
                EditorOperationService._detect_widget_blueprint_path_from_request(request, goal, context_bundle) or "",
            )
            detected_widget_name = EditorOperationService._detect_widget_name_from_request(request, goal)
            detected_text = EditorOperationService._detect_umg_text_from_request(request, goal)
            detected_layout = EditorOperationService._detect_umg_layout_from_request(request, goal)
            detected_visibility = EditorOperationService._detect_umg_visibility_from_request(request, goal)
            if detected_widget_name:
                plan_payload.setdefault("widget_name", detected_widget_name)
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
            "context": {
                **safe_context,
                "active_context": active_context,
                "editor_context": editor_context,
            },
            "requested_by": "agent_chat_workflow_planner",
        }

    @staticmethod
    def workflow_templates() -> dict[str, Any]:
        return {
            "schema_version": "editor_workflow_templates_v1",
            "mode": "plan_only_confirmed_step_workflows",
            "auto_execute": False,
            "requires_user_confirmation_per_step": True,
            "template_count": 3,
            "templates": [
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
        if resolved_type == "umg_text_widget":
            return self._umg_text_widget(
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
        if "print string" in lower or ("beginplay" in lower and "compile" in lower):
            return "blueprint_print_then_compile"
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
        )
        graph_name = _first_non_empty(payload.get("graph_name"), "EventGraph")
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
            "entry_event": "BeginPlay",
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
            context.get("widget_blueprint_path"),
            context.get("current_widget_blueprint_path"),
        )
        widget_name = _first_non_empty(payload.get("widget_name"), payload.get("name"), "AgentText")
        widget_class = _first_non_empty(payload.get("widget_class"), "TextBlock")
        text = _first_non_empty(payload.get("text"), _quoted_text(goal))
        parent_widget_name = _first_non_empty(payload.get("parent_widget_name"), payload.get("parent"))
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
            "safety_notes": safety_notes
            or [
                "This is a plan only; it does not create proposals automatically.",
                "Each step must be submitted as a separate Proposal and confirmed by the user.",
                "UEAgentTool remains the only layer that executes Unreal Editor writes.",
            ],
            "steps": steps,
        }
