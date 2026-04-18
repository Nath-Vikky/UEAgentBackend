from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.tools.code_review import review_ue_cpp_files
from app.tools.retrieval import retrieve_support_notes
from app.workflows.state import WorkflowState


def run_code_review_workflow(
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
        task_type="code_review",
        raw_input=payload,
        normalized_input=request.model_dump(mode="json"),
    )

    review_result = review_ue_cpp_files(payload, request.context)
    state.tool_outputs["review_ue_cpp_files"] = review_result
    state.step_results.append(
        {
            "step_id": "collect_preprocess",
            "title": "Collect & Preprocess",
            "status": "completed",
            "summary": "Collected code input, extracted symbols, includes, and diff statistics.",
            "details": review_result["preprocess_summary"],
        }
    )
    state.step_results.append(
        {
            "step_id": "rule_scan",
            "title": "Rule Scan",
            "status": "completed",
            "summary": f"Detected {len(review_result['issue_list'])} rule-based findings.",
            "details": {
                "rule_hits": review_result["rule_hits"],
                "severity_summary": review_result["severity_summary"],
            },
        }
    )

    retrieval_query = payload.get("review_focus") or payload.get("user_query") or request.context.current_file or "UE coding review guidance"
    guidance = retrieve_support_notes(
        kb_service,
        query=str(retrieval_query),
        context=request.context,
        output_language=output_language,
        domain_filters=["team_rules", "engine_notes", "project_docs", "examples"],
        extra_payload={"doc_type": "reference"},
    )
    state.retrieved_context = guidance
    state.step_results.append(
        {
            "step_id": "retrieve_guidelines",
            "title": "Retrieve Guidelines",
            "status": "completed",
            "summary": f"Retrieved {len(guidance['retrieved_docs'])} supporting document chunks.",
            "details": guidance["retrieval_trace"],
        }
    )

    state.step_results.append(
        {
            "step_id": "aggregate_review",
            "title": "Aggregate Review",
            "status": "completed",
            "summary": "Aggregated rule hits, supporting guidance, and follow-up suggestions.",
            "details": {
                "need_human_followup": review_result["need_human_followup"],
                "guidance_sources": guidance["sources"],
            },
        }
    )

    return {
        "result": {
            **review_result,
            "supporting_guidance": guidance["answer"],
            "retrieved_references": guidance["citations"],
        },
        "step_results": state.step_results,
        "retrieval_trace": guidance["retrieval_trace"],
        "tools": [
            {"tool_id": "review_ue_cpp_files", "status": "completed", "summary": review_result["summary"]},
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {len(guidance['retrieved_docs'])} guideline chunks.",
            },
        ],
        "warnings": guidance["warnings"],
        "artifacts": [
            {
                "artifact_type": "review_report",
                "label": "Code Review Report",
                "filename": "code_review_report.json",
                "content": {
                    "review_result": review_result,
                    "guidance": guidance,
                },
            }
        ],
        "action_proposals": [],
    }
