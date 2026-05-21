from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.schemas.requests import ProjectInventorySnapshotRequest
from app.utils.time import utc_isoformat


def _slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    return "_".join(item for item in text.split("_") if item) or "default"


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _asset_name(asset_path: str) -> str:
    leaf = asset_path.rstrip("/").split("/")[-1]
    if "." in leaf:
        return leaf.rsplit(".", 1)[-1]
    return leaf


def _contains_text(value: Any, needle: str) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return needle in value.lower()
    if isinstance(value, dict):
        return any(_contains_text(key, needle) or _contains_text(item, needle) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_text(item, needle) for item in value)
    return needle in str(value).lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _normalize_symbols(value: Any) -> dict[str, Any] | list[Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


class ProjectInventoryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.inventory_path = Path(settings.storage_dir) / "project_inventory.json"

    def save_snapshot(self, request: ProjectInventorySnapshotRequest) -> dict[str, Any]:
        store = self._load_store()
        project_id = _slug(request.project_id or request.project_name or "default")
        created_at = request.snapshot_time or utc_isoformat()
        snapshot_id = request.snapshot_id or f"{project_id}_{created_at.replace(':', '').replace('.', '_')}"
        previous = self._latest_project_snapshot(store, project_id) if request.mode == "incremental" else None
        assets = self._merge_by_id(previous.get("assets", []) if previous else [], self._normalize_assets(request.assets))
        code_files = self._merge_by_id(
            previous.get("code_files", []) if previous else [],
            self._normalize_code_files(request.code_files),
        )
        level_actors = self._merge_by_id(
            previous.get("level_actors", []) if previous else [],
            self._normalize_level_actors(request.level_actors),
        )
        material_instances = self._merge_by_id(
            previous.get("material_instances", []) if previous else [],
            self._normalize_material_instances(request.material_instances),
        )
        summary = {
            "asset_count": len(assets),
            "code_file_count": len(code_files),
            "level_actor_count": len(level_actors),
            "material_instance_count": len(material_instances),
            "asset_type_counts": self._count_by(assets, "asset_type"),
            "code_file_type_counts": self._count_by(code_files, "file_type"),
            "level_actor_class_counts": self._count_by(level_actors, "actor_class"),
            "level_actor_level_counts": self._count_by(level_actors, "level_name"),
            "material_instance_parent_counts": self._count_by(material_instances, "parent_material"),
            "material_parameter_count": sum(int(item.get("parameter_count") or 0) for item in material_instances),
            "blueprint_count": sum(1 for item in assets if self._is_blueprint_asset(item)),
            "static_mesh_count": sum(1 for item in assets if str(item.get("asset_type") or "") == "StaticMesh"),
            "map_count": sum(1 for item in assets if str(item.get("asset_type") or "") in {"World", "Map"}),
            "blueprint_parent_class_counts": self._count_blueprint_parent_classes(assets),
        }
        snapshot = {
            "status": "saved",
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "project_name": request.project_name or request.project_id or "default",
            "mode": request.mode,
            "source": request.source,
            "plugin_version": request.plugin_version,
            "created_at": created_at,
            "asset_count": len(assets),
            "code_file_count": len(code_files),
            "level_actor_count": len(level_actors),
            "material_instance_count": len(material_instances),
            "summary": summary,
            "assets": assets,
            "code_files": code_files,
            "level_actors": level_actors,
            "material_instances": material_instances,
            "scan_diagnostics": request.scan_diagnostics,
            "metadata": request.metadata,
        }
        store["snapshots"][snapshot_id] = snapshot
        store["latest_by_project"][project_id] = snapshot_id
        store["latest_snapshot_id"] = snapshot_id
        self._save_store(store)
        return {
            key: value
            for key, value in snapshot.items()
            if key not in {"assets", "code_files", "level_actors", "material_instances"}
        }

    def summary(self, project_id: str | None = None) -> dict[str, Any]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return {
                "has_snapshot": False,
                "asset_count": 0,
                "code_file_count": 0,
                "level_actor_count": 0,
                "material_instance_count": 0,
                "asset_type_counts": {},
                "code_file_type_counts": {},
                "level_actor_class_counts": {},
                "level_actor_level_counts": {},
                "material_instance_parent_counts": {},
                "material_parameter_count": 0,
            }
        assets = list(snapshot.get("assets") or [])
        code_files = list(snapshot.get("code_files") or [])
        level_actors = list(snapshot.get("level_actors") or [])
        material_instances = list(snapshot.get("material_instances") or [])
        asset_type_counts = self._count_by(assets, "asset_type")
        code_file_type_counts = self._count_by(code_files, "file_type")
        return {
            "has_snapshot": True,
            "snapshot_id": snapshot["snapshot_id"],
            "project_id": snapshot["project_id"],
            "project_name": snapshot["project_name"],
            "created_at": snapshot["created_at"],
            "asset_count": len(assets),
            "code_file_count": len(code_files),
            "level_actor_count": len(level_actors),
            "material_instance_count": len(material_instances),
            "asset_type_counts": asset_type_counts,
            "code_file_type_counts": code_file_type_counts,
            "level_actor_class_counts": self._count_by(level_actors, "actor_class"),
            "level_actor_level_counts": self._count_by(level_actors, "level_name"),
            "material_instance_parent_counts": self._count_by(material_instances, "parent_material"),
            "material_parameter_count": sum(int(item.get("parameter_count") or 0) for item in material_instances),
            "blueprint_count": sum(1 for item in assets if self._is_blueprint_asset(item)),
            "static_mesh_count": sum(1 for item in assets if str(item.get("asset_type") or "") == "StaticMesh"),
            "map_count": sum(1 for item in assets if str(item.get("asset_type") or "") in {"World", "Map"}),
            "blueprint_parent_class_counts": self._count_blueprint_parent_classes(assets),
            "source": snapshot.get("source"),
            "plugin_version": snapshot.get("plugin_version"),
            "scan_diagnostics": snapshot.get("scan_diagnostics", {}),
        }

    def list_assets(
        self,
        *,
        project_id: str | None = None,
        asset_type: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return []
        items = list(snapshot["assets"])
        if asset_type:
            expected = asset_type.lower()
            items = [item for item in items if str(item.get("asset_type") or "").lower() == expected]
        if query:
            needle = query.lower()
            items = [item for item in items if self._asset_matches(item, needle)]
        return items[:limit]

    def get_asset(self, asset_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        normalized = asset_id.lower()
        for item in self.list_assets(project_id=project_id, limit=10000):
            if normalized in {
                str(item.get("asset_id") or "").lower(),
                str(item.get("asset_path") or "").lower(),
                str(item.get("asset_name") or "").lower(),
            }:
                return item
        return None

    def list_code_files(
        self,
        *,
        project_id: str | None = None,
        query: str | None = None,
        module_name: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return []
        items = list(snapshot["code_files"])
        if module_name:
            expected = module_name.lower()
            items = [item for item in items if str(item.get("module_name") or "").lower() == expected]
        if query:
            needle = query.lower()
            items = [item for item in items if _contains_text(item, needle)]
        return items[:limit]

    def list_level_actors(
        self,
        *,
        project_id: str | None = None,
        query: str | None = None,
        level_name: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return []
        items = list(snapshot.get("level_actors") or [])
        if level_name:
            expected = level_name.lower()
            items = [item for item in items if str(item.get("level_name") or "").lower() == expected]
        if query:
            needle = query.lower()
            items = [item for item in items if self._level_actor_matches(item, needle)]
        return items[:limit]

    def list_material_instances(
        self,
        *,
        project_id: str | None = None,
        query: str | None = None,
        parent_material: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return []
        items = list(snapshot.get("material_instances") or [])
        if parent_material:
            expected = parent_material.lower()
            items = [item for item in items if str(item.get("parent_material") or "").lower() == expected]
        if query:
            needle = query.lower()
            items = [item for item in items if self._material_instance_matches(item, needle)]
        return items[:limit]

    def query(
        self,
        *,
        query: str,
        project_id: str | None = None,
        asset_path: str | None = None,
        asset_type: str | None = None,
        fields: list[str] | None = None,
        selected_assets: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        needle = query.lower().strip()
        inferred_type = asset_type or self._infer_asset_type(needle)
        is_code_query = self._looks_like_code_query(needle)
        is_level_actor_query = self._looks_like_level_actor_query(needle)
        is_material_instance_query = self._looks_like_material_instance_query(needle)
        is_asset_query = inferred_type is not None or self._mentions_asset_domain(needle)
        requested_fields = self._normalize_requested_fields(fields or self._infer_requested_fields(needle))
        assets: list[dict[str, Any]] = []
        if (not is_code_query or is_asset_query) and not is_level_actor_query:
            if asset_path:
                asset = self.get_asset(asset_path, project_id)
                assets = [asset] if asset else []
            if not assets and selected_assets and self._looks_like_selected_asset_query(needle):
                selected_matches = [
                    item
                    for asset in selected_assets
                    if (item := self.get_asset(asset, project_id)) is not None
                ]
                assets = selected_matches[:limit]
            if not assets and "nanite" in needle:
                assets = [
                    item
                    for item in self.list_assets(project_id=project_id, asset_type="StaticMesh", limit=10000)
                    if self._matches_nanite_query(item, needle)
                ][:limit]
            if not assets and query.strip():
                referenced_candidates = self.list_assets(project_id=project_id, asset_type=inferred_type, limit=10000)
                assets = [
                    item for item in referenced_candidates if self._asset_referenced_by_query(item, needle)
                ][:limit]
            if not assets and self._looks_like_asset_listing(needle):
                assets = self.list_assets(project_id=project_id, asset_type=inferred_type, limit=limit)
            if not assets and query.strip():
                assets = self.list_assets(project_id=project_id, asset_type=inferred_type, query=query, limit=limit)
            if not assets and query.strip():
                query_terms = self._query_terms(needle, inferred_type)
                candidates = self.list_assets(project_id=project_id, asset_type=inferred_type, limit=10000)
                assets = [
                    item
                    for item in candidates
                    if self._asset_referenced_by_query(item, needle)
                    or any(self._asset_matches(item, term) for term in query_terms)
                ][:limit]
        code_files = []
        if is_code_query:
            listing_query = self._looks_like_asset_listing(needle)
            code_files = (
                []
                if listing_query
                else self.list_code_files(project_id=project_id, query=query, limit=limit)
            )
            if not code_files and query.strip():
                code_candidates = self.list_code_files(project_id=project_id, limit=10000)
                code_files = [
                    item for item in code_candidates if self._code_file_referenced_by_query(item, needle)
                ][:limit]
            if not code_files and listing_query:
                code_files = self.list_code_files(project_id=project_id, limit=limit)
        level_actors: list[dict[str, Any]] = []
        if is_level_actor_query:
            level_actors = self.list_level_actors(project_id=project_id, query=query, limit=limit)
            if not level_actors and query.strip():
                query_terms = self._query_terms(needle, inferred_type)
                candidates = self.list_level_actors(project_id=project_id, limit=10000)
                level_actors = [
                    item
                    for item in candidates
                    if any(self._level_actor_matches(item, term) for term in query_terms)
                ][:limit]
            if not level_actors and self._looks_like_inventory_listing(needle):
                level_actors = self.list_level_actors(project_id=project_id, limit=limit)
        material_instances: list[dict[str, Any]] = []
        if is_material_instance_query:
            material_instances = self.list_material_instances(project_id=project_id, query=query, limit=limit)
            if not material_instances and query.strip():
                query_terms = self._query_terms(needle, inferred_type)
                candidates = self.list_material_instances(project_id=project_id, limit=10000)
                material_instances = [
                    item
                    for item in candidates
                    if any(self._material_instance_matches(item, term) for term in query_terms)
                ][:limit]
            if not material_instances and self._looks_like_inventory_listing(needle):
                material_instances = self.list_material_instances(project_id=project_id, limit=limit)
        summary = self.summary(project_id)
        empty_reason = ""
        if not summary.get("has_snapshot"):
            empty_reason = "no_project_inventory_snapshot"
        elif not assets and not code_files and not level_actors and not material_instances:
            empty_reason = "no_matching_inventory_items"
        items = [self._inventory_asset_result_item(item, requested_fields) for item in assets]
        items.extend(
            self._inventory_code_result_item(item, requested_fields)
            for item in code_files
        )
        items.extend(
            self._inventory_level_actor_result_item(item, requested_fields)
            for item in level_actors
        )
        items.extend(
            self._inventory_material_instance_result_item(item, requested_fields)
            for item in material_instances
        )
        return {
            "items": items[:limit],
            "summary": {
                **summary,
                "query": query,
                "inferred_asset_type": inferred_type,
                "asset_match_count": len(assets),
                "code_file_match_count": len(code_files),
                "level_actor_match_count": len(level_actors),
                "material_instance_match_count": len(material_instances),
                "empty_reason": empty_reason,
                "requested_asset_path": asset_path or "",
                "requested_fields": requested_fields,
                "field_view_available": bool(requested_fields),
                "selected_asset_context_used": bool(
                    selected_assets and self._looks_like_selected_asset_query(needle) and assets
                ),
            },
        }

    def context_snapshot(
        self,
        *,
        project_id: str | None = None,
        selected_assets: list[str] | None = None,
        current_file: str | None = None,
        limit: int = 6,
    ) -> dict[str, Any]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return {
                "status": "missing_snapshot",
                "has_snapshot": False,
                "summary": self.summary(project_id),
                "selected_assets": [],
                "current_file": None,
                "top_assets": [],
                "top_code_files": [],
                "top_level_actors": [],
                "top_material_instances": [],
            }

        selected_items = []
        for asset in selected_assets or []:
            item = self.get_asset(asset, project_id)
            if item:
                selected_items.append(self._compact_asset(item))
        current_file_item = None
        if current_file:
            for item in self.list_code_files(project_id=project_id, limit=10000):
                if self._code_file_referenced_by_query(item, current_file.lower()):
                    current_file_item = self._compact_code_file(item)
                    break

        return {
            "status": "available",
            "has_snapshot": True,
            "snapshot_id": snapshot.get("snapshot_id"),
            "project_id": snapshot.get("project_id"),
            "project_name": snapshot.get("project_name"),
            "created_at": snapshot.get("created_at"),
            "summary": self.summary(project_id),
            "selected_assets": selected_items[:limit],
            "current_file": current_file_item,
            "top_assets": [self._compact_asset(item) for item in list(snapshot.get("assets") or [])[:limit]],
            "top_code_files": [self._compact_code_file(item) for item in list(snapshot.get("code_files") or [])[:limit]],
            "top_level_actors": [
                self._compact_level_actor(item) for item in list(snapshot.get("level_actors") or [])[:limit]
            ],
            "top_material_instances": [
                self._compact_material_instance(item)
                for item in list(snapshot.get("material_instances") or [])[:limit]
            ],
        }

    def _normalize_assets(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in assets:
            if not isinstance(raw, dict):
                continue
            asset_path = str(raw.get("asset_path") or raw.get("path") or "").strip()
            if not asset_path:
                continue
            asset_name = str(raw.get("asset_name") or raw.get("name") or _asset_name(asset_path)).strip()
            asset_type = str(raw.get("asset_type") or raw.get("type") or "Unknown").strip() or "Unknown"
            properties = _as_dict(raw.get("properties"))
            settings = _as_dict(raw.get("settings"))
            metadata = _as_dict(raw.get("metadata"))
            blueprint = _as_dict(
                _first_present(
                    raw.get("blueprint"),
                    raw.get("blueprint_summary"),
                    properties.get("blueprint"),
                    metadata.get("blueprint"),
                )
            )
            components = _as_list(
                _first_present(
                    raw.get("components"),
                    blueprint.get("components"),
                    properties.get("components"),
                    settings.get("components"),
                )
            )
            variables = _as_list(
                _first_present(raw.get("variables"), blueprint.get("variables"), properties.get("variables"))
            )
            functions = _as_list(
                _first_present(raw.get("functions"), blueprint.get("functions"), properties.get("functions"))
            )
            graphs = _as_list(_first_present(raw.get("graphs"), blueprint.get("graphs"), properties.get("graphs")))
            interfaces = _as_list(
                _first_present(raw.get("interfaces"), blueprint.get("interfaces"), properties.get("interfaces"))
            )
            editor_flags = _as_dict(
                _first_present(raw.get("editor_flags"), blueprint.get("editor_flags"), metadata.get("editor_flags"))
            )
            parent_class = str(
                _first_present(
                    raw.get("parent_class"),
                    blueprint.get("parent_class"),
                    settings.get("parent_class"),
                    properties.get("parent_class"),
                )
                or ""
            ).strip()
            native_class = str(
                _first_present(
                    raw.get("native_class"),
                    raw.get("class_path"),
                    blueprint.get("native_class"),
                    blueprint.get("generated_class"),
                    properties.get("native_class"),
                )
                or ""
            ).strip()
            if blueprint or components or variables or functions or graphs or parent_class or native_class:
                blueprint = {
                    **blueprint,
                    "parent_class": parent_class or blueprint.get("parent_class"),
                    "native_class": native_class or blueprint.get("native_class"),
                    "components": components,
                    "variables": variables,
                    "functions": functions,
                    "graphs": graphs,
                    "interfaces": interfaces,
                    "editor_flags": editor_flags,
                }
            normalized.append(
                {
                    "asset_id": str(raw.get("asset_id") or _stable_id("asset", asset_path)).strip(),
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "package_path": str(raw.get("package_path") or "").strip(),
                    "dependencies": list(raw.get("dependencies") or []),
                    "referencers": list(raw.get("referencers") or []),
                    "tags": dict(raw.get("tags") or {}),
                    "properties": properties,
                    "settings": settings,
                    "metadata": metadata,
                    "blueprint": blueprint,
                    "components": components,
                    "variables": variables,
                    "functions": functions,
                    "graphs": graphs,
                    "interfaces": interfaces,
                    "editor_flags": editor_flags,
                    "parent_class": parent_class,
                    "native_class": native_class,
                }
            )
        return normalized

    def _normalize_code_files(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in files:
            if not isinstance(raw, dict):
                continue
            file_path = str(raw.get("file_path") or raw.get("relative_path") or raw.get("path") or "").strip()
            if not file_path:
                continue
            modified_at = str(raw.get("modified_at") or raw.get("last_modified") or "").strip()
            normalized.append(
                {
                    "file_id": str(raw.get("file_id") or _stable_id("code", file_path)).strip(),
                    "file_path": file_path,
                    "relative_path": str(raw.get("relative_path") or file_path).strip(),
                    "label": str(raw.get("label") or Path(file_path).name).strip(),
                    "module_name": str(raw.get("module_name") or "").strip(),
                    "file_type": str(raw.get("file_type") or Path(file_path).suffix.lstrip(".") or "text").strip(),
                    "language": str(raw.get("language") or "").strip(),
                    "size_bytes": int(raw.get("size_bytes") or 0),
                    "modified_at": modified_at,
                    "last_modified": modified_at,
                    "classes": list(raw.get("classes") or []),
                    "symbols": _normalize_symbols(raw.get("symbols")),
                    "metadata": dict(raw.get("metadata") or {}),
                }
            )
        return normalized

    def _normalize_level_actors(self, actors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in actors:
            if not isinstance(raw, dict):
                continue
            actor_label = str(raw.get("actor_label") or raw.get("label") or raw.get("name") or "").strip()
            actor_name = str(raw.get("actor_name") or raw.get("object_name") or actor_label).strip()
            actor_path = str(raw.get("actor_path") or raw.get("object_path") or raw.get("path") or "").strip()
            actor_class = str(raw.get("actor_class") or raw.get("class_path") or raw.get("class") or "").strip()
            if not any((actor_label, actor_name, actor_path, actor_class)):
                continue
            level_name = str(raw.get("level_name") or raw.get("map_name") or raw.get("level") or "").strip()
            merge_source = actor_path or "|".join([level_name, actor_label, actor_name, actor_class])
            normalized.append(
                {
                    "actor_id": str(raw.get("actor_id") or raw.get("id") or _stable_id("actor", merge_source)).strip(),
                    "actor_label": actor_label,
                    "actor_name": actor_name,
                    "actor_class": actor_class or "Unknown",
                    "actor_path": actor_path,
                    "level_name": level_name or "PersistentLevel",
                    "folder_path": str(raw.get("folder_path") or raw.get("folder") or "").strip(),
                    "blueprint_path": str(raw.get("blueprint_path") or raw.get("asset_path") or "").strip(),
                    "transform": _as_dict(raw.get("transform")),
                    "components": _as_list(raw.get("components")),
                    "tags": raw.get("tags") if isinstance(raw.get("tags"), (dict, list)) else {},
                    "mobility": str(raw.get("mobility") or "").strip(),
                    "hidden_in_game": raw.get("hidden_in_game"),
                    "selected": raw.get("selected"),
                    "properties": _as_dict(raw.get("properties")),
                    "metadata": _as_dict(raw.get("metadata")),
                }
            )
        return normalized

    def _normalize_material_instances(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            material_path = str(
                raw.get("material_instance_path") or raw.get("asset_path") or raw.get("path") or ""
            ).strip()
            material_name = str(raw.get("material_instance_name") or raw.get("asset_name") or raw.get("name") or "").strip()
            if not material_path and not material_name:
                continue
            parent_material = str(raw.get("parent_material") or raw.get("parent") or "").strip()
            scalar_parameters = _as_list(raw.get("scalar_parameters"))
            vector_parameters = _as_list(raw.get("vector_parameters"))
            texture_parameters = _as_list(raw.get("texture_parameters"))
            static_switch_parameters = _as_list(raw.get("static_switch_parameters"))
            parameters = _as_list(raw.get("parameters")) or self._flatten_material_parameters(
                scalar_parameters=scalar_parameters,
                vector_parameters=vector_parameters,
                texture_parameters=texture_parameters,
                static_switch_parameters=static_switch_parameters,
            )
            merge_source = material_path or material_name
            normalized.append(
                {
                    "material_instance_id": str(
                        raw.get("material_instance_id") or raw.get("id") or _stable_id("material", merge_source)
                    ).strip(),
                    "material_instance_path": material_path,
                    "material_instance_name": material_name or _asset_name(material_path),
                    "parent_material": parent_material or "Unknown",
                    "parameters": parameters,
                    "parameter_count": len(parameters),
                    "scalar_parameters": scalar_parameters,
                    "vector_parameters": vector_parameters,
                    "texture_parameters": texture_parameters,
                    "static_switch_parameters": static_switch_parameters,
                    "overrides": _as_dict(raw.get("overrides")),
                    "properties": _as_dict(raw.get("properties")),
                    "metadata": _as_dict(raw.get("metadata")),
                }
            )
        return normalized

    @staticmethod
    def _flatten_material_parameters(
        *,
        scalar_parameters: list[Any],
        vector_parameters: list[Any],
        texture_parameters: list[Any],
        static_switch_parameters: list[Any],
    ) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        for parameter_type, values in (
            ("scalar", scalar_parameters),
            ("vector", vector_parameters),
            ("texture", texture_parameters),
            ("static_switch", static_switch_parameters),
        ):
            for value in values:
                if isinstance(value, dict):
                    flattened.append({"parameter_type": parameter_type, **value})
                else:
                    flattened.append({"parameter_type": parameter_type, "name": str(value)})
        return flattened

    def _load_store(self) -> dict[str, Any]:
        if not self.inventory_path.exists():
            return {"latest_snapshot_id": None, "latest_by_project": {}, "snapshots": {}}
        try:
            data = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        except Exception:
            return {"latest_snapshot_id": None, "latest_by_project": {}, "snapshots": {}}
        if not isinstance(data, dict):
            return {"latest_snapshot_id": None, "latest_by_project": {}, "snapshots": {}}
        data.setdefault("latest_snapshot_id", None)
        data.setdefault("latest_by_project", {})
        data.setdefault("snapshots", {})
        return data

    def _save_store(self, store: dict[str, Any]) -> None:
        self.inventory_path.parent.mkdir(parents=True, exist_ok=True)
        self.inventory_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_snapshot(self, project_id: str | None = None) -> dict[str, Any] | None:
        store = self._load_store()
        snapshot_id = None
        if project_id:
            snapshot_id = store["latest_by_project"].get(_slug(project_id))
            if not snapshot_id:
                return None
        else:
            snapshot_id = store.get("latest_snapshot_id")
        snapshot = store["snapshots"].get(snapshot_id or "")
        return snapshot if isinstance(snapshot, dict) else None

    def _latest_project_snapshot(self, store: dict[str, Any], project_id: str) -> dict[str, Any] | None:
        snapshot_id = store["latest_by_project"].get(project_id)
        snapshot = store["snapshots"].get(snapshot_id or "")
        return snapshot if isinstance(snapshot, dict) else None

    def _merge_by_id(self, existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = {self._merge_key(item): item for item in existing}
        for item in incoming:
            key = self._merge_key(item)
            merged[key] = item
        return list(merged.values())

    @staticmethod
    def _merge_key(item: dict[str, Any]) -> str:
        for key in (
            "asset_id",
            "file_id",
            "actor_id",
            "material_instance_id",
            "asset_path",
            "file_path",
            "actor_path",
            "material_instance_path",
        ):
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return _stable_id("item", json.dumps(item, sort_keys=True, ensure_ascii=False))

    def _count_by(self, items: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            value = str(item.get(key) or "Unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _asset_matches(self, item: dict[str, Any], needle: str) -> bool:
        return any(
            _contains_text(item.get(key), needle)
            for key in (
                "asset_path",
                "asset_name",
                "asset_type",
                "package_path",
                "tags",
                "properties",
                "settings",
                "blueprint",
                "components",
                "variables",
                "functions",
                "graphs",
                "interfaces",
                "parent_class",
                "native_class",
            )
        )

    def _is_blueprint_asset(self, item: dict[str, Any]) -> bool:
        asset_type = str(item.get("asset_type") or "").lower()
        return asset_type in {"blueprint", "widgetblueprint", "animblueprint"} or bool(item.get("blueprint"))

    def _count_blueprint_parent_classes(self, assets: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in assets:
            if not self._is_blueprint_asset(item):
                continue
            parent_class = str(
                item.get("parent_class")
                or (_as_dict(item.get("blueprint")).get("parent_class"))
                or (_as_dict(item.get("settings")).get("parent_class"))
                or "Unknown"
            )
            counts[parent_class] = counts.get(parent_class, 0) + 1
        return counts

    def _compact_asset(self, item: dict[str, Any]) -> dict[str, Any]:
        settings = _as_dict(item.get("settings"))
        blueprint = _as_dict(item.get("blueprint"))
        return {
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "asset_type": item.get("asset_type"),
            "asset_path": item.get("asset_path"),
            "package_path": item.get("package_path"),
            "parent_class": item.get("parent_class") or blueprint.get("parent_class") or settings.get("parent_class"),
            "components": list(item.get("components") or blueprint.get("components") or [])[:12],
            "variables": list(item.get("variables") or blueprint.get("variables") or [])[:12],
            "functions": list(item.get("functions") or blueprint.get("functions") or [])[:12],
            "graphs": list(item.get("graphs") or blueprint.get("graphs") or [])[:8],
            "settings": {
                key: value
                for key, value in settings.items()
                if key
                in {
                    "nanite_enabled",
                    "lod_count",
                    "collision_complexity",
                    "parent_class",
                    "tick_enabled",
                    "blend_mode",
                    "srgb",
                    "lightmap_resolution",
                }
            },
            "dependency_count": len(item.get("dependencies") or []),
            "referencer_count": len(item.get("referencers") or []),
        }

    @staticmethod
    def _compact_code_file(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_id": item.get("file_id"),
            "file_path": item.get("file_path"),
            "module_name": item.get("module_name"),
            "file_type": item.get("file_type"),
            "language": item.get("language"),
            "classes": list(item.get("classes") or [])[:12],
            "size_bytes": item.get("size_bytes"),
            "modified_at": item.get("modified_at") or item.get("last_modified"),
        }

    @staticmethod
    def _compact_level_actor(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "actor_id": item.get("actor_id"),
            "actor_label": item.get("actor_label"),
            "actor_name": item.get("actor_name"),
            "actor_class": item.get("actor_class"),
            "actor_path": item.get("actor_path"),
            "level_name": item.get("level_name"),
            "folder_path": item.get("folder_path"),
            "blueprint_path": item.get("blueprint_path"),
            "transform": item.get("transform") or {},
            "component_count": len(item.get("components") or []),
            "mobility": item.get("mobility"),
        }

    @staticmethod
    def _compact_material_instance(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "material_instance_id": item.get("material_instance_id"),
            "material_instance_name": item.get("material_instance_name"),
            "material_instance_path": item.get("material_instance_path"),
            "parent_material": item.get("parent_material"),
            "parameter_count": item.get("parameter_count"),
            "scalar_parameter_count": len(item.get("scalar_parameters") or []),
            "vector_parameter_count": len(item.get("vector_parameters") or []),
            "texture_parameter_count": len(item.get("texture_parameters") or []),
            "static_switch_parameter_count": len(item.get("static_switch_parameters") or []),
        }

    def _inventory_asset_result_item(
        self,
        item: dict[str, Any],
        requested_fields: list[str],
    ) -> dict[str, Any]:
        result = {"kind": "asset", "score_reason": "asset_inventory_match", **item}
        if requested_fields:
            result["field_view"] = self._asset_field_view(item, requested_fields)
        return result

    def _inventory_code_result_item(
        self,
        item: dict[str, Any],
        requested_fields: list[str],
    ) -> dict[str, Any]:
        result = {"kind": "code_file", "score_reason": "code_inventory_match", **item}
        if requested_fields:
            result["field_view"] = self._code_file_field_view(item, requested_fields)
        return result

    def _inventory_level_actor_result_item(
        self,
        item: dict[str, Any],
        requested_fields: list[str],
    ) -> dict[str, Any]:
        result = {"kind": "level_actor", "score_reason": "level_actor_inventory_match", **item}
        if requested_fields:
            result["field_view"] = self._generic_field_view(item, requested_fields)
        return result

    def _inventory_material_instance_result_item(
        self,
        item: dict[str, Any],
        requested_fields: list[str],
    ) -> dict[str, Any]:
        result = {
            "kind": "material_instance",
            "score_reason": "material_instance_inventory_match",
            **item,
        }
        if requested_fields:
            result["field_view"] = self._generic_field_view(item, requested_fields)
        return result

    def _asset_field_view(self, item: dict[str, Any], requested_fields: list[str]) -> dict[str, Any]:
        blueprint = _as_dict(item.get("blueprint"))
        settings = _as_dict(item.get("settings"))
        properties = _as_dict(item.get("properties"))
        metadata = _as_dict(item.get("metadata"))
        direct_sources = (item, blueprint, settings, properties, metadata)
        derived = {
            "parent_class": item.get("parent_class") or blueprint.get("parent_class") or settings.get("parent_class"),
            "native_class": item.get("native_class") or blueprint.get("native_class"),
            "components": item.get("components") or blueprint.get("components") or [],
            "variables": item.get("variables") or blueprint.get("variables") or [],
            "functions": item.get("functions") or blueprint.get("functions") or [],
            "graphs": item.get("graphs") or blueprint.get("graphs") or [],
            "interfaces": item.get("interfaces") or blueprint.get("interfaces") or [],
            "dependencies": item.get("dependencies") or [],
            "referencers": item.get("referencers") or [],
        }
        view: dict[str, Any] = {}
        for field in requested_fields:
            if field in derived:
                view[field] = derived[field]
                continue
            for source in direct_sources:
                if field in source:
                    view[field] = source.get(field)
                    break
        return view

    @staticmethod
    def _code_file_field_view(item: dict[str, Any], requested_fields: list[str]) -> dict[str, Any]:
        allowed = {
            "file_path",
            "relative_path",
            "label",
            "module_name",
            "file_type",
            "language",
            "size_bytes",
            "modified_at",
            "last_modified",
            "classes",
            "symbols",
            "metadata",
        }
        return {field: item.get(field) for field in requested_fields if field in allowed}

    @staticmethod
    def _generic_field_view(item: dict[str, Any], requested_fields: list[str]) -> dict[str, Any]:
        return {field: item.get(field) for field in requested_fields if field in item}

    def _asset_referenced_by_query(self, item: dict[str, Any], query: str) -> bool:
        candidates = [
            str(item.get("asset_name") or "").lower(),
            str(item.get("asset_path") or "").lower(),
            str(item.get("package_path") or "").lower(),
        ]
        for value in candidates:
            if not value:
                continue
            leaf = value.rstrip("/").rsplit("/", 1)[-1].split(".", 1)[0]
            if value in query or (leaf and leaf in query):
                return True
        return False

    def _code_file_referenced_by_query(self, item: dict[str, Any], query: str) -> bool:
        candidates = [
            str(item.get("file_path") or "").lower(),
            str(item.get("relative_path") or "").lower(),
            str(item.get("label") or "").lower(),
            str(item.get("module_name") or "").lower(),
        ]
        for value in candidates:
            if not value:
                continue
            leaf = value.rstrip("/").rsplit("/", 1)[-1]
            stem = leaf.rsplit(".", 1)[0]
            if value in query or leaf in query or (stem and stem in query):
                return True
        return False

    def _level_actor_matches(self, item: dict[str, Any], needle: str) -> bool:
        return any(
            _contains_text(item.get(key), needle)
            for key in (
                "actor_label",
                "actor_name",
                "actor_class",
                "actor_path",
                "level_name",
                "folder_path",
                "blueprint_path",
                "components",
                "tags",
                "transform",
                "properties",
                "metadata",
            )
        )

    def _material_instance_matches(self, item: dict[str, Any], needle: str) -> bool:
        return any(
            _contains_text(item.get(key), needle)
            for key in (
                "material_instance_path",
                "material_instance_name",
                "parent_material",
                "parameters",
                "scalar_parameters",
                "vector_parameters",
                "texture_parameters",
                "static_switch_parameters",
                "overrides",
                "properties",
                "metadata",
            )
        )

    def _infer_asset_type(self, query: str) -> str | None:
        mapping = {
            "staticmesh": "StaticMesh",
            "static mesh": "StaticMesh",
            "静态网格": "StaticMesh",
            "nanite": "StaticMesh",
            "skeletal": "SkeletalMesh",
            "骨骼网格": "SkeletalMesh",
            "blueprint": "Blueprint",
            "蓝图": "Blueprint",
            "material instance": "MaterialInstanceConstant",
            "materialinstance": "MaterialInstanceConstant",
            "mi_": "MaterialInstanceConstant",
            "material": "Material",
            "材质": "Material",
            "texture": "Texture",
            "贴图": "Texture",
            "map": "World",
            "地图": "World",
            "niagara": "NiagaraSystem",
            "粒子": "NiagaraSystem",
            "sound": "SoundCue",
            "声音": "SoundCue",
            "data table": "DataTable",
            "数据表": "DataTable",
        }
        for token, asset_type in mapping.items():
            if token in query:
                return asset_type
        return None

    def _looks_like_code_query(self, query: str) -> bool:
        return any(
            token in query
            for token in ("cpp", ".cpp", ".h", "c++", "代码", "类", "class", "file", "module", "模块", "文件")
        )

    def _looks_like_asset_listing(self, query: str) -> bool:
        return any(
            token in query
            for token in (
                "asset",
                "assets",
                "list",
                "show",
                "which",
                "what",
                "资产",
                "有哪些",
                "哪些",
                "列出",
                "列一下",
                "列举",
                "列表",
                "查看",
                "查询",
                "settings",
                "属性",
                "设置",
            )
        )

    def _looks_like_inventory_listing(self, query: str) -> bool:
        return self._looks_like_asset_listing(query) or any(
            token in query
            for token in (
                "actor",
                "actors",
                "level actor",
                "level actors",
                "material instance",
                "material instances",
                "parameter",
                "parameters",
                "current level",
                "current scene",
                "level",
                "scene",
                "map",
                "有哪些",
                "哪些",
                "列出",
                "列表",
                "查看",
                "查询",
                "参数",
                "关卡",
                "场景",
            )
        )

    @staticmethod
    def _looks_like_level_actor_query(query: str) -> bool:
        actor_hint = any(
            token in query
            for token in (
                "actor",
                "actors",
                "pawn",
                "character",
                "bp_",
                "object",
                "objects",
                "placed object",
                "placed objects",
                "对象",
                "物体",
                "物件",
                "实例",
            )
        )
        level_hint = any(
            token in query
            for token in (
                "current level",
                "current scene",
                "level actor",
                "level actors",
                "in level",
                "in scene",
                "placed",
                "spawned",
                "关卡",
                "场景",
                "当前地图",
                "当前关卡",
                "当前场景",
                "关卡里",
                "关卡中",
                "场景里",
                "场景中",
                "地图里",
                "地图中",
                "摆放",
                "放置",
            )
        )
        listing_hint = any(
            token in query
            for token in (
                "list",
                "show",
                "which",
                "what",
                "how many",
                "有哪些",
                "有什么",
                "哪些",
                "列出",
                "列一下",
                "列举",
                "多少",
            )
        )
        return level_hint and (actor_hint or listing_hint)

    @staticmethod
    def _looks_like_material_instance_query(query: str) -> bool:
        material_hint = any(
            token in query
            for token in (
                "material",
                "materials",
                "material instance",
                "material instances",
                "mi_",
                "材质实例",
                "材质参数",
                "材质",
            )
        )
        parameter_hint = any(
            token in query
            for token in (
                "parameter",
                "parameters",
                "scalar",
                "vector",
                "texture",
                "static switch",
                "参数",
                "贴图",
                "开关",
                "roughness",
                "metallic",
                "base color",
                "basecolor",
                "albedo",
                "normal",
                "emissive",
                "opacity",
                "tint",
                "color",
                "value",
                "值",
                "颜色",
                "粗糙",
                "粗糙度",
                "金属",
                "金属度",
                "法线",
                "发光",
                "透明",
            )
        )
        return material_hint and (parameter_hint or "mi_" in query)

    def _looks_like_selected_asset_query(self, query: str) -> bool:
        return any(
            token in query
            for token in (
                "this asset",
                "that asset",
                "selected asset",
                "current asset",
                "asset details",
                "components",
                "variables",
                "functions",
                "graphs",
            )
        )

    def _mentions_asset_domain(self, query: str) -> bool:
        return any(
            token in query
            for token in (
                "asset",
                "assets",
                "blueprint",
                "staticmesh",
                "static mesh",
                "skeletalmesh",
                "skeletal mesh",
                "material",
                "texture",
                "mesh",
                "nanite",
                "lod",
                "资产",
                "蓝图",
                "静态网格",
                "骨骼网格",
                "材质",
                "贴图",
                "网格体",
            )
        )

    def _query_terms(self, query: str, inferred_asset_type: str | None) -> list[str]:
        separators = "，。！？、；：,.!?;:()[]{}<>|/\\\"'"
        normalized = query
        for char in separators:
            normalized = normalized.replace(char, " ")
        stopwords = {
            "current",
            "project",
            "this",
            "that",
            "assets",
            "asset",
            "actor",
            "actors",
            "level",
            "scene",
            "map",
            "material",
            "instance",
            "parameter",
            "parameters",
            "list",
            "show",
            "which",
            "what",
            "where",
            "please",
            "当前项目",
            "当前工程",
            "这个项目",
            "这个工程",
            "项目",
            "工程",
            "里面",
            "里",
            "中",
            "的",
            "有哪些",
            "哪些",
            "列出",
            "列一下",
            "列举",
            "一下",
            "资产",
            "设置",
            "属性",
            "关卡",
            "场景",
            "地图",
            "材质",
            "实例",
            "材质实例",
            "参数",
        }
        if inferred_asset_type:
            stopwords.add(inferred_asset_type.lower())
        raw_terms = [term.strip().lower() for term in normalized.split() if term.strip()]
        terms: list[str] = []
        for term in raw_terms:
            if term in stopwords or len(term) < 2:
                continue
            if term not in terms:
                terms.append(term)
        return terms[:8]

    def _infer_requested_fields(self, query: str) -> list[str]:
        field_hints = {
            "components": ("component", "组件"),
            "variables": ("variable", "变量"),
            "functions": ("function", "函数"),
            "graphs": ("graph", "图表", "蓝图图"),
            "interfaces": ("interface", "接口"),
            "parent_class": ("parent class", "parent_class", "父类"),
            "native_class": ("native class", "native_class", "原生类", "生成类"),
            "dependencies": ("dependency", "dependencies", "依赖", "引用了哪些"),
            "referencers": ("referencer", "referencers", "被谁引用", "引用者"),
            "nanite_enabled": ("nanite", "nanite_enabled"),
            "lod_count": ("lod", "lod_count"),
            "collision_complexity": ("collision", "碰撞", "collision_complexity"),
            "module_name": ("module", "模块"),
            "classes": ("class", "类"),
            "symbols": ("symbol", "符号"),
            "actor_class": ("actor class", "actor_class", "类型"),
            "actor_label": ("actor label", "actor_label", "label", "标签"),
            "transform": ("transform", "location", "rotation", "scale", "位置", "旋转", "缩放"),
            "level_name": ("level", "map", "关卡", "地图"),
            "folder_path": ("folder", "文件夹"),
            "parent_material": ("parent material", "parent_material", "父材质"),
            "parameters": ("parameter", "parameters", "参数"),
            "scalar_parameters": ("scalar", "roughness", "metallic", "标量", "粗糙", "金属"),
            "vector_parameters": ("vector", "color", "base color", "basecolor", "tint", "向量", "颜色"),
            "texture_parameters": ("texture", "albedo", "normal", "贴图", "法线"),
            "static_switch_parameters": ("static switch", "开关"),
        }
        fields: list[str] = []
        for field, hints in field_hints.items():
            if any(hint in query for hint in hints):
                fields.append(field)
        return fields

    @staticmethod
    def _normalize_requested_fields(fields: list[str]) -> list[str]:
        aliases = {
            "parent": "parent_class",
            "parentclass": "parent_class",
            "父类": "parent_class",
            "native": "native_class",
            "components": "components",
            "component": "components",
            "组件": "components",
            "variables": "variables",
            "variable": "variables",
            "变量": "variables",
            "functions": "functions",
            "function": "functions",
            "函数": "functions",
            "dependencies": "dependencies",
            "dependency": "dependencies",
            "依赖": "dependencies",
            "referencers": "referencers",
            "referencer": "referencers",
            "nanite": "nanite_enabled",
            "nanite_enabled": "nanite_enabled",
            "lod": "lod_count",
            "lod_count": "lod_count",
            "collision": "collision_complexity",
            "collision_complexity": "collision_complexity",
            "module": "module_name",
            "module_name": "module_name",
            "classes": "classes",
            "class": "classes",
            "symbols": "symbols",
            "symbol": "symbols",
            "actor_class": "actor_class",
            "actorclass": "actor_class",
            "actor_label": "actor_label",
            "actorlabel": "actor_label",
            "label": "actor_label",
            "transform": "transform",
            "location": "transform",
            "rotation": "transform",
            "scale": "transform",
            "level": "level_name",
            "map": "level_name",
            "level_name": "level_name",
            "folder": "folder_path",
            "folder_path": "folder_path",
            "parent_material": "parent_material",
            "parentmaterial": "parent_material",
            "parameters": "parameters",
            "parameter": "parameters",
            "scalar": "scalar_parameters",
            "scalar_parameters": "scalar_parameters",
            "vector": "vector_parameters",
            "vector_parameters": "vector_parameters",
            "texture": "texture_parameters",
            "texture_parameters": "texture_parameters",
            "static_switch": "static_switch_parameters",
            "static_switch_parameters": "static_switch_parameters",
        }
        normalized: list[str] = []
        for raw_field in fields:
            key = str(raw_field or "").strip().lower()
            if not key:
                continue
            field = aliases.get(key, key)
            if field not in normalized:
                normalized.append(field)
        return normalized[:12]

    def _matches_nanite_query(self, item: dict[str, Any], query: str) -> bool:
        settings = item.get("settings") if isinstance(item.get("settings"), dict) else {}
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        enabled_value = settings.get("nanite_enabled", properties.get("nanite_enabled"))
        if "开启" in query or "enabled" in query or "enable" in query:
            return enabled_value is True or str(enabled_value).lower() in {"true", "enabled", "1", "yes"}
        return _contains_text(settings, "nanite") or _contains_text(properties, "nanite")
