from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.tools.perf_analyze import analyze_memory_perf_signals
from app.tools.retrieval import retrieve_support_notes
from app.workflows.state import WorkflowState


def run_perf_analyze_workflow(
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
        task_type="perf_analyze",
        raw_input=payload,
        normalized_input=request.model_dump(mode="json"),
    )

    perf_result = analyze_memory_perf_signals(payload)
    state.tool_outputs["analyze_memory_perf_signals"] = perf_result
    state.step_results.append(
        {
            "step_id": "parse_metrics",
            "title": "Parse Metrics",
            "status": "completed",
            "summary": "Parsed frame, thread, draw-call, and memory evidence from the input.",
            "details": perf_result["parser_diagnostics"],
        }
    )
    state.step_results.append(
        {
            "step_id": "detect_hotspots",
            "title": "Detect Hotspots",
            "status": "completed",
            "summary": f"Detected {len(perf_result['suspicious_points'])} suspicious metric hotspot(s).",
            "details": {
                "suspicious_points": perf_result["suspicious_points"],
                "metric_summary": perf_result["metric_summary"],
            },
        }
    )

    retrieval_query = payload.get("user_query") or payload.get("insights_summary") or "UE performance notes"
    notes = retrieve_support_notes(
        kb_service,
        query=str(retrieval_query),
        context=request.context,
        output_language=output_language,
        domain_filters=["perf_notes", "engine_notes", "project_docs"],
    )
    state.retrieved_context = notes
    state.step_results.append(
        {
            "step_id": "retrieve_perf_notes",
            "title": "Retrieve Perf Notes",
            "status": "completed",
            "summary": f"Retrieved {len(notes['retrieved_docs'])} performance reference chunk(s).",
            "details": notes["retrieval_trace"],
        }
    )
    state.step_results.append(
        {
            "step_id": "summarize_next_steps",
            "title": "Summarize Next Steps",
            "status": "completed",
            "summary": "Combined parsed hotspots with supporting optimization references.",
            "details": {
                "reference_count": len(notes["citations"]),
                "suggestion_count": len(perf_result["optimization_suggestions"]),
            },
        }
    )

    return {
        "result": {
            **perf_result,
            "retrieved_references": notes["citations"],
            "supporting_notes": notes["answer"],
        },
        "step_results": state.step_results,
        "retrieval_trace": notes["retrieval_trace"],
        "tools": [
            {
                "tool_id": "analyze_memory_perf_signals",
                "status": "completed",
                "summary": perf_result["summary"],
            },
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {len(notes['retrieved_docs'])} performance reference chunk(s).",
            },
        ],
        "warnings": notes["warnings"],
        "artifacts": [
            {
                "artifact_type": "perf_analysis_report",
                "label": "Performance Analysis Report",
                "filename": "perf_analysis_report.json",
                "content": {
                    "analysis": perf_result,
                    "supporting_notes": notes,
                },
            }
        ],
        "action_proposals": [],
    }
