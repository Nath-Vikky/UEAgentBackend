from __future__ import annotations

from pathlib import Path


DEFAULT_CODE_EXTENSIONS = [
    ".h",
    ".hpp",
    ".hh",
    ".inl",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cs",
]
DEFAULT_SOURCE_ROOTS = ["Source", "Plugins"]
DEFAULT_FILE_SCAN_LIMIT = 200
DEFAULT_READ_MAX_BYTES = 256 * 1024


class ProjectFileAccessError(ValueError):
    pass


def _normalize_extensions(extensions: list[str] | None) -> list[str]:
    normalized = []
    for item in extensions or DEFAULT_CODE_EXTENSIONS:
        value = item.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        if value not in normalized:
            normalized.append(value)
    return normalized or list(DEFAULT_CODE_EXTENSIONS)


def _normalize_source_roots(source_roots: list[str] | None) -> list[str]:
    normalized = []
    for item in source_roots or DEFAULT_SOURCE_ROOTS:
        value = item.replace("\\", "/").strip().strip("/")
        if value and value not in normalized:
            normalized.append(value)
    return normalized or list(DEFAULT_SOURCE_ROOTS)


def _resolve_project_root(project_root: str) -> Path:
    if not project_root or not str(project_root).strip():
        raise ProjectFileAccessError("project_root is required")
    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        raise ProjectFileAccessError(f"project_root_not_found: {root}")
    if not root.is_dir():
        raise ProjectFileAccessError(f"project_root_not_directory: {root}")
    return root


def _source_root_paths(project_root: Path, source_roots: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in source_roots:
        candidate = (project_root / item).resolve()
        if candidate.exists() and candidate.is_dir():
            paths.append(candidate)
    return paths


def _source_root_diagnostics(project_root: Path, source_roots: list[str]) -> tuple[list[Path], list[str], list[str]]:
    paths: list[Path] = []
    existing: list[str] = []
    missing: list[str] = []
    for item in source_roots:
        candidate = (project_root / item).resolve()
        if candidate.exists() and candidate.is_dir():
            paths.append(candidate)
            existing.append(item)
        else:
            missing.append(item)
    return paths, existing, missing


def _infer_module_name(relative_path: str) -> str:
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "source":
        return parts[1]
    if len(parts) >= 4 and parts[0].lower() == "plugins":
        lowered = [part.lower() for part in parts]
        if "source" in lowered:
            source_index = lowered.index("source")
            if len(parts) > source_index + 1:
                return parts[source_index + 1]
    return ""


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _ensure_allowed_file(file_path: Path, allowed_roots: list[Path]) -> None:
    if not any(_is_relative_to(file_path, root) for root in allowed_roots):
        raise ProjectFileAccessError(f"file_outside_allowed_source_roots: {file_path}")
    if not file_path.exists():
        raise ProjectFileAccessError(f"file_not_found: {file_path}")
    if not file_path.is_file():
        raise ProjectFileAccessError(f"path_not_file: {file_path}")


def list_project_code_files(
    *,
    project_root: str,
    source_roots: list[str] | None = None,
    extensions: list[str] | None = None,
    query: str | None = None,
    limit: int = DEFAULT_FILE_SCAN_LIMIT,
) -> dict[str, object]:
    resolved_root = _resolve_project_root(project_root)
    normalized_roots = _normalize_source_roots(source_roots)
    normalized_extensions = _normalize_extensions(extensions)
    query_lower = (query or "").strip().lower()
    max_items = max(1, min(limit, 5000))

    discovered: list[dict[str, object]] = []
    source_root_paths, existing_roots, missing_roots = _source_root_diagnostics(resolved_root, normalized_roots)
    candidate_file_count = 0
    extension_match_count = 0
    skipped_by_query = 0
    permission_error_count = 0
    root_errors: list[str] = []
    for source_root_path in source_root_paths:
        try:
            iterator = source_root_path.rglob("*")
            for file_path in iterator:
                try:
                    if not file_path.is_file():
                        continue
                    candidate_file_count += 1
                    if file_path.suffix.lower() not in normalized_extensions:
                        continue
                    extension_match_count += 1
                    relative_path = file_path.relative_to(resolved_root).as_posix()
                    module_name = _infer_module_name(relative_path)
                    query_targets = [relative_path.lower(), file_path.name.lower(), module_name.lower()]
                    if query_lower and not any(query_lower in target for target in query_targets):
                        skipped_by_query += 1
                        continue
                    size_bytes = file_path.stat().st_size
                    source_root = source_root_path.relative_to(resolved_root).as_posix()
                    discovered.append(
                        {
                            "relative_path": relative_path,
                            "file_path": relative_path,
                            "absolute_path": str(file_path),
                            "label": file_path.name,
                            "file_name": file_path.name,
                            "module_name": module_name,
                            "file_type": file_path.suffix.lower().lstrip("."),
                            "extension": file_path.suffix.lower(),
                            "size_bytes": size_bytes,
                            "source_root": source_root,
                        }
                    )
                except (OSError, PermissionError) as exc:
                    permission_error_count += 1
                    root_errors.append(f"{file_path}: {exc}")
        except (OSError, PermissionError) as exc:
            permission_error_count += 1
            root_errors.append(f"{source_root_path}: {exc}")

    discovered.sort(key=lambda item: str(item["relative_path"]))
    limited_items = discovered[:max_items]
    empty_reason = ""
    if not discovered:
        if not source_root_paths:
            empty_reason = "source_roots_not_found"
        elif query_lower and skipped_by_query:
            empty_reason = "query_filtered_empty"
        elif extension_match_count == 0:
            empty_reason = "no_matching_code_extensions"
        else:
            empty_reason = "no_code_files_found"
    return {
        "project_root": str(resolved_root),
        "source_roots": normalized_roots,
        "extensions": normalized_extensions,
        "query": query or "",
        "items": limited_items,
        "total_count": len(discovered),
        "returned_count": len(limited_items),
        "truncated": len(discovered) > len(limited_items),
        "scan_diagnostics": {
            "project_root": str(resolved_root),
            "requested_source_roots": normalized_roots,
            "existing_source_roots": existing_roots,
            "missing_source_roots": missing_roots,
            "query": query or "",
            "limit": max_items,
            "candidate_file_count": candidate_file_count,
            "extension_match_count": extension_match_count,
            "skipped_by_query": skipped_by_query,
            "permission_error_count": permission_error_count,
            "root_errors": root_errors[:8],
            "empty_reason": empty_reason,
        },
    }


def read_project_code_file(
    *,
    project_root: str,
    file_path: str,
    source_roots: list[str] | None = None,
    max_bytes: int = DEFAULT_READ_MAX_BYTES,
) -> dict[str, object]:
    resolved_root = _resolve_project_root(project_root)
    normalized_roots = _normalize_source_roots(source_roots)
    allowed_roots = _source_root_paths(resolved_root, normalized_roots)
    if not allowed_roots:
        raise ProjectFileAccessError("no_allowed_source_roots_found")

    requested_path = Path(file_path)
    candidate = requested_path.resolve() if requested_path.is_absolute() else (resolved_root / requested_path).resolve()
    _ensure_allowed_file(candidate, allowed_roots)

    size_bytes = candidate.stat().st_size
    if size_bytes > max_bytes:
        raise ProjectFileAccessError(
            f"file_too_large: {candidate.name} ({size_bytes} bytes > {max_bytes} bytes)"
        )

    text = candidate.read_text(encoding="utf-8", errors="ignore")
    relative_path = candidate.relative_to(resolved_root).as_posix()
    return {
        "project_root": str(resolved_root),
        "relative_path": relative_path,
        "file_path": relative_path,
        "absolute_path": str(candidate),
        "resolved_absolute_path": str(candidate),
        "file_name": candidate.name,
        "label": candidate.name,
        "module_name": _infer_module_name(relative_path),
        "file_type": candidate.suffix.lower().lstrip("."),
        "extension": candidate.suffix.lower(),
        "size_bytes": size_bytes,
        "content_length": len(text),
        "read_status": "ok",
        "text": text,
        "source_roots": normalized_roots,
    }
