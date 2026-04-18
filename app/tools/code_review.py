from __future__ import annotations

import re
from typing import Any

from app.schemas.requests import ContextInput

DIFF_HUNK_RE = re.compile(r"^@@", re.MULTILINE)
FUNCTION_RE = re.compile(r"\b(?:virtual\s+)?(?:void|bool|int32|float|double|F\w+|U\w+|A\w+)\s+(\w+)\s*\(")
CLASS_RE = re.compile(r"\bclass\s+(\w+)")
INCLUDE_RE = re.compile(r'^\s*#include\s+["<]([^">]+)[">]', re.MULTILINE)


def _collect_source(payload: dict[str, Any], context: ContextInput) -> tuple[str, str]:
    if payload.get("diff_text"):
        return str(payload["diff_text"]), "diff_text"
    if payload.get("code"):
        return str(payload["code"]), "code"
    if payload.get("file_content"):
        return str(payload["file_content"]), "file_content"
    fallback = payload.get("user_query") or context.current_file or ""
    return str(fallback), "query_only"


def _line_numbers(lines: list[str], predicate) -> list[int]:
    return [index for index, line in enumerate(lines, start=1) if predicate(line)]


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
    source_text, source_kind = _collect_source(payload, context)
    lines = source_text.splitlines() or [source_text]
    issues: list[dict[str, Any]] = []

    for line_no in _line_numbers(
        lines,
        lambda line: "*" in line and "TObjectPtr" not in line and "TWeakObjectPtr" not in line and "UPROPERTY" not in line,
    )[:5]:
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
        lambda line: "AsyncTask(" in line or "FRunnable" in line or "std::thread" in line,
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
        },
    }
