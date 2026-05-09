from __future__ import annotations

import re
from typing import Any

from app.schemas.requests import ContextInput
from app.utils.project_files import ProjectFileAccessError, read_project_code_file

DIFF_HUNK_RE = re.compile(r"^@@", re.MULTILINE)
FUNCTION_RE = re.compile(r"\b(?:virtual\s+)?(?:void|bool|int32|float|double|F\w+|U\w+|A\w+)\s+(\w+)\s*\(")
CLASS_RE = re.compile(r"\bclass\s+(\w+)")
INCLUDE_RE = re.compile(r'^\s*#include\s+["<]([^">]+)[">]', re.MULTILINE)
RAW_UOBJECT_POINTER_RE = re.compile(r"\b(?:UObject|U[A-Za-z_]\w*|A[A-Za-z_]\w*)\s*\*")


def _read_focus(payload: dict[str, Any]) -> str:
    return str(payload.get("focus") or payload.get("review_focus") or "General").strip() or "General"


def _collect_source(payload: dict[str, Any], context: ContextInput) -> tuple[str, str, str | None, dict[str, Any]]:
    focus = _read_focus(payload)
    if payload.get("diff_text"):
        text = str(payload["diff_text"])
        return text, "diff_text", None, {"read_status": "inline", "content_length": len(text), "applied_focus": focus}
    if payload.get("code"):
        text = str(payload["code"])
        return text, "code", None, {"read_status": "inline", "content_length": len(text), "applied_focus": focus}
    if payload.get("file_content"):
        text = str(payload["file_content"])
        return text, "file_content", None, {"read_status": "inline", "content_length": len(text), "applied_focus": focus}
    project_root = payload.get("project_root") or context.project_root
    if payload.get("file_path") and project_root:
        try:
            file_payload = read_project_code_file(
                project_root=str(project_root),
                file_path=str(payload["file_path"]),
                source_roots=list(payload.get("source_roots") or []),
            )
            payload.setdefault("file_path", file_payload["relative_path"])
            metadata = {
                key: file_payload.get(key)
                for key in (
                    "project_root",
                    "relative_path",
                    "file_path",
                    "absolute_path",
                    "resolved_absolute_path",
                    "file_name",
                    "module_name",
                    "file_type",
                    "size_bytes",
                    "content_length",
                    "read_status",
                    "source_roots",
                )
            }
            metadata["applied_focus"] = focus
            return str(file_payload["text"]), "file_path", None, metadata
        except ProjectFileAccessError as exc:
            return (
                "",
                "file_path_error",
                str(exc),
                {
                    "project_root": str(project_root),
                    "requested_file_path": str(payload.get("file_path") or ""),
                    "resolved_absolute_path": None,
                    "read_status": "error",
                    "content_length": 0,
                    "load_error": str(exc),
                    "applied_focus": focus,
                    "source_roots": list(payload.get("source_roots") or []),
                },
            )
    fallback = payload.get("user_query") or context.current_file or ""
    text = str(fallback)
    return text, "query_only", None, {"read_status": "query_only", "content_length": len(text), "applied_focus": focus}


def _line_numbers(lines: list[str], predicate) -> list[int]:
    return [
        index
        for index, line in enumerate(lines, start=1)
        if not _is_comment_only_line(line) and predicate(line)
    ]


def _is_comment_only_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("//", "/*", "*", "*/"))


def _is_background_thread_line(line: str) -> bool:
    if "std::thread" in line or "FRunnable" in line:
        return True
    if "AsyncTask(" not in line:
        return False
    return "ENamedThreads::GameThread" not in line


def _has_uproperty_guard(lines: list[str], line_index: int) -> bool:
    for previous_index in range(line_index - 1, max(-1, line_index - 4), -1):
        previous = lines[previous_index].strip()
        if not previous:
            continue
        if _is_comment_only_line(previous):
            continue
        if "UPROPERTY" in previous:
            return True
        if previous.endswith((";", "{", "}")):
            return False
    return False


def _raw_pointer_line_numbers(lines: list[str]) -> list[int]:
    line_numbers: list[int] = []
    for index, line in enumerate(lines):
        if _is_comment_only_line(line):
            continue
        if "TObjectPtr" in line or "TWeakObjectPtr" in line:
            continue
        if not RAW_UOBJECT_POINTER_RE.search(line):
            continue
        if "UPROPERTY" in line or _has_uproperty_guard(lines, index):
            continue
        line_numbers.append(index + 1)
    return line_numbers


def _issue(rule_id: str, severity: str, title: str, line_no: int | None, evidence: str, suggestion: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "title": title,
        "line": line_no,
        "evidence": evidence.strip(),
        "suggestion": suggestion,
    }


def review_ue_cpp_files(payload: dict[str, Any], context: ContextInput) -> dict[str, Any]:
    source_text, source_kind, load_error, source_metadata = _collect_source(payload, context)
    lines = source_text.splitlines() or [source_text]
    issues: list[dict[str, Any]] = []

    for line_no in _raw_pointer_line_numbers(lines)[:5]:
        issues.append(
            _issue(
                "raw_pointer_ownership",
                "high",
                "Potential raw pointer ownership risk",
                line_no,
                lines[line_no - 1],
                "Prefer TObjectPtr/TWeakObjectPtr or document ownership more explicitly.",
            )
        )

    for line_no in _line_numbers(
        lines,
        lambda line: "Tick(" in line or "PrimaryActorTick" in line,
    )[:3]:
        issues.append(
            _issue(
                "tick_hot_path",
                "medium",
                "Tick usage should be justified",
                line_no,
                lines[line_no - 1],
                "Confirm the work is lightweight or move expensive logic off Tick.",
            )
        )

    for line_no in _line_numbers(
        lines,
        _is_background_thread_line,
    )[:3]:
        issues.append(
            _issue(
                "thread_context",
                "high",
                "Potential thread-context hazard",
                line_no,
                lines[line_no - 1],
                "Review whether UObject or world access is occurring off the game thread.",
            )
        )

    for line_no in _line_numbers(
        lines,
        lambda line: 'TEXT("/Game/' in line or '"/Game/' in line,
    )[:3]:
        issues.append(
            _issue(
                "hardcoded_asset_path",
                "medium",
                "Hard-coded asset path detected",
                line_no,
                lines[line_no - 1],
                "Prefer configurable references or clearly document the dependency.",
            )
        )

    for line_no in _line_numbers(
        lines,
        lambda line: "LoadObject<" in line or "StaticLoadObject" in line or ".TryLoad(" in line,
    )[:3]:
        issues.append(
            _issue(
                "sync_load_usage",
                "medium",
                "Synchronous asset loading detected",
                line_no,
                lines[line_no - 1],
                "Confirm this cannot be deferred or switched to soft references / async loading.",
            )
        )

    for line_no in _line_numbers(
        lines,
        lambda line: "BlueprintCallable" in line or "BlueprintReadWrite" in line,
    )[:3]:
        issues.append(
            _issue(
                "blueprint_surface",
                "low",
                "Blueprint exposure should match the intended API boundary",
                line_no,
                lines[line_no - 1],
                "Re-check whether this symbol needs to be exposed or should remain internal.",
            )
        )

    includes = INCLUDE_RE.findall(source_text)
    if len(includes) > 10:
        issues.append(
            _issue(
                "include_pollution",
                "low",
                "Large include surface detected",
                None,
                f"Found {len(includes)} include directives.",
                "Consider forward declarations and tightening module boundaries.",
            )
        )

    severity_summary = {
        "high": sum(1 for item in issues if item["severity"] == "high"),
        "medium": sum(1 for item in issues if item["severity"] == "medium"),
        "low": sum(1 for item in issues if item["severity"] == "low"),
    }
    static_analysis = payload.get("static_analysis") or []
    static_analysis_summary = {
        "items": len(static_analysis),
        "errors": sum(1 for item in static_analysis if str(item.get("severity", "")).lower() == "error"),
        "warnings": sum(1 for item in static_analysis if str(item.get("severity", "")).lower() == "warning"),
    }
    symbols = sorted(set(CLASS_RE.findall(source_text) + FUNCTION_RE.findall(source_text)))[:12]
    added_lines = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed_lines = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    review_scope = {
        "source_kind": source_kind,
        "file_path": payload.get("file_path") or context.current_file,
        "file_list": payload.get("file_list") or [],
        "module_dir": payload.get("module_dir") or context.current_module,
        "line_count": len(lines),
        "load_error": load_error,
        "project_root": source_metadata.get("project_root") or payload.get("project_root") or context.project_root,
        "resolved_absolute_path": source_metadata.get("resolved_absolute_path") or source_metadata.get("absolute_path"),
        "read_status": source_metadata.get("read_status"),
        "content_length": source_metadata.get("content_length", len(source_text)),
        "applied_focus": source_metadata.get("applied_focus"),
        "source_roots": source_metadata.get("source_roots") or payload.get("source_roots") or [],
        "source_excerpt_truncated": len(source_text) > 12000,
    }
    change_summary = {
        "diff_hunks": len(DIFF_HUNK_RE.findall(source_text)),
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "symbols": symbols,
        "include_count": len(includes),
        "ue_macros": [
            token
            for token in ("UCLASS", "USTRUCT", "UPROPERTY", "UFUNCTION")
            if token in source_text
        ],
    }
    rule_hits = sorted({item["rule_id"] for item in issues})
    suggestions = []
    for item in issues:
        if item["suggestion"] not in suggestions:
            suggestions.append(item["suggestion"])
    if not suggestions:
        suggestions.append("No major rule hits were detected. A human review can focus on architecture and naming quality.")

    summary = (
        f"Scanned {len(lines)} lines and found {len(issues)} potential review findings."
        if issues
        else f"Scanned {len(lines)} lines and did not detect any obvious rule-based issues."
    )
    if load_error:
        summary = f"Could not read the selected file, so the review fell back to an empty source. Error: {load_error}"
    return {
        "issue_list": issues,
        "severity_summary": severity_summary,
        "summary": summary,
        "suggestions": suggestions[:5],
        "review_scope": review_scope,
        "change_summary": change_summary,
        "static_analysis_summary": static_analysis_summary,
        "need_human_followup": bool(severity_summary["high"] or static_analysis_summary["errors"]),
        "rule_hits": rule_hits,
        "preprocess_summary": {
            "symbols": symbols,
            "includes": includes[:12],
            "source_kind": source_kind,
            "load_error": load_error,
            "file_read": source_metadata,
            "static_analysis_trace": {
                "rule_hits": rule_hits,
                "static_analysis_summary": static_analysis_summary,
            },
        },
        "analysis_input": {
            "source_excerpt": source_text[:12000],
            "source_length": len(source_text),
            "source_excerpt_truncated": len(source_text) > 12000,
        },
    }
