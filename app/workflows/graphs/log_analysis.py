from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.tools.log_analysis import analyze_ue_log
from app.tools.retrieval import retrieve_support_notes
from app.workflows.state import WorkflowState

LOG_RETRIEVAL_MIN_CONFIDENCE = 0.5
LOG_RETRIEVAL_MIN_TOP_SCORE = 0.45


def _top_retrieval_score(history: dict[str, Any]) -> float:
    scores: list[float] = []
    for item in history.get("retrieved_docs") or []:
        for key in ("final_score", "score", "lexical_score"):
            try:
                scores.append(float(item.get(key) or 0.0))
                break
            except (TypeError, ValueError):
                continue
    for item in history.get("citations") or []:
        try:
            scores.append(float(item.get("score") or 0.0))
        except (TypeError, ValueError):
            continue
    return max(scores or [0.0])


def _quality_gate_support(history: dict[str, Any]) -> dict[str, Any]:
    top_score = _top_retrieval_score(history)
    confidence = float(history.get("confidence") or 0.0)
    passed = bool(history.get("retrieved_docs")) and (
        confidence >= LOG_RETRIEVAL_MIN_CONFIDENCE or top_score >= LOG_RETRIEVAL_MIN_TOP_SCORE
    )
    quality_gate = {
        "status": "passed" if passed else "skipped",
        "reason": "high_confidence_match" if passed else "below_log_retrieval_threshold",
        "confidence": round(confidence, 4),
        "top_score": round(top_score, 4),
        "min_confidence": LOG_RETRIEVAL_MIN_CONFIDENCE,
        "min_top_score": LOG_RETRIEVAL_MIN_TOP_SCORE,
        "candidate_count": len(history.get("retrieved_docs") or []),
    }
    gated = dict(history)
    retrieval_trace = dict(history.get("retrieval_trace") or {})
    retrieval_trace["quality_gate"] = quality_gate
    gated["retrieval_trace"] = retrieval_trace
    gated["quality_gate"] = quality_gate
    if passed:
        return gated

    gated["answer"] = ""
    gated["sources"] = []
    gated["citations"] = []
    gated["retrieved_docs"] = []
    warnings = list(gated.get("warnings") or [])
    if "log_retrieval_below_threshold" not in warnings:
        warnings.append("log_retrieval_below_threshold")
    gated["warnings"] = warnings
    return gated


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

    log_result = analyze_ue_log(
        payload,
        project_root=request.context.project_root,
        context_current_file=request.context.current_file,
    )
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
    raw_history = retrieve_support_notes(
        kb_service,
        query=str(retrieval_query),
        context=request.context,
        output_language=output_language,
        domain_filters=["incident_history", "engine_notes", "project_docs"],
    )
    history = _quality_gate_support(raw_history)
    state.retrieved_context = history
    state.step_results.append(
        {
            "step_id": "retrieve_incident_history",
            "title": "Retrieve Incident History",
            "status": "completed",
            "summary": (
                f"Accepted {len(history['retrieved_docs'])} historical reference chunk(s)."
                if history["quality_gate"]["status"] == "passed"
                else "Skipped weak incident-history matches below the log retrieval threshold."
            ),
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
            "retrieval_quality_gate": history["quality_gate"],
        },
        "step_results": state.step_results,
        "retrieval_trace": history["retrieval_trace"],
        "tools": [
            {"tool_id": "analyze_ue_log", "status": "completed", "summary": log_result["summary"]},
            {
                "tool_id": "lookup_incident_history",
                "status": "completed" if history["quality_gate"]["status"] == "passed" else "skipped",
                "summary": (
                    f"Accepted {len(history['retrieved_docs'])} historical support chunk(s)."
                    if history["quality_gate"]["status"] == "passed"
                    else "Retrieved candidates were below the log support threshold."
                ),
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
