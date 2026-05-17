from __future__ import annotations

from app.schemas.requests import SessionInput, UnifiedTaskRequest
from app.services.code_generation_service import _llm_generation_rejection_reason
from app.tools.code_generate import generate_code_draft
from app.tools.code_preflight import build_code_generation_preflight


def test_preflight_passes_enhanced_input_template() -> None:
    result = generate_code_draft(
        {
            "target_type": "ue_cpp",
            "target_module": "RushBa",
            "requirement_description": "Enhanced Input player character movement code",
        }
    )

    report = build_code_generation_preflight(
        result=result,
        requirement="Enhanced Input player character movement code",
        target_module="RushBa",
    )

    assert report["status"] == "passed"
    assert report["summary"]["checked_item_count"] == 2
    assert report["summary"]["has_header_source_pair"] is True
    assert report["summary"]["error_count"] == 0


def test_generate_code_draft_handles_chinese_input_enhancement_word_order() -> None:
    result = generate_code_draft(
        {
            "target_type": "ue_cpp",
            "target_module": "RushBa",
            "requirement_description": "\u89d2\u8272\u8f93\u5165\u589e\u5f3a\u7684\u4ee3\u7801\u600e\u4e48\u5199",
        }
    )
    code = "\n".join(item["code"] for item in result["generated_items"])

    assert "Source/RushBa/Public/EnhancedInputCharacter.h" in result["code_draft"]
    assert "ACharacter" in code
    assert "UEnhancedInputComponent" in code
    assert "UInputAction" in code
    assert "UInputMappingContext" in code
    assert "BindAction" in code
    assert "AddMappingContext" in code


def test_llm_enhanced_input_skeleton_is_rejected_for_template_fallback() -> None:
    request = UnifiedTaskRequest(
        task_type="code_generate",
        session=SessionInput(
            session_id="unit_codegen_quality_gate",
            messages=[
                {
                    "role": "user",
                    "content": "\u89d2\u8272\u8f93\u5165\u589e\u5f3a\u7684\u4ee3\u7801\u600e\u4e48\u5199",
                }
            ],
        ),
        payload={
            "user_query": "\u89d2\u8272\u8f93\u5165\u589e\u5f3a\u7684\u4ee3\u7801\u600e\u4e48\u5199",
            "requirement_description": "\u89d2\u8272\u8f93\u5165\u589e\u5f3a\u7684\u4ee3\u7801\u600e\u4e48\u5199",
            "target_type": "ue_cpp",
        },
    )

    reason = _llm_generation_rejection_reason(
        request=request,
        query=request.payload["requirement_description"],
        generated_items=[
            {
                "file_path": "Source/RushBa/Public/MyActor.h",
                "code": "class AMyActor : public AActor { virtual void BeginPlay() override; };",
            },
            {
                "file_path": "Source/RushBa/Private/MyActor.cpp",
                "code": "void AMyActor::BeginPlay() { Super::BeginPlay(); }",
            },
        ],
    )

    assert reason.startswith("enhanced_input_incomplete:")
    assert "enhanced_input_component" in reason


def test_preflight_flags_text_draft_for_cpp_request() -> None:
    report = build_code_generation_preflight(
        result={
            "generated_items": [
                {
                    "item_id": "generated_1",
                    "file_path": "draft.txt",
                    "language": "text",
                    "code": "Create an AActor later.",
                }
            ]
        },
        requirement="Generate a UE C++ actor",
        target_module="Gameplay",
    )

    assert report["status"] == "warning"
    assert any(item["finding_id"] == "virtual_text_draft_for_cpp_request" for item in report["findings"])


def test_preflight_flags_reflection_header_errors() -> None:
    report = build_code_generation_preflight(
        result={
            "generated_items": [
                {
                    "item_id": "generated_1",
                    "file_path": "Source/Demo/Public/BadActor.h",
                    "language": "cpp",
                    "code": "UCLASS()\nclass DEMO_API ABadActor : public AActor\n{\n};",
                }
            ]
        },
        requirement="Generate a UE C++ actor",
        target_module="Demo",
    )

    finding_ids = {item["finding_id"] for item in report["findings"]}
    assert report["status"] == "failed"
    assert "missing_pragma_once" in finding_ids
    assert "missing_generated_header" in finding_ids
    assert "missing_generated_body" in finding_ids


def test_preflight_flags_unsafe_paths() -> None:
    report = build_code_generation_preflight(
        result={
            "generated_items": [
                {
                    "item_id": "generated_1",
                    "file_path": "../Source/Demo/Private/Bad.cpp",
                    "language": "cpp",
                    "code": '#include "Bad.h"\nvoid Foo() {}',
                }
            ]
        },
        requirement="Generate a UE C++ helper",
        target_module="Demo",
    )

    assert report["status"] == "failed"
    assert any(item["finding_id"] == "unsafe_generated_path" for item in report["findings"])
