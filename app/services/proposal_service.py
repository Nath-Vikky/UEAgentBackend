from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.models.audit import AuditLogModel
from app.db.models.proposal import ProposalDecisionModel, ProposalModel
from app.db.models.task import TaskArtifactModel, TaskEventModel, TaskModel
from app.db.repositories.audit_logs import create_audit_log
from app.db.repositories.proposals import (
    create_proposal_decision,
    get_proposal,
    get_proposal_decision,
    list_pending_proposals,
    list_proposal_decisions,
    save_proposal,
)
from app.db.repositories.tasks import add_task_artifact, add_task_event, get_task, save_task
from app.i18n.language import DEFAULT_OUTPUT_LANGUAGE
from app.observability.audit import build_audit_entry
from app.schemas.requests import ProposalDecisionRequest
from app.services.code_write_service import execute_code_write_plan
from app.utils.json_tools import dumps_pretty
from app.utils.paths import task_artifact_dir
from app.utils.time import now_utc


class ProposalService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings

    def _language_of_task(self, task: TaskModel) -> str:
        return str((task.locale_json or {}).get("final_output_language") or DEFAULT_OUTPUT_LANGUAGE)

    def _localized(self, task: TaskModel, zh_text: str, en_text: str) -> str:
        return zh_text if self._language_of_task(task).startswith("zh") else en_text

    def _write_snapshot(self, task: TaskModel, response_payload: dict) -> None:
        if not task.snapshot_path:
            return
        Path(task.snapshot_path).write_text(dumps_pretty(response_payload), encoding="utf-8")

    def _persist_response_payload(self, task: TaskModel, response_payload: dict) -> None:
        task.raw_response_json = response_payload
        task.user_view_json = dict(response_payload.get("user_view") or {})
        task.debug_view_json = dict(response_payload.get("debug_view") or {})
        task.presentation_json = dict(response_payload.get("presentation") or {})
        task.data_json = dict(response_payload.get("data") or {})
        task.trace_summary_json = dict(response_payload.get("trace_summary") or {})
        task.step_results_json = list(response_payload.get("step_results") or [])
        task.assistant_message = str(response_payload.get("assistant_message") or "")
        self._write_snapshot(task, response_payload)

    def _materialize_approved_config_artifact(
        self,
        *,
        task: TaskModel,
        proposal: ProposalModel,
    ) -> dict | None:
        if not self.settings:
            return None
        draft_config = (
            dict(proposal.dry_run_preview_json or {}).get("draft_config")
            or dict(task.data_json or {}).get("draft_config")
        )
        if not draft_config:
            return None

        artifact_id = f"artifact_{uuid.uuid4().hex}"
        path = task_artifact_dir(self.settings, task.task_id) / "approved_config.json"
        path.write_text(dumps_pretty(draft_config), encoding="utf-8")
        descriptor = {
            "artifact_id": artifact_id,
            "artifact_type": "approved_config",
            "label": "Approved Config Export",
            "path": str(path),
            "metadata": {
                "proposal_id": proposal.proposal_id,
                "proposal_type": proposal.proposal_type,
                "generated_from": "proposal_confirmation",
            },
        }
        add_task_artifact(
            self.db,
            TaskArtifactModel(
                artifact_id=artifact_id,
                task_id=task.task_id,
                artifact_type=descriptor["artifact_type"],
                label=descriptor["label"],
                path=descriptor["path"],
                metadata_json=descriptor["metadata"],
            ),
        )
        return descriptor

    def _materialize_code_write_report(
        self,
        *,
        task: TaskModel,
        proposal: ProposalModel,
        code_write_result: dict,
    ) -> dict | None:
        if not self.settings:
            return None
        artifact_id = f"artifact_{uuid.uuid4().hex}"
        path = task_artifact_dir(self.settings, task.task_id) / "code_write_report.json"
        path.write_text(dumps_pretty(code_write_result), encoding="utf-8")
        descriptor = {
            "artifact_id": artifact_id,
            "artifact_type": "code_write_report",
            "label": "Code Write Report",
            "path": str(path),
            "metadata": {
                "proposal_id": proposal.proposal_id,
                "proposal_type": proposal.proposal_type,
                "execution_state": code_write_result.get("execution_state"),
                "written_to_disk": code_write_result.get("written_to_disk", False),
            },
        }
        add_task_artifact(
            self.db,
            TaskArtifactModel(
                artifact_id=artifact_id,
                task_id=task.task_id,
                artifact_type=descriptor["artifact_type"],
                label=descriptor["label"],
                path=descriptor["path"],
                metadata_json=descriptor["metadata"],
            ),
        )
        return descriptor

    @staticmethod
    def _mark_written_generated_items(data: dict, code_write_result: dict) -> None:
        written_by_relative_path = {
            str(item.get("relative_path") or ""): item
            for item in code_write_result.get("written_files") or []
        }
        updated_items: list[dict] = []
        for item in data.get("generated_items") or []:
            current = dict(item)
            written = written_by_relative_path.get(str(current.get("file_path") or ""))
            if written:
                current["write_status"] = "written"
                current["is_virtual"] = False
                current["written_path"] = written.get("target_path")
            updated_items.append(current)
        if updated_items:
            data["generated_items"] = updated_items
            data["write_policy"] = {
                **dict(data.get("write_policy") or {}),
                "written_to_disk": bool(code_write_result.get("written_to_disk")),
                "execution_state": code_write_result.get("execution_state"),
            }

    @staticmethod
    def _refresh_generated_items_blocks(user_view: dict, data: dict) -> None:
        generated_items = list(data.get("generated_items") or [])
        if not generated_items:
            return
        refreshed_blocks: list[dict] = []
        for block in user_view.get("blocks") or []:
            current = dict(block)
            if current.get("block_type") == "generated_items":
                current["text"] = "\n".join(
                    f"{item.get('file_path')} ({item.get('write_status', 'not_written')})"
                    for item in generated_items
                )
                current["data"] = {
                    **dict(current.get("data") or {}),
                    "generated_items": generated_items,
                }
            refreshed_blocks.append(current)
        user_view["blocks"] = refreshed_blocks

    def _apply_follow_up(
        self,
        *,
        task: TaskModel,
        proposal: ProposalModel,
        decision: str,
        response_payload: dict,
    ) -> dict | None:
        data = dict(response_payload.get("data") or {})
        user_view = dict(response_payload.get("user_view") or {})
        debug_view = dict(response_payload.get("debug_view") or {})
        step_results = list(response_payload.get("step_results") or [])
        artifacts = list(debug_view.get("artifacts") or [])

        if decision == "confirmed":
            artifact_descriptor = None
            execution_state = "recorded"
            if proposal.proposal_type == "config_apply":
                artifact_descriptor = self._materialize_approved_config_artifact(task=task, proposal=proposal)
                if artifact_descriptor:
                    execution_state = "materialized"
                    artifacts.append(artifact_descriptor)
                    data["approved_config"] = (
                        dict(proposal.dry_run_preview_json or {}).get("draft_config")
                        or dict(task.data_json or {}).get("draft_config")
                    )
            elif proposal.proposal_type == "write_code_files":
                write_plan = (
                    dict(proposal.dry_run_preview_json or {}).get("write_plan")
                    or dict(task.data_json or {}).get("write_plan")
                    or {}
                )
                code_write_result = execute_code_write_plan(dict(write_plan))
                execution_state = str(code_write_result.get("execution_state") or "blocked")
                data["code_write_result"] = code_write_result
                self._mark_written_generated_items(data, code_write_result)
                self._refresh_generated_items_blocks(user_view, data)
                artifact_descriptor = self._materialize_code_write_report(
                    task=task,
                    proposal=proposal,
                    code_write_result=code_write_result,
                )
                if artifact_descriptor:
                    artifacts.append(artifact_descriptor)

            data["approval_result"] = {
                "decision": "confirmed",
                "proposal_id": proposal.proposal_id,
                "proposal_type": proposal.proposal_type,
                "execution_state": execution_state,
                "artifact": artifact_descriptor,
            }
            if proposal.proposal_type == "write_code_files" and execution_state != "files_written":
                user_view["text"] = self._localized(
                    task,
                    "Proposal 已确认，但写入被安全校验阻止，未修改工程文件。请查看审批结果和 Code Write Report。",
                    "The proposal was confirmed, but the write was blocked by safety validation and no project files were changed. Check the approval result and Code Write Report.",
                )
                user_view["status_hint"] = "blocked"
            elif proposal.proposal_type == "write_code_files":
                user_view["text"] = self._localized(
                    task,
                    "Proposal 已确认，生成的代码文件已写入项目目录。请在 UE 中重新生成/编译并按验证清单检查。",
                    "The proposal was confirmed and generated code files were written into the project directory. Regenerate/compile in UE and follow the validation checklist.",
                )
                user_view["status_hint"] = "approved"
            else:
                user_view["text"] = self._localized(
                    task,
                    "Proposal 已确认，后续产物已经生成，可继续在 Artifact 面板查看。",
                    "The proposal was confirmed and the downstream artifact has been materialized. Check the Artifacts panel for the generated output.",
                )
                user_view["status_hint"] = "approved"
            user_view["quick_actions"] = list(user_view.get("quick_actions") or []) + [
                {
                    "action_id": "open_artifacts",
                    "label": self._localized(task, "查看产物", "Open artifacts"),
                    "payload": {"task_id": task.task_id},
                }
            ]
            user_view["blocks"] = list(user_view.get("blocks") or []) + [
                {
                    "block_type": "summary",
                    "title": self._localized(task, "审批结果", "Approval Result"),
                    "text": self._localized(
                        task,
                        "当前变更已确认，后端已完成确认后的安全后续处理。",
                        "The change has been confirmed and the backend completed the approved safe follow-up.",
                    ),
                    "data": data["approval_result"],
                }
            ]
            step_results.append(
                {
                    "step_id": "proposal_execution",
                    "title": "Proposal Execution",
                    "status": "completed",
                    "summary": self._localized(
                        task,
                        "确认后的后续执行已完成。",
                        "The post-confirmation follow-up execution completed.",
                    ),
                    "details": data["approval_result"],
                }
            )
        else:
            data["approval_result"] = {
                "decision": "rejected",
                "proposal_id": proposal.proposal_id,
                "proposal_type": proposal.proposal_type,
                "execution_state": "cancelled",
                "artifact": None,
            }
            user_view["text"] = self._localized(
                task,
                "Proposal 已拒绝，本次变更不会继续落地。",
                "The proposal was rejected, so the requested change will not continue.",
            )
            user_view["status_hint"] = "rejected"
            user_view["blocks"] = list(user_view.get("blocks") or []) + [
                {
                    "block_type": "summary",
                    "title": self._localized(task, "审批结果", "Approval Result"),
                    "text": self._localized(
                        task,
                        "当前提案已被拒绝，任务以取消结束。",
                        "The proposal was rejected and the task closed as cancelled.",
                    ),
                    "data": data["approval_result"],
                }
            ]
            step_results.append(
                {
                    "step_id": "proposal_execution",
                    "title": "Proposal Execution",
                    "status": "cancelled",
                    "summary": self._localized(
                        task,
                        "确认环节被拒绝，后续执行已停止。",
                        "The proposal was rejected, so downstream execution stopped.",
                    ),
                    "details": data["approval_result"],
                }
            )

        debug_view["raw_result"] = data
        debug_view["step_results"] = step_results
        debug_view["artifacts"] = artifacts
        if data.get("code_write_result"):
            debug_view["side_effects"] = list(debug_view.get("side_effects") or []) + [
                {
                    "proposal_id": proposal.proposal_id,
                    "proposal_type": proposal.proposal_type,
                    "side_effect_level": "confirmed_write",
                    "execution_state": data["code_write_result"].get("execution_state"),
                    "written_to_disk": data["code_write_result"].get("written_to_disk", False),
                    "written_files": data["code_write_result"].get("written_files", []),
                    "blocked_files": data["code_write_result"].get("blocked_files", []),
                }
            ]
        response_payload["data"] = data
        response_payload["user_view"] = user_view
        response_payload["debug_view"] = debug_view
        response_payload["step_results"] = step_results
        response_payload["presentation"] = {
            "user_title": user_view.get("title") or "",
            "user_text": user_view.get("text") or "",
        }
        response_payload["assistant_message"] = user_view.get("text") or ""
        return data["approval_result"]

    def _proposal_payload(self, proposal: ProposalModel) -> dict:
        return {
            "proposal_id": proposal.proposal_id,
            "title": proposal.title,
            "proposal_type": proposal.proposal_type,
            "before_summary": proposal.before_summary,
            "after_summary": proposal.after_summary,
            "rationale": proposal.rationale,
            "risk_flags": proposal.risk_flags,
            "dry_run_preview": proposal.dry_run_preview_json,
            "display_hints": proposal.display_hints_json,
            "requires_confirmation": proposal.requires_confirmation,
            "confirmation": {
                "state": proposal.confirmation_state,
                "decision_endpoint": proposal.decision_endpoint,
            },
        }

    def _decision_payload(self, decision: ProposalDecisionModel) -> dict:
        return {
            "decision_id": decision.decision_id,
            "proposal_id": decision.proposal_id,
            "task_id": decision.task_id,
            "decision": decision.decision,
            "actor": decision.actor,
            "comment": decision.comment,
            "metadata": decision.metadata_json,
            "created_at": decision.created_at.isoformat(),
        }

    def pending(self) -> list[dict]:
        return [self._proposal_payload(proposal) for proposal in list_pending_proposals(self.db)]

    def get_detail(self, proposal_id: str) -> dict | None:
        proposal = get_proposal(self.db, proposal_id)
        if not proposal:
            return None
        task = get_task(self.db, proposal.task_id) if proposal.task_id else None
        decisions = [self._decision_payload(item) for item in list_proposal_decisions(self.db, proposal_id)]
        return {
            "item": self._proposal_payload(proposal),
            "task": {
                "task_id": task.task_id,
                "run_id": task.run_id,
                "status": task.status,
                "task_type": task.task_type,
                "finish_reason": task.finish_reason,
            }
            if task
            else {},
            "decisions": decisions,
        }

    def record_decision(self, proposal_id: str, request: ProposalDecisionRequest) -> dict | None:
        proposal = get_proposal(self.db, proposal_id)
        if not proposal:
            return None
        if proposal.confirmation_state != "pending":
            raise ValueError(f"Proposal `{proposal_id}` is already `{proposal.confirmation_state}`.")

        decision = create_proposal_decision(
            self.db,
            ProposalDecisionModel(
                decision_id=f"decision_{uuid.uuid4().hex}",
                proposal_id=proposal_id,
                task_id=proposal.task_id,
                decision=request.decision,
                actor=request.actor,
                comment=request.comment,
                metadata_json=request.metadata,
            ),
        )
        proposal.confirmation_state = request.decision
        save_proposal(self.db, proposal)

        task = get_task(self.db, proposal.task_id) if proposal.task_id else None
        if task:
            updated_proposals = []
            for item in task.action_proposals_json:
                if item.get("proposal_id") == proposal_id:
                    confirmation = dict(item.get("confirmation") or {})
                    confirmation["state"] = request.decision
                    item = {**item, "confirmation": confirmation}
                updated_proposals.append(item)

            task.action_proposals_json = updated_proposals
            task.status = "completed" if request.decision == "confirmed" else "cancelled"
            task.finish_reason = (
                "proposal_confirmed" if request.decision == "confirmed" else "proposal_rejected"
            )
            task.output_complete = True
            task.completed_at = now_utc()

            response_payload = dict(task.raw_response_json or {})
            task_payload = dict(response_payload.get("task") or {})
            task_payload["status"] = task.status
            task_payload["finish_reason"] = task.finish_reason
            task_payload["output_complete"] = True
            response_payload["task"] = task_payload
            response_payload["action_proposals"] = updated_proposals

            trace_summary = dict(response_payload.get("trace_summary") or {})
            trace_summary["final_status"] = task.status
            trace_summary["finish_reason"] = task.finish_reason
            response_payload["trace_summary"] = trace_summary

            debug_view = dict(response_payload.get("debug_view") or {})
            debug_view["output_complete"] = True
            debug_view["finish_reason"] = task.finish_reason
            response_payload["debug_view"] = debug_view

            approval_result = self._apply_follow_up(
                task=task,
                proposal=proposal,
                decision=request.decision,
                response_payload=response_payload,
            )
            self._persist_response_payload(task, response_payload)
            save_task(self.db, task)

            next_seq = len(task.events) + 1
            event_payload = {
                "event": "proposal_decision_recorded",
                "run_id": task.run_id,
                "task_id": task.task_id,
                "seq": next_seq,
                "timestamp": now_utc().isoformat(),
                "payload": self._decision_payload(decision),
            }
            add_task_event(
                self.db,
                TaskEventModel(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    task_id=task.task_id,
                    event_type="proposal_decision_recorded",
                    payload_json=event_payload,
                ),
            )
            if approval_result:
                followup_event = {
                    "event": "proposal_followup_completed",
                    "run_id": task.run_id,
                    "task_id": task.task_id,
                    "seq": next_seq + 1,
                    "timestamp": now_utc().isoformat(),
                    "payload": approval_result,
                }
                add_task_event(
                    self.db,
                    TaskEventModel(
                        event_id=f"evt_{uuid.uuid4().hex}",
                        task_id=task.task_id,
                        event_type="proposal_followup_completed",
                        payload_json=followup_event,
                    ),
                )
            audit_entry = build_audit_entry(
                "proposal_decision_recorded",
                {
                    "proposal_id": proposal_id,
                    "decision_id": decision.decision_id,
                    "decision": request.decision,
                    "actor": request.actor,
                },
                task_id=task.task_id,
                session_id=task.session_id,
            )
            if approval_result:
                followup_audit = build_audit_entry(
                    "proposal_followup_completed",
                    approval_result,
                    task_id=task.task_id,
                    session_id=task.session_id,
                )
                create_audit_log(
                    self.db,
                    AuditLogModel(
                        audit_id=f"audit_{uuid.uuid4().hex}",
                        task_id=task.task_id,
                        session_id=task.session_id,
                        event_type=followup_audit["event_type"],
                        payload_json=followup_audit["payload"],
                    ),
                )
        else:
            audit_entry = build_audit_entry(
                "proposal_decision_recorded",
                {
                    "proposal_id": proposal_id,
                    "decision_id": decision.decision_id,
                    "decision": request.decision,
                    "actor": request.actor,
                },
            )

        create_audit_log(
            self.db,
            AuditLogModel(
                audit_id=f"audit_{uuid.uuid4().hex}",
                task_id=proposal.task_id,
                session_id=task.session_id if task else None,
                event_type=audit_entry["event_type"],
                payload_json=audit_entry["payload"],
            ),
        )
        return {
            "item": self._decision_payload(decision),
            "proposal": self._proposal_payload(proposal),
        }

    def get_decision(self, decision_id: str) -> dict | None:
        decision = get_proposal_decision(self.db, decision_id)
        if not decision:
            return None
        proposal = get_proposal(self.db, decision.proposal_id)
        return {
            "item": self._decision_payload(decision),
            "proposal": self._proposal_payload(proposal) if proposal else None,
        }
