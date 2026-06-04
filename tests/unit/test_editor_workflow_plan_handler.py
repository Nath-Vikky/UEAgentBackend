from __future__ import annotations

from app.services.task_handlers.editor_workflow import EditorWorkflowPlanHandler


def test_workflow_quick_actions_skip_dependency_blocked_steps() -> None:
    plan = {
        "plan_id": "workflow_plan_test",
        "steps": [
            {
                "step_index": 0,
                "step_id": "step_0_add_blueprint_node_template",
                "title": "Add node",
                "operation_type": "add_blueprint_node_template",
                "proposal_ready": True,
                "missing_inputs": [],
                "depends_on_step_ids": [],
            },
            {
                "step_index": 1,
                "step_id": "step_1_compile_blueprint",
                "title": "Compile Blueprint",
                "operation_type": "compile_blueprint",
                "proposal_ready": True,
                "missing_inputs": [],
                "depends_on_step_ids": ["step_0_add_blueprint_node_template"],
            },
        ],
    }

    actions = EditorWorkflowPlanHandler._build_step_quick_actions(plan=plan, output_language="en")

    assert len(actions) == 1
    assert actions[0]["payload"]["workflow_step_id"] == "step_0_add_blueprint_node_template"


def test_workflow_step_display_status_reports_dependency_wait() -> None:
    assert EditorWorkflowPlanHandler._step_display_status({"proposal_ready": False}) == "needs_more_input"
    assert (
        EditorWorkflowPlanHandler._step_display_status(
            {"proposal_ready": True, "depends_on_step_ids": ["step_0"]}
        )
        == "waiting_dependency"
    )
    assert EditorWorkflowPlanHandler._step_display_status({"proposal_ready": True}) == "ready"
