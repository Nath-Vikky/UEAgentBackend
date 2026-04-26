from app.tools.code_generate import generate_code_draft


def test_code_generate_treats_generic_target_as_ue_cpp_draft() -> None:
    result = generate_code_draft(
        {
            "target_type": "general",
            "requirement_description": "spawn helper actor",
        }
    )

    assert "draft.txt" not in result["code_draft"]
    assert "Source/SpawnHelper.h" in result["code_draft"]
    assert "Source/SpawnHelper.cpp" in result["code_draft"]
    assert result["write_policy"]["written_to_disk"] is False
    assert all(item["write_status"] == "not_written" for item in result["generated_items"])


def test_code_generate_falls_back_to_safe_ascii_class_name_for_chinese_requirement() -> None:
    result = generate_code_draft(
        {
            "target_type": "ue_cpp_class",
            "requirement_description": "生成一个交互 Actor",
        }
    )

    assert "Source/GeneratedFeature.h" in result["code_draft"]
    assert "Source/GeneratedFeature.cpp" in result["code_draft"]
