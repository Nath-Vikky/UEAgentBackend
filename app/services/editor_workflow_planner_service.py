from __future__ import annotations

import re
import uuid
from typing import Any

from app.services.editor_operation_service import OPERATION_SPECS

WORKFLOW_PLAN_SCHEMA_VERSION = "editor_workflow_plan_v1"


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
                    "description": "Add a BeginPlay Print String template, then compile the Blueprint as a second Proposal step.",
                    "required_payload_fields": ["blueprint_path"],
                    "optional_payload_fields": ["graph_name", "message"],
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
        steps = [
            self._step(
                index=0,
                operation_type="add_blueprint_node_template",
                title="Add BeginPlay Print String node",
                payload={
                    "blueprint_path": blueprint_path,
                    "graph_name": graph_name,
                    "template_id": "print_string",
                    "entry_event": "BeginPlay",
                    "message": message,
                    "compile_after_edit": False,
                },
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
