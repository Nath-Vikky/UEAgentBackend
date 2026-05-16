from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.schemas.requests import UnifiedTaskRequest


ALLOWED_PROJECT_FILE_SUFFIXES = {
    ".h",
    ".hpp",
    ".hh",
    ".inl",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cs",
    ".md",
    ".txt",
    ".json",
    ".ini",
    ".yaml",
    ".yml",
    ".uproject",
    ".uplugin",
}

PROJECT_FILE_REFERENCE_TOKENS = (
    "this file",
    "current file",
    "that file",
    "read file",
    "open file",
    "explain file",
    "这个文件",
    "当前文件",
    "该文件",
    "读取文件",
    "查看文件",
    "解释文件",
)


def project_file_candidate(request: UnifiedTaskRequest) -> dict[str, Any]:
    project_root = str(request.payload.get("project_root") or request.context.project_root or "").strip()
    file_path = str(
        request.payload.get("read_file_path")
        or request.payload.get("file_path")
        or request.payload.get("current_file")
        or request.context.current_file
        or ""
    ).strip()
    try:
        max_bytes = int(
            request.payload.get("max_file_read_bytes")
            or request.payload.get("max_bytes")
            or 40_000
        )
    except (TypeError, ValueError):
        max_bytes = 40_000
    return {
        "project_root": project_root,
        "file_path": file_path,
        "max_bytes": max(1024, min(max_bytes, 120_000)),
    }


def should_read_project_file(*, request: UnifiedTaskRequest, query: str) -> bool:
    candidate = project_file_candidate(request)
    if not candidate["project_root"] or not candidate["file_path"]:
        return False
    lowered = query.lower()
    return any(token in lowered or token in query for token in PROJECT_FILE_REFERENCE_TOKENS)


def read_project_file_tool(request: UnifiedTaskRequest) -> dict[str, Any]:
    candidate = project_file_candidate(request)
    return read_project_file(
        project_root=str(candidate["project_root"]),
        file_path=str(candidate["file_path"]),
        max_bytes=int(candidate["max_bytes"]),
    )


def read_project_file(
    *,
    project_root: str,
    file_path: str,
    max_bytes: int = 40_000,
) -> dict[str, Any]:
    max_bytes = max(1024, min(int(max_bytes or 40_000), 120_000))
    if not project_root or not file_path:
        return {
            "status": "skipped",
            "reason": "missing_project_root_or_file_path",
            "file_path": file_path,
        }

    root = Path(project_root).resolve()
    requested = Path(file_path)
    resolved = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    try:
        is_inside_root = os.path.commonpath([str(root), str(resolved)]) == str(root)
    except ValueError:
        is_inside_root = False
    if not is_inside_root:
        return {
            "status": "blocked",
            "reason": "file_outside_project_root",
            "file_path": file_path,
            "project_root": str(root),
            "resolved_path": str(resolved),
        }

    if resolved.suffix.lower() not in ALLOWED_PROJECT_FILE_SUFFIXES:
        return {
            "status": "blocked",
            "reason": "unsupported_file_extension",
            "file_path": file_path,
            "resolved_path": str(resolved),
            "allowed_suffixes": sorted(ALLOWED_PROJECT_FILE_SUFFIXES),
        }
    if not resolved.exists() or not resolved.is_file():
        return {
            "status": "error",
            "reason": "file_not_found",
            "file_path": file_path,
            "resolved_path": str(resolved),
        }

    with resolved.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    return {
        "status": "completed",
        "reason": "read_completed",
        "file_path": file_path,
        "resolved_path": str(resolved),
        "bytes_read": min(len(raw), max_bytes),
        "max_bytes": max_bytes,
        "truncated": truncated,
        "text_excerpt": text,
    }


def project_file_candidate_from_result(project_file_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_path": project_file_result.get("file_path"),
        "max_bytes": project_file_result.get("max_bytes"),
    }


def project_file_fallback_answer(
    *,
    project_file_result: dict[str, Any],
    output_language: str,
) -> str:
    if project_file_result.get("status") == "completed":
        excerpt = str(project_file_result.get("text_excerpt") or "").strip()
        preview = excerpt[:500] + ("..." if len(excerpt) > 500 else "")
        if output_language.startswith("zh"):
            return (
                f"我已读取当前项目文件 `{project_file_result.get('file_path')}`。"
                f"当前没有可用 LLM 综合解释，因此先返回文件片段供你确认：\n\n{preview}"
            )
        return (
            f"I read project file `{project_file_result.get('file_path')}`. "
            "No live LLM synthesis is available, so here is the file excerpt for confirmation:\n\n"
            f"{preview}"
        )
    reason = project_file_result.get("reason") or "unknown_reason"
    if output_language.startswith("zh"):
        return f"我尝试读取当前项目文件，但未成功：{reason}。"
    return f"I tried to read the current project file, but it did not succeed: {reason}."
