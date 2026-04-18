from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.tools.config_generate import generate_design_config
from app.tools.retrieval import retrieve_support_notes
from app.workflows.state import WorkflowState


def run_config_generate_workflow(
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
        task_type="config_generate",
        raw_input=payload,
        normalized_input=request.model_dump(mode="json"),
    )

    retrieval_query = payload.get("object_type") or payload.get("user_query") or "config schema and examples"
    support = retrieve_support_notes(
        kb_service,
        query=str(retrieval_query),
        context=request.context,
        output_language=output_language,
        domain_filters=["config_schema", "examples", "project_docs"],
    )
    state.retrieved_context = support
    state.step_results.append(
        {
            "step_id": "load_schema_examples",
            "title": "Load Schema & Examples",
            "status": "completed",
            "summary": f"Retrieved {len(support['retrieved_docs'])} schema/example chunk(s).",
            "details": support["retrieval_trace"],
        }
    )

    config_result = generate_design_config(payload)
    state.tool_outputs["generate_design_config"] = config_result
    state.step_results.append(
        {
            "step_id": "generate_draft",
            "title": "Generate Draft",
            "status": "completed",
            "summary": "Generated a first-pass configuration draft.",
            "details": {
                "export_format": config_result["export_format"],
                "schema_loaded": config_result["schema_loaded"],
            },
        }
    )
    state.step_results.append(
        {
            "step_id": "validate_draft",
            "title": "Validate Draft",
            "status": "completed",
            "summary": "Validated the generated draft against the available schema.",
            "details": config_result["validation_results"]["validation_summary"],
        }
    )

    action_proposals = [
        {
            "proposal_id": f"proposal_{task_id}_config_review",
            "title": "Approve Generated Config Draft",
            "proposal_type": "config_apply",
            "before_summary": "No config has been applied yet.",
            "after_summary": "The reviewed JSON draft can move into the export/apply stage after confirmation.",
            "rationale": "This draft changes structured configuration content and should be explicitly approved before adoption.",
            "risk_flags": "LOW",
            "dry_run_preview": {"draft_config": config_result["draft_config"]},
            "display_hints": {"panel": "ConfigGenerator"},
            "requires_confirmation": True,
            "confirmation": {
                "state": "pending",
                "decision_endpoint": f"/api/v1/proposals/proposal_{task_id}_config_review/decision",
            },
        }
    ]

    return {
        "result": {
            **config_result,
            "retrieved_references": support["citations"],
            "supporting_notes": support["answer"],
        },
        "step_results": state.step_results,
        "retrieval_trace": support["retrieval_trace"],
        "tools": [
            {
                "tool_id": "load_schema_examples",
                "status": "completed",
                "summary": f"Retrieved {len(support['retrieved_docs'])} schema/example chunk(s).",
            },
            {
                "tool_id": "generate_design_config",
                "status": "completed",
                "summary": config_result["explanation"],
            },
        ],
        "warnings": support["warnings"],
        "artifacts": [
            {
                "artifact_type": "config_draft",
                "label": "Generated Config Draft",
                "filename": "generated_config.json",
                "content": config_result["draft_config"],
            },
            {
                "artifact_type": "config_generation_report",
                "label": "Config Generation Report",
                "filename": "config_generation_report.json",
                "content": {
                    "config_result": config_result,
                    "support": support,
                },
            },
        ],
        "action_proposals": action_proposals,
    }
