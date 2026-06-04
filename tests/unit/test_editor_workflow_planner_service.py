from __future__ import annotations

from app.schemas.requests import SessionInput, SessionMessageInput, UnifiedTaskRequest
from app.services.editor_workflow_planner_service import EditorWorkflowPlannerService


def test_blueprint_workflow_plan_emits_two_confirmed_steps() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal='Add "Ready" Print String on BeginPlay and compile it',
        workflow_type="blueprint_print_then_compile",
        payload={"blueprint_path": "/Game/Blueprints/BP_Player"},
    )

    assert plan["schema_version"] == "editor_workflow_plan_v1"
    assert plan["status"] == "planned"
    assert plan["step_count"] == 2
    assert plan["ready_step_count"] == 2
    assert plan["auto_execute"] is False
    assert plan["requires_user_confirmation_per_step"] is True

    first, second = plan["steps"]
    assert first["operation_type"] == "add_blueprint_node_template"
    assert first["payload"]["template_id"] == "print_string"
    assert first["payload"]["entry_event"] == "BeginPlay"
    assert first["payload"]["message"] == "Ready"
    assert first["payload"]["compile_after_edit"] is False
    assert second["operation_type"] == "compile_blueprint"
    assert second["depends_on_step_ids"] == ["step_0_add_blueprint_node_template"]


def test_blueprint_workflow_can_use_delay_print_template() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal='Add "Ready" Print String after 2 seconds on BeginPlay and compile it',
        workflow_type="blueprint_print_then_compile",
        payload={"blueprint_path": "/Game/Blueprints/BP_Player"},
    )

    first, second = plan["steps"]
    assert plan["status"] == "planned"
    assert first["operation_type"] == "add_blueprint_node_template"
    assert first["title"] == "Add BeginPlay Delay -> Print String nodes"
    assert first["payload"]["template_id"] == "delay_print_string"
    assert first["payload"]["delay_seconds"] == 2.0
    assert first["payload"]["compile_after_edit"] is False
    assert second["operation_type"] == "compile_blueprint"
    assert second["depends_on_step_ids"] == ["step_0_add_blueprint_node_template"]


def test_blueprint_workflow_uses_active_context_blueprint_focus() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal='Add "Ready" Print String and compile it',
        workflow_type="blueprint_print_then_compile",
        payload={},
        context={
            "active_context": {
                "blueprint": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor",
                    "current_graph_name": "ConstructionScript",
                    "has_blueprint_focus": True,
                }
            }
        },
    )

    first, second = plan["steps"]
    assert plan["status"] == "planned"
    assert first["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"
    assert first["payload"]["graph_name"] == "ConstructionScript"
    assert first["payload"]["entry_event"] == ""
    assert second["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"


def test_blueprint_workflow_explicit_eventgraph_overrides_active_graph() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal='Add "Ready" Print String in EventGraph and compile it',
        workflow_type="blueprint_print_then_compile",
        payload={"graph_name": "EventGraph"},
        context={
            "active_context": {
                "blueprint": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor",
                    "current_graph_name": "ConstructionScript",
                }
            }
        },
    )

    first = plan["steps"][0]
    assert first["payload"]["graph_name"] == "EventGraph"
    assert first["payload"]["entry_event"] == "BeginPlay"


def test_blueprint_connect_workflow_uses_current_node_and_graph_summary() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Connect the current node to Print String then compile",
        workflow_type="blueprint_connect_then_compile",
        payload={"target_node_name": "Print String"},
        context={
            "active_context": {
                "blueprint": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor",
                    "current_graph_name": "EventGraph",
                    "current_node_summary": {
                        "node_id": "event-begin-play",
                        "title": "Event BeginPlay",
                        "pins": [
                            {
                                "pin_name": "then",
                                "direction": "output",
                                "category": "exec",
                            }
                        ],
                    },
                    "current_graph_summary": {
                        "graph_name": "EventGraph",
                        "nodes": [
                            {
                                "node_id": "event-begin-play",
                                "title": "Event BeginPlay",
                                "pins": [
                                    {
                                        "pin_name": "then",
                                        "direction": "output",
                                        "category": "exec",
                                    }
                                ],
                            },
                            {
                                "node_id": "print-string",
                                "title": "Print String",
                                "pins": [
                                    {
                                        "pin_name": "execute",
                                        "direction": "input",
                                        "category": "exec",
                                    }
                                ],
                            },
                        ],
                    },
                }
            }
        },
    )

    first, second = plan["steps"]
    assert plan["status"] == "planned"
    assert plan["workflow_type"] == "blueprint_connect_then_compile"
    assert first["operation_type"] == "connect_blueprint_nodes"
    assert first["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"
    assert first["payload"]["graph_name"] == "EventGraph"
    assert first["payload"]["source_node_id"] == "event-begin-play"
    assert first["payload"]["source_pin_name"] == "then"
    assert first["payload"]["target_node_id"] == "print-string"
    assert first["payload"]["target_pin_name"] == "execute"
    assert second["operation_type"] == "compile_blueprint"
    assert second["depends_on_step_ids"] == ["step_0_connect_blueprint_nodes"]


def test_blueprint_connect_workflow_reports_missing_explicit_target() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Connect the current node then compile",
        workflow_type="blueprint_connect_then_compile",
        payload={},
        context={
            "active_context": {
                "blueprint": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor",
                    "current_graph_name": "EventGraph",
                    "current_node_summary": {
                        "node_id": "event-begin-play",
                        "pins": [{"pin_name": "then", "direction": "output", "category": "exec"}],
                    },
                }
            }
        },
    )

    first, second = plan["steps"]
    assert plan["status"] == "partial"
    assert "target_node_id" in first["missing_inputs"]
    assert "target_pin_name" in first["missing_inputs"]
    assert second["proposal_ready"] is True


def test_blueprint_enhanced_input_workflow_emits_template_then_compile() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Add Enhanced Input IA_Jump to Print String then compile",
        workflow_type="blueprint_enhanced_input_print_then_compile",
        payload={
            "blueprint_path": "/Game/Blueprints/BP_Player",
            "input_action_path": "/Game/Input/IA_Jump",
        },
    )

    first, second = plan["steps"]
    assert plan["status"] == "planned"
    assert plan["workflow_type"] == "blueprint_enhanced_input_print_then_compile"
    assert first["operation_type"] == "add_blueprint_node_template"
    assert first["payload"]["template_id"] == "enhanced_input_print_string"
    assert first["payload"]["input_action_path"] == "/Game/Input/IA_Jump"
    assert first["payload"]["entry_event"] == ""
    assert first["payload"]["message"] == "IA_Jump triggered"
    assert first["payload"]["compile_after_edit"] is False
    assert second["operation_type"] == "compile_blueprint"
    assert second["payload"]["blueprint_path"] == "/Game/Blueprints/BP_Player"


def test_workflow_templates_describe_plan_only_safety() -> None:
    templates = EditorWorkflowPlannerService.workflow_templates()

    assert templates["schema_version"] == "editor_workflow_templates_v1"
    assert templates["auto_execute"] is False
    assert templates["requires_user_confirmation_per_step"] is True
    assert templates["safety_policy"]["planner_creates_proposals"] is False
    assert templates["safety_policy"]["planner_executes_editor_writes"] is False
    workflow_types = {item["workflow_type"] for item in templates["templates"]}
    assert workflow_types == {
        "blueprint_connect_then_compile",
        "blueprint_enhanced_input_print_then_compile",
        "blueprint_print_then_compile",
        "umg_hud_group",
        "umg_text_widget",
        "arrange_and_tag_actors",
    }


def test_umg_text_workflow_reports_missing_inputs_without_executing() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Create HUD title text",
        workflow_type="umg_text_widget",
        payload={"widget_name": "TitleText"},
    )

    assert plan["status"] == "needs_more_input"
    assert plan["ready_step_count"] == 0
    assert plan["steps"][0]["operation_type"] == "add_umg_widget"
    assert "widget_blueprint_path" in plan["steps"][0]["missing_inputs"]
    assert "text" in plan["steps"][0]["missing_inputs"]
    assert plan["steps"][0]["auto_execute"] is False


def test_umg_hud_group_workflow_emits_bounded_add_widget_steps() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Plan a HUD group under RootCanvas with text 'HP 100'",
        workflow_type="umg_hud_group",
        payload={
            "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            "parent_widget_name": "RootCanvas",
            "group_name": "StatusHUDGroup",
            "label_text": "HP 100",
        },
    )

    assert plan["status"] == "planned"
    assert plan["workflow_type"] == "umg_hud_group"
    assert plan["step_count"] == 4
    assert plan["ready_step_count"] == 4
    assert [step["operation_type"] for step in plan["steps"]] == [
        "add_umg_widget",
        "add_umg_widget",
        "add_umg_widget",
        "add_umg_widget",
    ]
    first, icon, label, button = plan["steps"]
    assert first["payload"]["widget_class"] == "HorizontalBox"
    assert first["payload"]["widget_name"] == "StatusHUDGroup"
    assert first["payload"]["parent_widget_name"] == "RootCanvas"
    assert icon["payload"]["widget_class"] == "Image"
    assert icon["depends_on_step_ids"] == ["step_0_add_umg_widget"]
    assert label["payload"]["widget_class"] == "TextBlock"
    assert label["payload"]["text"] == "HP 100"
    assert button["payload"]["widget_class"] == "Button"
    assert all(step["auto_execute"] is False for step in plan["steps"])


def test_arrange_and_tag_workflow_creates_one_metadata_step_per_actor() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Arrange these actors and add Patrol tag",
        workflow_type="arrange_and_tag_actors",
        payload={
            "actor_references": ["BP_A_1", "BP_B_1"],
            "pattern": {"type": "line", "spacing": 250},
            "metadata": {"tags": ["Patrol"], "tag_mode": "append"},
        },
    )

    assert plan["status"] == "planned"
    assert [step["operation_type"] for step in plan["steps"]] == [
        "arrange_actors_pattern",
        "set_actor_metadata",
        "set_actor_metadata",
    ]
    assert plan["steps"][1]["payload"]["actor_reference"] == "BP_A_1"
    assert plan["steps"][2]["payload"]["actor_reference"] == "BP_B_1"
    assert all(step["create_request_hint"]["path"] == "/api/v1/editor-operations/proposals" for step in plan["steps"])


def test_detect_chat_workflow_request_requires_multistep_signal() -> None:
    request = UnifiedTaskRequest(
        task_type="agent_chat",
        session=SessionInput(
            session_id="workflow_detect",
            messages=[
                SessionMessageInput(
                    role="user",
                    content="Add a Print String node to /Game/Blueprints/BP_PlayerCharacter",
                )
            ],
        ),
        payload={
            "user_query": "Add a Print String node to /Game/Blueprints/BP_PlayerCharacter",
        },
    )

    assert EditorWorkflowPlannerService.detect_chat_workflow_request(request) is None


def test_detect_chat_workflow_request_extracts_blueprint_plan() -> None:
    request = UnifiedTaskRequest(
        task_type="agent_chat",
        session=SessionInput(
            session_id="workflow_detect",
            messages=[
                SessionMessageInput(
                    role="user",
                    content=(
                        "Plan a workflow: add a Print String node to "
                        "/Game/Blueprints/BP_PlayerCharacter then compile it"
                    ),
                )
            ],
        ),
        payload={
            "user_query": (
                "Plan a workflow: add a Print String node to "
                "/Game/Blueprints/BP_PlayerCharacter then compile it"
            ),
            "message": "Ready",
        },
    )

    detected = EditorWorkflowPlannerService.detect_chat_workflow_request(request)

    assert detected is not None
    assert detected["workflow_type"] == "blueprint_print_then_compile"
    assert detected["payload"]["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"


def test_detect_chat_workflow_request_extracts_blueprint_connect_plan_from_focus() -> None:
    request = UnifiedTaskRequest(
        task_type="agent_chat",
        session=SessionInput(
            session_id="workflow_detect_connect",
            messages=[
                SessionMessageInput(
                    role="user",
                    content="Plan a workflow: connect the current node to Print String then compile",
                )
            ],
        ),
        payload={
            "user_query": "Plan a workflow: connect the current node to Print String then compile",
            "target_node_name": "Print String",
        },
    )

    detected = EditorWorkflowPlannerService.detect_chat_workflow_request(
        request,
        context_bundle={
            "active_context": {
                "blueprint": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor",
                    "current_graph_name": "EventGraph",
                    "current_node_summary": {
                        "node_id": "event-begin-play",
                        "pins": [{"pin_name": "then", "direction": "output", "category": "exec"}],
                    },
                    "current_graph_summary": {
                        "graph_name": "EventGraph",
                        "nodes": [
                            {
                                "node_id": "print-string",
                                "title": "Print String",
                                "pins": [{"pin_name": "execute", "direction": "input", "category": "exec"}],
                            }
                        ],
                    },
                }
            }
        },
    )

    assert detected is not None
    assert detected["workflow_type"] == "blueprint_connect_then_compile"
    assert detected["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"
    assert detected["payload"]["source_node_id"] == "event-begin-play"
    assert detected["payload"]["target_node_id"] == "print-string"
    assert detected["payload"]["target_pin_name"] == "execute"


def test_detect_chat_workflow_request_extracts_enhanced_input_plan() -> None:
    request = UnifiedTaskRequest(
        task_type="agent_chat",
        session=SessionInput(
            session_id="workflow_detect_enhanced_input",
            messages=[
                SessionMessageInput(
                    role="user",
                    content="Plan a workflow: add Enhanced Input IA_Jump to BP_Player then compile",
                )
            ],
        ),
        payload={
            "user_query": "Plan a workflow: add Enhanced Input IA_Jump to BP_Player then compile",
            "input_action_path": "/Game/Input/IA_Jump",
        },
        context={"selected_assets": ["/Game/Blueprints/BP_Player"]},
    )

    detected = EditorWorkflowPlannerService.detect_chat_workflow_request(request)

    assert detected is not None
    assert detected["workflow_type"] == "blueprint_enhanced_input_print_then_compile"
    assert detected["payload"]["blueprint_path"] == "/Game/Blueprints/BP_Player"
    assert detected["payload"]["input_action_path"] == "/Game/Input/IA_Jump"


def test_detect_chat_workflow_request_extracts_umg_hud_group_plan() -> None:
    request = UnifiedTaskRequest(
        task_type="agent_chat",
        session=SessionInput(
            session_id="workflow_detect_umg_hud_group",
            messages=[
                SessionMessageInput(
                    role="user",
                    content=(
                        "Plan a HUD group in WBP_MainHUD under RootCanvas "
                        "with text 'HP 100'"
                    ),
                )
            ],
        ),
        payload={
            "user_query": (
                "Plan a HUD group in WBP_MainHUD under RootCanvas "
                "with text 'HP 100'"
            )
        },
    )

    detected = EditorWorkflowPlannerService.detect_chat_workflow_request(
        request,
        context_bundle={
            "project_inventory_context": {
                "query_candidates": [
                    {
                        "asset_path": "/Game/UI/WBP_MainHUD.WBP_MainHUD",
                        "asset_name": "WBP_MainHUD",
                        "asset_type": "WidgetBlueprint",
                    }
                ]
            }
        },
    )

    assert detected is not None
    assert detected["workflow_type"] == "umg_hud_group"
    assert detected["payload"]["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert detected["payload"]["parent_widget_name"] == "RootCanvas"
    assert detected["payload"]["label_text"] == "HP 100"


def test_prepare_step_proposal_request_materializes_single_ready_step() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal='Add "Ready" Print String on BeginPlay and compile it',
        workflow_type="blueprint_print_then_compile",
        payload={"blueprint_path": "/Game/Blueprints/BP_Player"},
    )

    materialized = EditorWorkflowPlannerService.prepare_step_proposal_request(
        workflow_plan_id=plan["plan_id"],
        step=plan["steps"][0],
        requested_by="unit_test",
    )

    assert materialized["schema_version"] == "editor_workflow_step_materialization_v1"
    assert materialized["workflow_plan_id"] == plan["plan_id"]
    assert materialized["workflow_step_id"] == "step_0_add_blueprint_node_template"
    assert materialized["operation_type"] == "add_blueprint_node_template"
    assert materialized["auto_execute"] is False
    assert materialized["requires_user_confirmation"] is True
    assert materialized["proposal_request"]["requested_by"] == "unit_test"
    assert materialized["proposal_request"]["context"]["workflow_materialization"]["auto_execute"] is False


def test_prepare_step_proposal_request_rejects_missing_inputs() -> None:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal="Create HUD title text",
        workflow_type="umg_text_widget",
        payload={"widget_name": "TitleText"},
    )

    try:
        EditorWorkflowPlannerService.prepare_step_proposal_request(step=plan["steps"][0])
    except ValueError as exc:
        assert str(exc) == "workflow_step_not_ready_for_proposal"
    else:
        raise AssertionError("Expected workflow_step_not_ready_for_proposal")
