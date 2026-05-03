from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ALLOWED_CODE_WRITE_SUFFIXES = {
    ".h",
    ".hpp",
    ".hh",
    ".inl",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cs",
    ".txt",
    ".md",
}
ALLOWED_CODE_WRITE_ROOTS = {"Source", "Plugins"}
MAX_CODE_WRITE_BYTES = 300_000


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_relative_path(file_path: str) -> tuple[str, str | None]:
    raw = str(file_path or "").replace("\\", "/").strip()
    if not raw:
        return "", "empty_file_path"
    if "\x00" in raw:
        return "", "null_byte_in_path"
    if PureWindowsPath(raw).is_absolute() or PurePosixPath(raw).is_absolute():
        return raw, "absolute_paths_are_not_allowed"
    path = PurePosixPath(raw)
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        return raw, "empty_file_path"
    if any(part == ".." for part in parts):
        return raw, "parent_directory_segments_are_not_allowed"
    if ":" in parts[0]:
        return raw, "drive_prefix_is_not_allowed"
    if parts[0] not in ALLOWED_CODE_WRITE_ROOTS:
        return raw, "path_must_start_with_source_or_plugins"
    return "/".join(parts), None


def _safe_target(project_root: Path, relative_path: str) -> tuple[Path | None, str | None]:
    root = project_root.expanduser().resolve(strict=False)
    target = (root / relative_path).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        return None, "target_path_escapes_project_root"
    return target, None


def build_code_write_plan(
    *,
    project_root: str,
    generated_items: list[dict[str, Any]],
    allow_overwrite_existing: bool = False,
) -> dict[str, Any]:
    root = Path(str(project_root or "")).expanduser()
    files: list[dict[str, Any]] = []
    blocked_count = 0
    ready_count = 0

    if not str(project_root or "").strip():
        return {
            "status": "blocked",
            "reason": "missing_project_root",
            "project_root": "",
            "written_to_disk": False,
            "allow_overwrite_existing": allow_overwrite_existing,
            "allowed_roots": sorted(ALLOWED_CODE_WRITE_ROOTS),
            "allowed_suffixes": sorted(ALLOWED_CODE_WRITE_SUFFIXES),
            "files": [],
            "summary": {"ready_count": 0, "blocked_count": 0, "file_count": 0},
        }

    for index, item in enumerate(generated_items, start=1):
        raw_path = str(item.get("file_path") or item.get("path") or item.get("label") or "").strip()
        relative_path, path_error = _normalize_relative_path(raw_path)
        code = str(item.get("code") or item.get("content") or "")
        suffix = Path(relative_path or raw_path).suffix.lower()
        target_path, target_error = (None, None)
        if not path_error:
            target_path, target_error = _safe_target(root, relative_path)

        reason = path_error or target_error
        if not reason and suffix not in ALLOWED_CODE_WRITE_SUFFIXES:
            reason = "unsupported_file_extension"
        encoded_size = len(code.encode("utf-8"))
        if not reason and encoded_size > MAX_CODE_WRITE_BYTES:
            reason = "file_too_large"
        exists = bool(target_path and target_path.exists())
        if not reason and exists and not allow_overwrite_existing:
            reason = "target_file_exists_overwrite_disabled"

        status = "blocked" if reason else "ready"
        blocked_count += 1 if reason else 0
        ready_count += 0 if reason else 1
        files.append(
            {
                "item_id": item.get("item_id") or f"generated_{index}",
                "label": item.get("label") or Path(relative_path or raw_path).name,
                "relative_path": relative_path or raw_path,
                "target_path": str(target_path) if target_path else "",
                "language": item.get("language") or "",
                "content": code,
                "content_sha256": _sha256(code),
                "bytes": encoded_size,
                "exists": exists,
                "allow_overwrite_existing": allow_overwrite_existing,
                "status": status,
                "reason": reason or "ready_to_write",
            }
        )

    status = "ready" if ready_count > 0 and blocked_count == 0 else "blocked"
    return {
        "status": status,
        "reason": "ready" if status == "ready" else "one_or_more_files_blocked",
        "project_root": str(root.resolve(strict=False)),
        "written_to_disk": False,
        "allow_overwrite_existing": allow_overwrite_existing,
        "allowed_roots": sorted(ALLOWED_CODE_WRITE_ROOTS),
        "allowed_suffixes": sorted(ALLOWED_CODE_WRITE_SUFFIXES),
        "files": files,
        "summary": {
            "ready_count": ready_count,
            "blocked_count": blocked_count,
            "file_count": len(files),
        },
    }


def execute_code_write_plan(write_plan: dict[str, Any]) -> dict[str, Any]:
    if write_plan.get("status") != "ready":
        return {
            "execution_state": "blocked",
            "reason": write_plan.get("reason") or "write_plan_not_ready",
            "written_files": [],
            "blocked_files": list(write_plan.get("files") or []),
            "written_to_disk": False,
        }

    project_root = str(write_plan.get("project_root") or "").strip()
    rebuilt_plan = build_code_write_plan(
        project_root=project_root,
        generated_items=[
            {
                "item_id": item.get("item_id"),
                "label": item.get("label"),
                "file_path": item.get("relative_path"),
                "language": item.get("language"),
                "code": item.get("content"),
            }
            for item in write_plan.get("files") or []
        ],
        allow_overwrite_existing=bool(write_plan.get("allow_overwrite_existing")),
    )
    if rebuilt_plan.get("status") != "ready":
        return {
            "execution_state": "blocked",
            "reason": rebuilt_plan.get("reason") or "write_plan_revalidation_failed",
            "written_files": [],
            "blocked_files": list(rebuilt_plan.get("files") or []),
            "written_to_disk": False,
        }

    written_files: list[dict[str, Any]] = []
    for item in rebuilt_plan["files"]:
        target_path = Path(str(item["target_path"]))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(item.get("content") or ""), encoding="utf-8", newline="\n")
        written_files.append(
            {
                "item_id": item.get("item_id"),
                "relative_path": item.get("relative_path"),
                "target_path": str(target_path),
                "bytes": item.get("bytes"),
                "content_sha256": item.get("content_sha256"),
                "status": "written",
            }
        )

    return {
        "execution_state": "files_written",
        "reason": "write_completed",
        "written_files": written_files,
        "blocked_files": [],
        "written_to_disk": True,
    }

