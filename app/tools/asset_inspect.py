from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.schemas.requests import ContextInput

TEMP_NAME_RE = re.compile(r"\b(?:newfolder|newblueprint|temp|test)\b", re.IGNORECASE)


def _asset_name(path: str) -> str:
    return path.rstrip("/").split("/")[-1]


def inspect_asset_metadata(payload: dict[str, Any], context: ContextInput) -> dict[str, Any]:
    asset_paths = list(payload.get("asset_paths") or context.selected_assets or [])
    project_prefix = f"/Game/{context.project_name}/" if context.project_name else "/Game/"

    violations: list[dict[str, Any]] = []
    rename_suggestions: list[dict[str, Any]] = []
    organization_suggestions: list[dict[str, Any]] = []
    groups: defaultdict[str, list[str]] = defaultdict(list)

    for asset_path in asset_paths:
        asset_name = _asset_name(asset_path)
        normalized = re.sub(r"[_\-\d]+", "", asset_name).lower()
        groups[normalized].append(asset_path)

        if " " in asset_name:
            violations.append(
                {
                    "asset_path": asset_path,
                    "rule_id": "asset_name_spaces",
                    "severity": "medium",
                    "message": "Asset names should not contain spaces.",
                }
            )
            rename_suggestions.append(
                {
                    "asset_path": asset_path,
                    "suggested_name": asset_name.replace(" ", ""),
                    "reason": "Remove spaces to align with UE asset naming conventions.",
                }
            )

        if TEMP_NAME_RE.search(asset_name):
            violations.append(
                {
                    "asset_path": asset_path,
                    "rule_id": "temporary_name",
                    "severity": "low",
                    "message": "Asset name looks temporary and should be finalized.",
                }
            )

        if not asset_path.startswith("/Game/"):
            violations.append(
                {
                    "asset_path": asset_path,
                    "rule_id": "content_root",
                    "severity": "medium",
                    "message": "Assets should resolve inside `/Game/` for project content.",
                }
            )

        if not asset_path.startswith(project_prefix):
            organization_suggestions.append(
                {
                    "asset_path": asset_path,
                    "suggested_directory": project_prefix,
                    "reason": "Consider grouping assets under the project-specific content root.",
                }
            )

        if asset_name and asset_name[0].islower():
            rename_suggestions.append(
                {
                    "asset_path": asset_path,
                    "suggested_name": asset_name[:1].upper() + asset_name[1:],
                    "reason": "Use a stable PascalCase-style asset name.",
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
                "rule_id": "duplicate_candidate",
                "severity": "low",
                "message": "Assets share a very similar normalized name and may be duplicates.",
            }
        )

    return {
        "violations": violations,
        "rename_suggestions": rename_suggestions[:8],
        "organization_suggestions": organization_suggestions[:8],
        "duplicate_candidates": duplicate_candidates,
        "summary": {
            "asset_count": len(asset_paths),
            "violation_count": len(violations),
            "rename_candidate_count": len(rename_suggestions),
            "organization_candidate_count": len(organization_suggestions),
        },
    }
