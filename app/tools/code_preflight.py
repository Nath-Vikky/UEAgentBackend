from __future__ import annotations

import re
from typing import Any

CPP_SUFFIXES = (".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cpp", ".cxx")
HEADER_SUFFIXES = (".h", ".hpp", ".hh", ".inl")
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx")


def _normalize_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def _path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _basename(path: str) -> str:
    return _path_parts(path)[-1] if _path_parts(path) else ""


def _stem(path: str) -> str:
    name = _basename(path)
    return name.rsplit(".", 1)[0] if "." in name else name


def _suffix(path: str) -> str:
    name = _basename(path).lower()
    return "." + name.rsplit(".", 1)[1] if "." in name else ""


def _is_cpp_path(path: str) -> bool:
    return path.lower().endswith(CPP_SUFFIXES)


def _is_header_path(path: str) -> bool:
    return path.lower().endswith(HEADER_SUFFIXES)


def _is_source_path(path: str) -> bool:
    return path.lower().endswith(SOURCE_SUFFIXES)


def _is_absolute_or_escaping(path: str) -> bool:
    if not path:
        return True
    if path.startswith(("/", "\\")):
        return True
    if re.match(r"^[A-Za-z]:", path):
        return True
    return any(part == ".." for part in _path_parts(path))


def _is_expected_ue_cpp_path(path: str) -> bool:
    parts = _path_parts(path)
    lowered_parts = [part.lower() for part in parts]
    if "source" not in lowered_parts:
        return False
    return "public" in lowered_parts or "private" in lowered_parts


def _finding(
    finding_id: str,
    *,
    severity: str,
    category: str,
    title: str,
    message: str,
    suggestion: str,
    file_path: str | None = None,
    item_id: str | None = None,
    evidence: str | None = None,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "category": category,
        "title": title,
        "message": message,
        "suggestion": suggestion,
        "file_path": file_path,
        "item_id": item_id,
        "evidence": evidence,
    }


def _has_balanced_braces(code: str) -> bool:
    balance = 0
    for char in code:
        if char == "{":
            balance += 1
        elif char == "}":
            balance -= 1
        if balance < 0:
            return False
    return balance == 0


def _class_declarations(code: str) -> list[tuple[str, str]]:
    return [
        (match.group("name"), match.group("base"))
        for match in re.finditer(
            r"class\s+(?:[A-Z0-9_]+_API\s+)?(?P<name>[AU][A-Za-z0-9_]*)\s*:\s*public\s+(?P<base>[AU][A-Za-z0-9_]*)",
            code,
        )
    ]


def _expected_class_prefix(base: str) -> str | None:
    if base.startswith(("AActor", "ACharacter", "APawn", "AController", "AGameMode")):
        return "A"
    if base.startswith(
        (
            "UActorComponent",
            "USceneComponent",
            "UGameInstanceSubsystem",
            "UWorldSubsystem",
            "UDeveloperSettings",
            "UAttributeSet",
            "UObject",
        )
    ):
        return "U"
    return None


def _text_contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _is_enhanced_input_context(text: str) -> bool:
    return _text_contains_any(
        text,
        (
            "enhanced input",
            "enhancedinput",
            "input action",
            "input mapping",
            "mapping context",
            "uinputaction",
            "uinputmappingcontext",
            "uenhancedinputcomponent",
        ),
    )


def build_code_generation_preflight(
    *,
    result: dict[str, Any],
    requirement: str = "",
    target_module: str = "",
) -> dict[str, Any]:
    """Run lightweight deterministic checks on generated UE C++ drafts.

    This is intentionally smaller than clang/UHT. It catches common local-agent
    failures before users copy a draft into an Unreal project.
    """

    generated_items = [item for item in list(result.get("generated_items") or []) if isinstance(item, dict)]
    findings: list[dict[str, Any]] = []
    header_stems: set[str] = set()
    source_stems: set[str] = set()
    cpp_item_count = 0

    if not generated_items:
        findings.append(
            _finding(
                "no_generated_items",
                severity="error",
                category="structure",
                title="No generated code items",
                message="The code generation response did not contain any generated_items.",
                suggestion="Return at least one virtual generated item with file_path and code.",
            )
        )

    for item in generated_items:
        item_id = str(item.get("item_id") or "")
        path = _normalize_path(item.get("file_path") or item.get("path") or item.get("label"))
        code = str(item.get("code") or item.get("content") or "")
        suffix = _suffix(path)

        if _is_cpp_path(path):
            cpp_item_count += 1
        if _is_header_path(path):
            header_stems.add(_stem(path))
        if _is_source_path(path):
            source_stems.add(_stem(path))

        if _is_absolute_or_escaping(path):
            findings.append(
                _finding(
                    "unsafe_generated_path",
                    severity="error",
                    category="path",
                    title="Unsafe generated path",
                    message="Generated file paths must be relative and must not escape the UE project.",
                    suggestion="Use paths such as Source/<Module>/Public/<Class>.h or Source/<Module>/Private/<Class>.cpp.",
                    file_path=path,
                    item_id=item_id,
                )
            )

        if suffix in CPP_SUFFIXES and not _is_expected_ue_cpp_path(path):
            findings.append(
                _finding(
                    "unexpected_ue_cpp_path",
                    severity="warning",
                    category="path",
                    title="UE C++ path is not under Source Public/Private",
                    message="The generated C++ path does not follow the usual UE module layout.",
                    suggestion="Prefer Source/<Module>/Public for headers and Source/<Module>/Private for .cpp files.",
                    file_path=path,
                    item_id=item_id,
                )
            )

        if suffix in {".txt", ".md"} and _text_contains_any(
            f"{requirement} {path}", ("ue", "unreal", "cpp", "c++", "actor", "character", "component")
        ):
            findings.append(
                _finding(
                    "virtual_text_draft_for_cpp_request",
                    severity="warning",
                    category="structure",
                    title="Text draft returned for a UE C++ request",
                    message="The request appears to need UE C++ files, but the generated item is a text/markdown draft.",
                    suggestion="Return concrete .h/.cpp generated_items with suggested module paths.",
                    file_path=path,
                    item_id=item_id,
                )
            )

        if "```" in code:
            findings.append(
                _finding(
                    "markdown_fence_in_code",
                    severity="warning",
                    category="format",
                    title="Markdown fence found inside generated code",
                    message="Generated item code should contain raw source text, not markdown code fences.",
                    suggestion="Remove ``` fences before exposing the generated item to the frontend.",
                    file_path=path,
                    item_id=item_id,
                )
            )

        if _is_cpp_path(path) and code and not _has_balanced_braces(code):
            findings.append(
                _finding(
                    "unbalanced_cpp_braces",
                    severity="error",
                    category="syntax_smoke",
                    title="Unbalanced braces in generated C++",
                    message="The generated C++ item has unbalanced curly braces.",
                    suggestion="Regenerate or fix the draft before offering it as a copyable UE C++ file.",
                    file_path=path,
                    item_id=item_id,
                )
            )

        if _is_header_path(path):
            if "#pragma once" not in code:
                findings.append(
                    _finding(
                        "missing_pragma_once",
                        severity="warning",
                        category="ue_header",
                        title="Header is missing #pragma once",
                        message="UE C++ headers should usually start with #pragma once.",
                        suggestion="Add #pragma once to the generated header.",
                        file_path=path,
                        item_id=item_id,
                    )
                )
            if any(token in code for token in ("UCLASS", "USTRUCT", "UENUM")):
                expected_generated_include = f'#include "{_stem(path)}.generated.h"'
                if ".generated.h" not in code:
                    findings.append(
                        _finding(
                            "missing_generated_header",
                            severity="error",
                            category="ue_reflection",
                            title="Missing generated.h include",
                            message="A reflected UE header must include its matching .generated.h file.",
                            suggestion=f"Add {expected_generated_include} after normal includes.",
                            file_path=path,
                            item_id=item_id,
                        )
                    )
                elif expected_generated_include not in code:
                    findings.append(
                        _finding(
                            "generated_header_name_mismatch",
                            severity="warning",
                            category="ue_reflection",
                            title="generated.h include does not match file name",
                            message="The generated.h include should normally match the header file stem.",
                            suggestion=f"Use {expected_generated_include}.",
                            file_path=path,
                            item_id=item_id,
                        )
                    )
                if "GENERATED_BODY()" not in code:
                    findings.append(
                        _finding(
                            "missing_generated_body",
                            severity="error",
                            category="ue_reflection",
                            title="Missing GENERATED_BODY()",
                            message="A reflected UE class/struct/enum wrapper is missing GENERATED_BODY().",
                            suggestion="Add GENERATED_BODY() inside the reflected type declaration.",
                            file_path=path,
                            item_id=item_id,
                        )
                    )

        if _is_source_path(path):
            expected_header = f'#include "{_stem(path)}.h"'
            if expected_header not in code:
                findings.append(
                    _finding(
                        "source_missing_matching_header_include",
                        severity="warning",
                        category="include",
                        title="Source file may not include its matching header",
                        message="The .cpp file does not include the same-stem header.",
                        suggestion=f"Add {expected_header} near the top of the .cpp file if this is the owning source.",
                        file_path=path,
                        item_id=item_id,
                    )
                )

        for class_name, base_name in _class_declarations(code):
            expected_prefix = _expected_class_prefix(base_name)
            if expected_prefix and not class_name.startswith(expected_prefix):
                findings.append(
                    _finding(
                        "ue_class_prefix_mismatch",
                        severity="warning",
                        category="ue_naming",
                        title="UE class prefix does not match base class",
                        message=f"{class_name} derives from {base_name}, but its prefix is unusual for that base.",
                        suggestion=f"Use a {expected_prefix}-prefixed class name for this base type.",
                        file_path=path,
                        item_id=item_id,
                        evidence=f"{class_name} : public {base_name}",
                    )
                )

    if cpp_item_count:
        missing_headers = sorted(source_stems - header_stems)
        missing_sources = sorted(header_stems - source_stems)
        for stem in missing_headers[:5]:
            findings.append(
                _finding(
                    "missing_header_pair",
                    severity="warning",
                    category="file_pair",
                    title="C++ source has no matching header item",
                    message=f"{stem}.cpp was generated without a matching {stem}.h item.",
                    suggestion="Return header/source pairs for UE reflected classes whenever possible.",
                    evidence=stem,
                )
            )
        for stem in missing_sources[:5]:
            findings.append(
                _finding(
                    "missing_source_pair",
                    severity="warning",
                    category="file_pair",
                    title="C++ header has no matching source item",
                    message=f"{stem}.h was generated without a matching {stem}.cpp item.",
                    suggestion="Return header/source pairs for UE classes unless the header is intentionally header-only.",
                    evidence=stem,
                )
            )

    text_blob = "\n".join(
        [
            requirement,
            target_module,
            str(result.get("summary") or ""),
            "\n".join(str(item) for item in result.get("notes") or []),
            "\n".join(str(item) for item in result.get("patch_plan") or []),
            "\n".join(str(item.get("code") or "") for item in generated_items),
        ]
    )
    if _is_enhanced_input_context(text_blob):
        required_terms = {
            "input_action_reference": ("uinputaction", "inputaction"),
            "mapping_context_reference": ("uinputmappingcontext", "inputmappingcontext"),
            "enhanced_input_component": ("uenhancedinputcomponent", "enhancedinputcomponent"),
            "bind_action": ("bindaction",),
            "add_mapping_context": ("addmappingcontext",),
            "buildcs_dependency_note": (
                "build.cs",
                "publicdependencymodulenames",
                "privatedependencymodulenames",
                "module dependency",
                "module dependencies",
            ),
        }
        lowered_blob = text_blob.lower()
        for finding_key, terms in required_terms.items():
            if not any(term in lowered_blob for term in terms):
                findings.append(
                    _finding(
                        f"enhanced_input_missing_{finding_key}",
                        severity="warning",
                        category="enhanced_input",
                        title="Enhanced Input draft is missing a common element",
                        message=f"The generated draft did not mention {finding_key.replace('_', ' ')}.",
                        suggestion=(
                            "For Enhanced Input Character code, include InputAction/MappingContext properties, "
                            "UEnhancedInputComponent bindings, AddMappingContext, and a Build.cs dependency note."
                        ),
                    )
                )

    error_count = sum(1 for item in findings if item["severity"] == "error")
    warning_count = sum(1 for item in findings if item["severity"] == "warning")
    info_count = sum(1 for item in findings if item["severity"] == "info")
    status = "failed" if error_count else "warning" if warning_count else "passed"
    quality_score = max(0.0, 1.0 - error_count * 0.25 - warning_count * 0.08)

    return {
        "version": "ue_cpp_codegen_preflight_v1",
        "status": status,
        "quality_score": round(quality_score, 4),
        "summary": {
            "checked_item_count": len(generated_items),
            "cpp_item_count": cpp_item_count,
            "finding_count": len(findings),
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "has_header_source_pair": bool(header_stems and source_stems and header_stems & source_stems),
        },
        "findings": findings,
        "automation_boundary": (
            "Lightweight static preflight only; it does not run clang, UnrealHeaderTool, Build.cs resolution, "
            "or the UE editor compiler."
        ),
    }
