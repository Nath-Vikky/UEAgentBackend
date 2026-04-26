from app.tools.code_generate import generate_code_draft


def test_code_generate_treats_generic_target_as_ue_cpp_draft() -> None:
    result = generate_code_draft(
        {
            "target_type": "general",
            "requirement_description": "spawn helper actor",
        }
    )

    assert "draft.txt" not in result["code_draft"]
    assert "Source/YourModule/Public/SpawnHelper.h" in result["code_draft"]
    assert "Source/YourModule/Private/SpawnHelper.cpp" in result["code_draft"]
    assert result["write_policy"]["written_to_disk"] is False
    assert all(item["write_status"] == "not_written" for item in result["generated_items"])


def test_code_generate_falls_back_to_safe_ascii_class_name_for_chinese_requirement() -> None:
    result = generate_code_draft(
        {
            "target_type": "ue_cpp_class",
            "requirement_description": "生成一个交互 Actor",
        }
    )

    assert "Source/YourModule/Public/GeneratedFeature.h" in result["code_draft"]
    assert "Source/YourModule/Private/GeneratedFeature.cpp" in result["code_draft"]


def test_code_generate_returns_enhanced_input_character_template() -> None:
    result = generate_code_draft(
        {
            "target_type": "ue_cpp",
            "target_module": "RushBa",
            "requirement_description": "角色增强输入代码怎么写",
        }
    )

    assert "Source/RushBa/Public/EnhancedInputCharacter.h" in result["code_draft"]
    assert "Source/RushBa/Private/EnhancedInputCharacter.cpp" in result["code_draft"]
    assert "UInputMappingContext" in result["code_draft"]["Source/RushBa/Public/EnhancedInputCharacter.h"]
    assert "UEnhancedInputComponent" in result["code_draft"]["Source/RushBa/Private/EnhancedInputCharacter.cpp"]
    assert "EnhancedInput" in "\n".join(result["patch_plan"])


def test_code_generate_returns_interaction_component_template() -> None:
    result = generate_code_draft(
        {
            "target_type": "component",
            "target_module": "RushBa",
            "requirement_description": "交互组件 overlap 怎么写",
        }
    )

    assert "Source/RushBa/Public/InteractionComponent.h" in result["code_draft"]
    assert "Source/RushBa/Private/InteractionComponent.cpp" in result["code_draft"]
    assert "OnComponentBeginOverlap" in result["code_draft"]["Source/RushBa/Private/InteractionComponent.cpp"]


def test_code_generate_returns_line_trace_interaction_template() -> None:
    result = generate_code_draft(
        {
            "target_type": "component",
            "target_module": "RushBa",
            "requirement_description": "射线交互组件怎么写",
        }
    )

    assert "Source/RushBa/Public/LineTraceInteractionComponent.h" in result["code_draft"]
    assert "Source/RushBa/Private/LineTraceInteractionComponent.cpp" in result["code_draft"]
    assert "LineTraceSingleByChannel" in result["code_draft"]["Source/RushBa/Private/LineTraceInteractionComponent.cpp"]


def test_code_generate_returns_game_instance_subsystem_template() -> None:
    result = generate_code_draft(
        {
            "target_type": "subsystem",
            "target_module": "RushBa",
            "requirement_description": "全局管理器子系统怎么写",
        }
    )

    assert "Source/RushBa/Public/GameFeatureSubsystem.h" in result["code_draft"]
    assert "Source/RushBa/Private/GameFeatureSubsystem.cpp" in result["code_draft"]
    assert "UGameInstanceSubsystem" in result["code_draft"]["Source/RushBa/Public/GameFeatureSubsystem.h"]
