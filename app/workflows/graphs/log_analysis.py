from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.tools.log_analysis import analyze_ue_log
from app.tools.retrieval import retrieve_support_notes
from app.workflows.state import WorkflowState


def run_log_analysis_workflow(
    *,
    request: UnifiedTaskRequest,
    kb_service: KnowledgeBaseService,
    task_id: str,
    run_id: str,
    output_language: str,
) -> dict[str, Any]:
    payload = request.payload
    state = WorkflowState(
        run_id=run_id,
        task_id=task_id,
        session_id=request.session.session_id,
        task_type="logs_analyze",
        raw_input=payload,
        normalized_input=request.model_dump(mode="json"),
    )

    log_result = analyze_ue_log(payload)
    state.tool_outputs["analyze_ue_log"] = log_result
    state.step_results.append(
        {
            "step_id": "parse_log",
            "title": "Parse Log",
            "status": "completed",
            "summary": "Parsed the incoming log text into structured events and diagnostics.",
            "details": log_result["parser_diagnostics"],
        }
    )
    state.step_results.append(
        {
            "step_id": "cluster_signatures",
            "title": "Cluster Signatures",
            "status": "completed",
            "summary": f"Identified {len(log_result['issue_families']) or 1} issue family candidate(s).",
            "details": {
                "issue_families": log_result["issue_families"],
                "log_summary": log_result["log_summary"],
            },
        }
    )

    retrieval_query = "; ".join(log_result["issue_families"]) or payload.get("user_query") or "UE crash log incident history"
    history = retrieve_support_notes(
        kb_service,
        query=str(retrieval_query),
        context=request.context,
        output_language=output_language,
        domain_filters=["incident_history", "engine_notes", "project_docs"],
    )
    state.retrieved_context = history
    state.step_results.append(
        {
            "step_id": "retrieve_incident_history",
            "title": "Retrieve Incident History",
            "status": "completed",
            "summary": f"Retrieved {len(history['retrieved_docs'])} historical reference chunk(s).",
            "details": history["retrieval_trace"],
        }
    )
    state.step_results.append(
        {
            "step_id": "compose_root_cause_summary",
            "title": "Compose Root Cause Summary",
            "status": "completed",
            "summary": "Merged parser signals with incident history references.",
            "details": {
                "finding_count": len(log_result["findings"]),
                "reference_count": len(history["citations"]),
            },
        }
    )

    return {
        "result": {
            **log_result,
            "retrieved_references": history["citations"],
            "incident_history_summary": history["answer"],
        },
        "step_results": state.step_results,
        "retrieval_trace": history["retrieval_trace"],
        "tools": [
            {"tool_id": "analyze_ue_log", "status": "completed", "summary": log_result["summary"]},
            {
                "tool_id": "lookup_incident_history",
                "status": "completed",
                "summary": f"Retrieved {len(history['retrieved_docs'])} historical support chunk(s).",
            },
        ],
        "warnings": history["warnings"],
        "artifacts": [
            {
                "artifact_type": "log_analysis_report",
                "label": "Log Analysis Report",
                "filename": "log_analysis_report.json",
                "content": {
                    "analysis": log_result,
                    "incident_history": history,
                },
            }
        ],
        "action_proposals": [],
    }
