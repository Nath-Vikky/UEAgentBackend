from __future__ import annotations

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
