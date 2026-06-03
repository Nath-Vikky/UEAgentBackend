from __future__ import annotations

from typing import Any

from app.services.editor_operations.catalog import (
    ASSET_NAME_RE,
    CLASS_NAME_RE,
    EditorOperationValidationError,
)


def normalize_asset_path(value: Any, *, require_game_root: bool = True) -> str:
    path = str(value or "").strip().replace("\\", "/")
    if path.endswith(".uasset"):
        path = path[: -len(".uasset")]
    if "." in path and path.startswith("/"):
        package_path, object_name = path.rsplit(".", 1)
        if object_name and package_path.endswith("/" + object_name):
            path = package_path
    if not path.startswith("/"):
        path = "/Game/" + path.lstrip("/")
    while "//" in path:
        path = path.replace("//", "/")
    if ".." in path.split("/"):
        raise EditorOperationValidationError("asset_path_contains_parent_traversal")
    if require_game_root and not (path == "/Game" or path.startswith("/Game/")):
        raise EditorOperationValidationError("asset_path_must_be_under_game", {"asset_path": path})
    if len(path) > 240:
        raise EditorOperationValidationError("asset_path_too_long", {"asset_path": path})
    return path


def normalize_folder(value: Any) -> str:
    folder = normalize_asset_path(value, require_game_root=True).rstrip("/")
    if "." in folder:
        raise EditorOperationValidationError("target_folder_must_not_be_object_path", {"target_folder": folder})
    return folder


def normalize_redirector_folder(value: Any) -> str:
    folder = normalize_folder(value)
    if folder == "/Game":
        raise EditorOperationValidationError(
            "redirector_folder_too_broad",
            {"folder_path": folder, "rule": "Use a bounded subfolder such as /Game/Blueprints."},
        )
    return folder


def normalize_asset_name(value: Any, field_name: str = "asset_name") -> str:
    name = str(value or "").strip()
    if not ASSET_NAME_RE.match(name):
        raise EditorOperationValidationError(
            f"{field_name}_invalid",
            {
                field_name: name,
                "rule": "Use 2-64 characters. Start with a letter. Only letters, numbers, and underscore are allowed.",
            },
        )
    return name


def normalize_class_path(value: Any) -> str:
    class_path = str(value or "").strip()
    if not class_path:
        raise EditorOperationValidationError("parent_class_required")
    if ".." in class_path or "\\" in class_path:
        raise EditorOperationValidationError("parent_class_invalid", {"parent_class": class_path})
    if len(class_path) > 180 or not CLASS_NAME_RE.match(class_path):
        raise EditorOperationValidationError("parent_class_invalid", {"parent_class": class_path})
    return class_path


def normalize_optional_string(value: Any, *, max_length: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise EditorOperationValidationError("text_field_too_long", {"max_length": max_length})
    return text


__all__ = [
    "normalize_asset_name",
    "normalize_asset_path",
    "normalize_class_path",
    "normalize_folder",
    "normalize_optional_string",
    "normalize_redirector_folder",
]
