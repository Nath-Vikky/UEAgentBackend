from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.proposal import ProposalModel
from app.services.editor_operations.catalog import EDITOR_OPERATION_PROPOSAL_TYPE
from app.services.editor_operations.followups import operation_follow_up_payload

WORKFLOW_BLOCKING_DIAGNOSTIC_FLAGS = {
    "blueprint_target_unresolved",
    "blueprint_graph_unresolved",
    "entry_event_unresolved",
    "pin_resolution_failed",
    "expected_linked_pins_missing",
    "compile_failed",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


class EditorWorkflowStateService:
    """Projects workflow progress from a plan plus stored editor-operation Proposals."""

    def __init__(self, db: Session):
        self.db = db

    def project_state(
        self,
        *,
        workflow_plan: dict[str, Any] | None = None,
        workflow_plan_id: str | None = None,
        completed_step_ids: list[str] | None = None,
        history_limit: int = 500,
    ) -> dict[str, Any]:
        safe_plan = _as_dict(workflow_plan)
        plan_id = _clean_text(workflow_plan_id or safe_plan.get("plan_id"))
        steps = [dict(item) for item in safe_plan.get("steps") or [] if isinstance(item, dict)]
        records_by_step_id = self._workflow_step_records(plan_id=plan_id, history_limit=history_limit) if plan_id else {}

        completed_ids = set(_as_string_list(completed_step_ids))
        for step_id, record in records_by_step_id.items():
            if bool(record.get("repair_resolved")):
                completed_ids.add(step_id)
            elif (
                record.get("execution_state") == "completed"
                and record.get("success") is True
                and not bool(record.get("blocks_workflow_dependency"))
            ):
                completed_ids.add(step_id)
            elif bool(record.get("blocks_workflow_dependency")):
                completed_ids.discard(step_id)

        step_states = [
            self._step_state(
                step=step,
                record=records_by_step_id.get(_clean_text(step.get("step_id"))),
                completed_step_ids=completed_ids,
            )
            for step in steps
        ]
        status_counts = Counter(str(item.get("status") or "unknown") for item in step_states)
        next_ready_step_ids = [item["step_id"] for item in step_states if item.get("status") == "ready_for_proposal"]
        completed_step_ids_sorted = sorted(completed_ids)
        next_step_proposal_requests = self._next_step_proposal_requests(
            plan_id=plan_id,
            steps=steps,
            next_ready_step_ids=next_ready_step_ids,
            completed_step_ids=completed_step_ids_sorted,
        )
        follow_up_proposal_requests = self._follow_up_proposal_requests(step_states)
        status = self._overall_status(step_states)
        next_action = self._next_action(step_states, follow_up_proposal_requests=follow_up_proposal_requests)
        quick_actions = self._quick_actions(
            next_step_proposal_requests=next_step_proposal_requests,
            follow_up_proposal_requests=follow_up_proposal_requests,
        )
        user_view = self._user_view(
            workflow_type=_clean_text(safe_plan.get("workflow_type")),
            status=status,
            next_action=next_action,
            step_states=step_states,
            quick_actions=quick_actions,
        )
        return {
            "schema_version": "editor_workflow_state_v1",
            "workflow_plan_id": plan_id,
            "workflow_type": _clean_text(safe_plan.get("workflow_type")),
            "status": status,
            "step_count": len(step_states),
            "completed_step_ids": completed_step_ids_sorted,
            "next_ready_step_ids": next_ready_step_ids,
            "pending_step_ids": [
                item["step_id"]
                for item in step_states
                if item.get("status") in {"pending_confirmation", "waiting_execution_result"}
            ],
            "blocked_step_ids": [
                item["step_id"]
                for item in step_states
                if item.get("status")
                in {"waiting_dependency", "needs_more_input", "completed_needs_attention", "failed", "blocked", "cancelled"}
            ],
            "status_counts": dict(status_counts),
            "step_states": step_states,
            "materialized_step_records": list(records_by_step_id.values()),
            "next_step_proposal_requests": next_step_proposal_requests,
            "follow_up_candidate_count": sum(
                int(_as_dict(item.get("proposal_record")).get("follow_up", {}).get("candidate_count") or 0)
                for item in step_states
                if str(item.get("status") or "") in {"completed_needs_attention", "failed", "blocked"}
            ),
            "ready_follow_up_candidate_count": len(follow_up_proposal_requests),
            "follow_up_proposal_requests": follow_up_proposal_requests,
            "next_action": next_action,
            "quick_actions": quick_actions,
            "user_view": user_view,
            "auto_execute": False,
            "requires_user_confirmation_per_step": True,
        }

    def _workflow_step_records(self, *, plan_id: str, history_limit: int) -> dict[str, dict[str, Any]]:
        safe_limit = max(1, min(int(history_limit or 500), 1000))
        statement = (
            select(ProposalModel)
            .where(ProposalModel.proposal_type == EDITOR_OPERATION_PROPOSAL_TYPE)
            .order_by(ProposalModel.updated_at.desc())
            .limit(safe_limit)
        )
        proposals = list(self.db.scalars(statement))
        repair_records_by_source_proposal_id = self._follow_up_repair_records_by_source(proposals)
        records: dict[str, dict[str, Any]] = {}
        for proposal in proposals:
            preview = _as_dict(proposal.dry_run_preview_json)
            context = _as_dict(preview.get("context"))
            if _clean_text(_as_dict(context.get("follow_up_materialization")).get("source_proposal_id")):
                continue
            workflow_context = _as_dict(context.get("workflow_materialization"))
            if _clean_text(workflow_context.get("workflow_plan_id")) != plan_id:
                continue
            step_id = _clean_text(workflow_context.get("workflow_step_id"))
            if not step_id or step_id in records:
                continue
            operation_result = _as_dict(preview.get("operation_result"))
            result_summary = _as_dict(operation_result.get("result_summary"))
            operation_diagnostics = _as_dict(result_summary.get("operation_diagnostics"))
            diagnostic_flags = _as_string_list(operation_diagnostics.get("diagnostic_flags"))
            blocking_flags = [flag for flag in diagnostic_flags if flag in WORKFLOW_BLOCKING_DIAGNOSTIC_FLAGS]
            repair_records = repair_records_by_source_proposal_id.get(proposal.proposal_id, [])
            successful_repairs = [item for item in repair_records if item.get("repair_success") is True]
            repair_resolved = bool(successful_repairs)
            unresolved_blocking_flags = [] if repair_resolved else blocking_flags
            follow_up = (
                operation_follow_up_payload(
                    proposal_id=proposal.proposal_id,
                    preview=preview,
                    is_editor_operation=True,
                ).get("follow_up", {})
                if operation_result
                else {}
            )
            records[step_id] = {
                "step_id": step_id,
                "proposal_id": proposal.proposal_id,
                "operation_type": _clean_text(preview.get("operation_type")),
                "tool_id": preview.get("tool_id"),
                "confirmation_state": proposal.confirmation_state,
                "approval_state": preview.get("approval_state"),
                "execution_state": operation_result.get("execution_state"),
                "success": operation_result.get("success"),
                "updated_at": _isoformat(proposal.updated_at),
                "operation_result_available": bool(operation_result),
                "diagnostic_flags": diagnostic_flags,
                "workflow_blocking_flags": blocking_flags,
                "unresolved_workflow_blocking_flags": unresolved_blocking_flags,
                "blocks_workflow_dependency": bool(unresolved_blocking_flags),
                "repair_resolved": repair_resolved,
                "repair_records": successful_repairs[:5],
                "follow_up": follow_up,
                "workflow_materialization": workflow_context,
            }
        return records

    def _follow_up_repair_records_by_source(
        self,
        proposals: list[ProposalModel],
    ) -> dict[str, list[dict[str, Any]]]:
        records: dict[str, list[dict[str, Any]]] = {}
        for proposal in proposals:
            preview = _as_dict(proposal.dry_run_preview_json)
            context = _as_dict(preview.get("context"))
            materialization = _as_dict(context.get("follow_up_materialization"))
            source_proposal_id = _clean_text(materialization.get("source_proposal_id"))
            if not source_proposal_id:
                continue
            operation_result = _as_dict(preview.get("operation_result"))
            result_summary = _as_dict(operation_result.get("result_summary"))
            operation_diagnostics = _as_dict(result_summary.get("operation_diagnostics"))
            diagnostic_flags = _as_string_list(operation_diagnostics.get("diagnostic_flags"))
            blocking_flags = [flag for flag in diagnostic_flags if flag in WORKFLOW_BLOCKING_DIAGNOSTIC_FLAGS]
            execution_state = _clean_text(operation_result.get("execution_state"))
            repair_success = execution_state == "completed" and operation_result.get("success") is True and not blocking_flags
            records.setdefault(source_proposal_id, []).append(
                {
                    "proposal_id": proposal.proposal_id,
                    "source_proposal_id": source_proposal_id,
                    "candidate_id": _clean_text(materialization.get("candidate_id")),
                    "operation_type": _clean_text(preview.get("operation_type")),
                    "tool_id": preview.get("tool_id"),
                    "execution_state": execution_state,
                    "success": operation_result.get("success"),
                    "repair_success": repair_success,
                    "diagnostic_flags": diagnostic_flags,
                    "workflow_blocking_flags": blocking_flags,
                    "updated_at": _isoformat(proposal.updated_at),
                }
            )
        return records

    @staticmethod
    def _step_state(
        *,
        step: dict[str, Any],
        record: dict[str, Any] | None,
        completed_step_ids: set[str],
    ) -> dict[str, Any]:
        step_id = _clean_text(step.get("step_id"))
        depends_on_step_ids = _as_string_list(step.get("depends_on_step_ids"))
        missing_inputs = list(step.get("missing_inputs") or [])
        unmet_dependencies = [item for item in depends_on_step_ids if item not in completed_step_ids]
        proposal_ready = bool(step.get("proposal_ready")) and not missing_inputs
        status = "ready_for_proposal"
        if record:
            execution_state = _clean_text(record.get("execution_state"))
            success = record.get("success")
            confirmation_state = _clean_text(record.get("confirmation_state"))
            if bool(record.get("repair_resolved")):
                status = "completed_after_repair"
            elif execution_state == "completed" and success is True and bool(record.get("blocks_workflow_dependency")):
                status = "completed_needs_attention"
            elif execution_state == "completed" and success is True:
                status = "completed"
            elif execution_state in {"failed", "blocked", "cancelled"}:
                status = execution_state
            elif record.get("operation_result_available"):
                status = "completed_needs_attention" if success is True and bool(record.get("blocks_workflow_dependency")) else (
                    "completed" if success is True else "failed"
                )
            elif confirmation_state == "confirmed":
                status = "waiting_execution_result"
            elif confirmation_state == "pending":
                status = "pending_confirmation"
            else:
                status = "materialized"
        elif missing_inputs or not proposal_ready:
            status = "needs_more_input"
        elif unmet_dependencies:
            status = "waiting_dependency"

        return {
            "step_id": step_id,
            "step_index": step.get("step_index"),
            "title": step.get("title"),
            "operation_type": step.get("operation_type"),
            "proposal_ready": bool(step.get("proposal_ready")),
            "depends_on_step_ids": depends_on_step_ids,
            "missing_inputs": missing_inputs,
            "unmet_dependency_step_ids": unmet_dependencies,
            "status": status,
            "can_create_proposal": status == "ready_for_proposal",
            "completed": status in {"completed", "completed_after_repair"},
            "needs_attention": status in {"completed_needs_attention", "failed", "blocked", "cancelled"},
            "diagnostic_flags": _as_string_list(record.get("diagnostic_flags") if record else []),
            "workflow_blocking_flags": _as_string_list(record.get("workflow_blocking_flags") if record else []),
            "unresolved_workflow_blocking_flags": _as_string_list(
                record.get("unresolved_workflow_blocking_flags") if record else []
            ),
            "repair_resolved": bool(record.get("repair_resolved")) if record else False,
            "repair_records": list(record.get("repair_records") or []) if record else [],
            "proposal_record": record or {},
        }

    @staticmethod
    def _overall_status(step_states: list[dict[str, Any]]) -> str:
        if not step_states:
            return "empty_plan"
        statuses = {str(item.get("status") or "") for item in step_states}
        if statuses <= {"completed", "completed_after_repair"}:
            return "completed"
        if statuses & {"completed_needs_attention", "failed", "blocked", "cancelled"}:
            return "needs_attention"
        if "ready_for_proposal" in statuses:
            return "ready_for_next_step"
        if statuses & {"pending_confirmation", "waiting_execution_result"}:
            return "waiting_for_execution"
        if "waiting_dependency" in statuses:
            return "waiting_dependency"
        return "needs_more_input"

    @staticmethod
    def _next_action(
        step_states: list[dict[str, Any]],
        *,
        follow_up_proposal_requests: list[dict[str, Any]] | None = None,
    ) -> str:
        if follow_up_proposal_requests:
            return "create_follow_up_repair_proposal"
        statuses = [str(item.get("status") or "") for item in step_states]
        if "ready_for_proposal" in statuses:
            return "create_next_ready_proposal"
        if "pending_confirmation" in statuses:
            return "confirm_or_reject_pending_proposal"
        if "waiting_execution_result" in statuses:
            return "wait_for_ue_plugin_result"
        if any(status in {"completed_needs_attention", "failed", "blocked", "cancelled"} for status in statuses):
            return "inspect_failure_or_follow_up"
        if "waiting_dependency" in statuses:
            return "complete_prerequisite_step"
        if "needs_more_input" in statuses:
            return "collect_missing_inputs"
        return "workflow_complete"

    @staticmethod
    def _next_step_proposal_requests(
        *,
        plan_id: str,
        steps: list[dict[str, Any]],
        next_ready_step_ids: list[str],
        completed_step_ids: list[str],
    ) -> list[dict[str, Any]]:
        next_ready = set(next_ready_step_ids)
        requests: list[dict[str, Any]] = []
        for step in steps:
            step_id = _clean_text(step.get("step_id"))
            if step_id not in next_ready:
                continue
            requests.append(
                {
                    "action_type": "create_workflow_step_proposal",
                    "workflow_step_id": step_id,
                    "operation_type": step.get("operation_type"),
                    "method": "POST",
                    "endpoint": "/api/v1/editor-operations/workflows/steps/proposal",
                    "request": {
                        "workflow_plan_id": plan_id,
                        "step": step,
                        "requested_by": "workflow_state_projection",
                        "context": {"completed_step_ids": completed_step_ids},
                    },
                    "safety": {
                        "auto_execute": False,
                        "creates_pending_proposal_only": True,
                        "requires_user_confirmation": True,
                    },
                }
            )
        return requests

    @staticmethod
    def _follow_up_proposal_requests(step_states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        requests: list[dict[str, Any]] = []
        for state in step_states:
            if str(state.get("status") or "") not in {"completed_needs_attention", "failed", "blocked"}:
                continue
            record = _as_dict(state.get("proposal_record"))
            proposal_id = _clean_text(record.get("proposal_id"))
            if not proposal_id:
                continue
            follow_up = _as_dict(record.get("follow_up"))
            for candidate in list(follow_up.get("candidates") or []):
                if not isinstance(candidate, dict):
                    continue
                if not bool(candidate.get("proposal_ready")) or candidate.get("missing_inputs"):
                    continue
                requests.append(
                    {
                        "action_type": "create_editor_operation_follow_up_proposal",
                        "workflow_step_id": state.get("step_id"),
                        "source_proposal_id": proposal_id,
                        "candidate_id": candidate.get("candidate_id"),
                        "operation_type": candidate.get("operation_type"),
                        "method": "POST",
                        "endpoint": f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal",
                        "request": {
                            "candidate": candidate,
                            "requested_by": "workflow_state_projection",
                            "context": {
                                "workflow_repair_context": {
                                    "schema_version": "editor_workflow_repair_context_v1",
                                    "workflow_plan_id": _clean_text(
                                        _as_dict(record.get("workflow_materialization")).get("workflow_plan_id")
                                    ),
                                    "workflow_step_id": state.get("step_id"),
                                    "source_proposal_id": proposal_id,
                                    "candidate_id": candidate.get("candidate_id"),
                                }
                            },
                        },
                        "safety": {
                            "auto_execute": False,
                            "creates_pending_proposal_only": True,
                            "requires_user_confirmation": True,
                        },
                    }
                )
        return requests[:5]

    @staticmethod
    def _quick_actions(
        *,
        next_step_proposal_requests: list[dict[str, Any]],
        follow_up_proposal_requests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for request in follow_up_proposal_requests:
            candidate_id = _clean_text(request.get("candidate_id")) or f"repair_{len(actions)}"
            operation_type = _clean_text(request.get("operation_type")) or "editor_operation"
            actions.append(
                {
                    "action_id": f"workflow_create_repair_proposal_{candidate_id}",
                    "label": f"Create Repair Proposal: {operation_type}",
                    "payload": request,
                }
            )
        if actions:
            return actions[:5]
        for request in next_step_proposal_requests:
            step_id = _clean_text(request.get("workflow_step_id")) or f"step_{len(actions)}"
            operation_type = _clean_text(request.get("operation_type")) or "editor_operation"
            actions.append(
                {
                    "action_id": f"workflow_create_step_proposal_{step_id}",
                    "label": f"Create Step Proposal: {operation_type}",
                    "payload": request,
                }
            )
        return actions[:5]

    @staticmethod
    def _user_view(
        *,
        workflow_type: str,
        status: str,
        next_action: str,
        step_states: list[dict[str, Any]],
        quick_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        completed_count = sum(1 for item in step_states if bool(item.get("completed")))
        attention_steps = [item for item in step_states if bool(item.get("needs_attention"))]
        ready_steps = [item for item in step_states if item.get("status") == "ready_for_proposal"]
        pending_steps = [
            item
            for item in step_states
            if item.get("status") in {"pending_confirmation", "waiting_execution_result"}
        ]
        if status == "needs_attention" and quick_actions:
            text = "The workflow needs a repair Proposal before it can continue."
        elif status == "ready_for_next_step" and ready_steps:
            text = "The workflow is ready for the next confirmed Proposal step."
        elif status == "waiting_for_execution":
            text = "The workflow is waiting for user confirmation or a UE execution result."
        elif status == "completed":
            text = "The workflow is complete."
        elif status == "empty_plan":
            text = "No workflow steps are available."
        else:
            text = "The workflow is not ready to continue yet."

        blocks: list[dict[str, Any]] = [
            {
                "block_type": "editor_workflow_state_summary",
                "title": "Workflow State",
                "text": text,
                "data": {
                    "workflow_type": workflow_type,
                    "status": status,
                    "next_action": next_action,
                    "step_count": len(step_states),
                    "completed_count": completed_count,
                    "attention_count": len(attention_steps),
                    "ready_count": len(ready_steps),
                    "pending_count": len(pending_steps),
                    "quick_action_count": len(quick_actions),
                },
            }
        ]
        if attention_steps:
            blocks.append(
                {
                    "block_type": "editor_workflow_attention_steps",
                    "title": "Steps Needing Attention",
                    "items": [
                        {
                            "step_id": item.get("step_id"),
                            "title": item.get("title"),
                            "status": item.get("status"),
                            "operation_type": item.get("operation_type"),
                            "workflow_blocking_flags": item.get("workflow_blocking_flags") or [],
                            "unresolved_workflow_blocking_flags": item.get("unresolved_workflow_blocking_flags") or [],
                        }
                        for item in attention_steps[:5]
                    ],
                }
            )
        if ready_steps:
            blocks.append(
                {
                    "block_type": "editor_workflow_ready_steps",
                    "title": "Ready Steps",
                    "items": [
                        {
                            "step_id": item.get("step_id"),
                            "title": item.get("title"),
                            "operation_type": item.get("operation_type"),
                            "status": item.get("status"),
                        }
                        for item in ready_steps[:5]
                    ],
                }
            )
        if quick_actions:
            blocks.append(
                {
                    "block_type": "workflow_ready_actions",
                    "title": "Available Actions",
                    "items": [
                        {
                            "action_id": item.get("action_id"),
                            "label": item.get("label"),
                            "action_type": _as_dict(item.get("payload")).get("action_type"),
                        }
                        for item in quick_actions[:5]
                    ],
                }
            )

        return {
            "schema_version": "editor_workflow_state_user_view_v1",
            "title": "Editor Workflow State",
            "text": text,
            "status_hint": status,
            "blocks": blocks,
            "quick_actions": quick_actions,
        }


__all__ = ["EditorWorkflowStateService"]
