from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.schemas.requests import ContextInput

PLACEHOLDER_ASSET_NAMES = {
    "newmap",
    "untitled",
    "newblueprint",
    "newmaterial",
    "newtexture",
    "newdataasset",
}
TEMP_NAME_RE = re.compile(r"\b(?:newfolder|newblueprint|temp|test|placeholder)\b", re.IGNORECASE)
TYPE_PREFIX_HINTS = {
    "Blueprint": "BP_",
    "WidgetBlueprint": "WBP_",
    "Material": "M_",
    "MaterialInstance": "MI_",
    "Texture": "T_",
    "StaticMesh": "SM_",
    "SkeletalMesh": "SK_",
    "Animation": "AN_",
    "Sound": "S_",
    "World": "L_",
}
TYPE_PREFIX_ALIASES = {"World": ("L_", "Map_")}


def _asset_name(path: str) -> str:
    leaf = path.rstrip("/").split("/")[-1]
    if "." in leaf:
        return leaf.rsplit(".", 1)[-1]
    return leaf


def _asset_directory(path: str) -> str:
    parts = path.rstrip("/").split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else path


def _compact_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _placeholder_issue(asset_name: str) -> bool:
    compact = _compact_name(asset_name)
    return compact in PLACEHOLDER_ASSET_NAMES or bool(TEMP_NAME_RE.search(asset_name))


def _prefixes_for_type(asset_type: str) -> tuple[str, ...]:
    if asset_type in TYPE_PREFIX_ALIASES:
        return TYPE_PREFIX_ALIASES[asset_type]
    expected = TYPE_PREFIX_HINTS.get(asset_type)
    return (expected,) if expected else ()


def _placeholder_suggestion(asset_type: str) -> str:
    if asset_type == "World":
        return "L_ProjectSpecificName or Map_ProjectSpecificName"
    expected_prefix = TYPE_PREFIX_HINTS.get(asset_type, "")
    return f"{expected_prefix}ProjectSpecificName" if expected_prefix else "ProjectSpecificAssetName"


def _normalize_asset_items(payload: dict[str, Any], context: ContextInput) -> list[dict[str, Any]]:
    asset_items = payload.get("asset_items") or []
    if isinstance(asset_items, list) and asset_items:
        normalized: list[dict[str, Any]] = []
        for item in asset_items:
            if isinstance(item, str):
                normalized.append({"asset_path": item})
                continue
            if not isinstance(item, dict):
                continue
            asset_path = str(item.get("asset_path") or item.get("path") or "").strip()
            if not asset_path:
                continue
            asset_name = str(item.get("asset_name") or _asset_name(asset_path)).strip() or _asset_name(asset_path)
            normalized.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "asset_type": str(item.get("asset_type") or "Unknown").strip() or "Unknown",
                    "package_path": str(item.get("package_path") or _asset_directory(asset_path)).strip(),
                    "dependencies": list(item.get("dependencies") or []),
                    "referencers": list(item.get("referencers") or []),
                }
            )
        return normalized

    asset_paths = list(payload.get("asset_paths") or context.selected_assets or [])
    return [
        {
            "asset_path": item,
            "asset_name": _asset_name(item),
            "asset_type": "Unknown",
            "package_path": _asset_directory(item),
            "dependencies": [],
            "referencers": [],
        }
        for item in asset_paths
    ]


def _type_description(asset_type: str) -> str:
    descriptions = {
        "Blueprint": "Blueprint assets usually define gameplay objects or reusable logic wrappers.",
        "WidgetBlueprint": "Widget blueprints usually belong to UI flow or HUD composition.",
        "Material": "Materials define rendering behavior and usually feed instances or meshes.",
        "MaterialInstance": "Material instances inherit a parent material and override parameters.",
        "Texture": "Textures are content resources frequently consumed by materials or UI.",
        "StaticMesh": "Static meshes are geometric assets typically placed in levels or referenced by actors.",
        "SkeletalMesh": "Skeletal meshes usually pair with animation assets and character rigs.",
        "Animation": "Animation assets are often consumed by animation blueprints, montages, or characters.",
        "Sound": "Sound assets are commonly referenced by cues, UI events, or gameplay triggers.",
        "Unknown": "The backend did not receive a concrete asset type from the editor context.",
    }
    return descriptions.get(asset_type, f"{asset_type} is a project-specific asset type.")


def inspect_asset_metadata(payload: dict[str, Any], context: ContextInput) -> dict[str, Any]:
    asset_items = _normalize_asset_items(payload, context)
    asset_paths = [item["asset_path"] for item in asset_items]
    project_prefix = f"/Game/{context.project_name}/" if context.project_name else "/Game/"

    violations: list[dict[str, Any]] = []
    rename_suggestions: list[dict[str, Any]] = []
    organization_suggestions: list[dict[str, Any]] = []
    type_insights: list[dict[str, Any]] = []
    relationship_summary: list[dict[str, Any]] = []
    groups: defaultdict[str, list[str]] = defaultdict(list)

    total_dependency_edges = 0
    total_referencer_edges = 0

    for asset in asset_items:
        asset_path = str(asset["asset_path"])
        asset_name = str(asset.get("asset_name") or _asset_name(asset_path))
        asset_type = str(asset.get("asset_type") or "Unknown")
        dependencies = list(asset.get("dependencies") or [])
        referencers = list(asset.get("referencers") or [])
        package_path = str(asset.get("package_path") or _asset_directory(asset_path))

        total_dependency_edges += len(dependencies)
        total_referencer_edges += len(referencers)

        normalized = re.sub(r"[_\-\d]+", "", asset_name).lower()
        groups[normalized].append(asset_path)

        if " " in asset_name:
            violations.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "rule_id": "asset_name_spaces",
                    "severity": "medium",
                    "message": "Asset names should not contain spaces.",
                    "reason": "Spaces make UE asset references harder to scan and can create inconsistent naming.",
                    "suggestion": "Remove spaces and use a stable project naming style.",
                }
            )
            rename_suggestions.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "suggested_name": asset_name.replace(" ", ""),
                    "reason": "Remove spaces to align with UE asset naming conventions.",
                }
            )

        if _placeholder_issue(asset_name):
            suggested_name = _placeholder_suggestion(asset_type)
            violations.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "rule_id": "placeholder_asset_name",
                    "severity": "warning",
                    "message": f"Asset name `{asset_name}` looks like a default or placeholder name.",
                    "reason": f"Asset name uses the default placeholder name `{asset_name}`.",
                    "suggestion": f"Rename it to a project-specific name, for example {suggested_name}.",
                }
            )
            rename_suggestions.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "suggested_name": suggested_name,
                    "reason": "Default or placeholder asset names should be replaced before the asset becomes part of the project.",
                }
            )

        if not asset_path.startswith("/Game/"):
            violations.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "rule_id": "content_root",
                    "severity": "medium",
                    "message": "Assets should resolve inside `/Game/` for project content.",
                    "reason": "Project content assets should be rooted under `/Game/` for consistent packaging and references.",
                    "suggestion": "Move or reference the asset under the project content root.",
                }
            )

        if not asset_path.startswith(project_prefix):
            organization_suggestions.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "suggested_directory": project_prefix,
                    "reason": "Consider grouping assets under the project-specific content root.",
                }
            )

        if asset_name and asset_name[0].islower():
            rename_suggestions.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "suggested_name": asset_name[:1].upper() + asset_name[1:],
                    "reason": "Use a stable PascalCase-style asset name.",
                }
            )

        expected_prefixes = _prefixes_for_type(asset_type)
        if expected_prefixes and not asset_name.startswith(expected_prefixes):
            suggested_prefix = expected_prefixes[0]
            rename_suggestions.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "suggested_name": f"{suggested_prefix}{asset_name}",
                    "reason": (
                        f"{asset_type} assets often use one of these prefixes for quick scanning: "
                        f"{', '.join(expected_prefixes)}."
                    ),
                }
            )

        type_insights.append(
            {
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_type": asset_type,
                "package_path": package_path,
                "description": _type_description(asset_type),
            }
        )
        relationship_summary.append(
            {
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_type": asset_type,
                "dependency_count": len(dependencies),
                "referencer_count": len(referencers),
                "dependencies": dependencies[:8],
                "referencers": referencers[:8],
            }
        )

    duplicate_candidates = [
        {"normalized_name": key, "assets": value}
        for key, value in groups.items()
        if len(value) > 1
    ]
    for item in duplicate_candidates:
        violations.append(
            {
                "asset_path": ", ".join(item["assets"]),
                "asset_name": item["normalized_name"],
                "asset_type": "Unknown",
                "rule_id": "duplicate_candidate",
                "severity": "low",
                "message": "Assets share a very similar normalized name and may be duplicates.",
                "reason": "Normalized asset names collapse to the same value after removing separators and numeric suffixes.",
                "suggestion": "Confirm whether these are intentional variants or rename them with clearer semantic differences.",
            }
        )

    return {
        "violations": violations,
        "rename_suggestions": rename_suggestions[:8],
        "organization_suggestions": organization_suggestions[:8],
        "duplicate_candidates": duplicate_candidates,
        "type_insights": type_insights[:12],
        "relationship_summary": relationship_summary[:12],
        "summary": {
            "asset_count": len(asset_paths),
            "violation_count": len(violations),
            "rename_candidate_count": len(rename_suggestions),
            "organization_candidate_count": len(organization_suggestions),
            "dependency_edge_count": total_dependency_edges,
            "referencer_edge_count": total_referencer_edges,
        },
    }
