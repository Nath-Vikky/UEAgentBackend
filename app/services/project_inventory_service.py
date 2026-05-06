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
        summary = {
            "asset_count": len(assets),
            "code_file_count": len(code_files),
            "asset_type_counts": self._count_by(assets, "asset_type"),
            "code_file_type_counts": self._count_by(code_files, "file_type"),
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
            "summary": summary,
            "assets": assets,
            "code_files": code_files,
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
            if key not in {"assets", "code_files"}
        }

    def summary(self, project_id: str | None = None) -> dict[str, Any]:
        snapshot = self._resolve_snapshot(project_id)
        if not snapshot:
            return {
                "has_snapshot": False,
                "asset_count": 0,
                "code_file_count": 0,
                "asset_type_counts": {},
                "code_file_type_counts": {},
            }
        asset_type_counts = self._count_by(snapshot["assets"], "asset_type")
        code_file_type_counts = self._count_by(snapshot["code_files"], "file_type")
        return {
            "has_snapshot": True,
            "snapshot_id": snapshot["snapshot_id"],
            "project_id": snapshot["project_id"],
            "project_name": snapshot["project_name"],
            "created_at": snapshot["created_at"],
            "asset_count": len(snapshot["assets"]),
            "code_file_count": len(snapshot["code_files"]),
            "asset_type_counts": asset_type_counts,
            "code_file_type_counts": code_file_type_counts,
            "blueprint_count": sum(1 for item in snapshot["assets"] if self._is_blueprint_asset(item)),
            "static_mesh_count": sum(1 for item in snapshot["assets"] if str(item.get("asset_type") or "") == "StaticMesh"),
            "map_count": sum(1 for item in snapshot["assets"] if str(item.get("asset_type") or "") in {"World", "Map"}),
            "blueprint_parent_class_counts": self._count_blueprint_parent_classes(snapshot["assets"]),
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

    def query(
        self,
        *,
        query: str,
        project_id: str | None = None,
        asset_type: str | None = None,
        selected_assets: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        needle = query.lower().strip()
        inferred_type = asset_type or self._infer_asset_type(needle)
        is_code_query = self._looks_like_code_query(needle)
        is_asset_query = inferred_type is not None or self._mentions_asset_domain(needle)
        assets: list[dict[str, Any]] = []
        if not is_code_query or is_asset_query:
            if selected_assets and self._looks_like_selected_asset_query(needle):
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
        summary = self.summary(project_id)
        empty_reason = ""
        if not summary.get("has_snapshot"):
            empty_reason = "no_project_inventory_snapshot"
        elif not assets and not code_files:
            empty_reason = "no_matching_inventory_items"
        items = [
            {"kind": "asset", "score_reason": "asset_inventory_match", **item}
            for item in assets
        ]
        items.extend(
            {"kind": "code_file", "score_reason": "code_inventory_match", **item}
            for item in code_files
        )
        return {
            "items": items[:limit],
            "summary": {
                **summary,
                "query": query,
                "inferred_asset_type": inferred_type,
                "asset_match_count": len(assets),
                "code_file_match_count": len(code_files),
                "empty_reason": empty_reason,
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
            "top_assets": [self._compact_asset(item) for item in snapshot["assets"][:limit]],
            "top_code_files": [self._compact_code_file(item) for item in snapshot["code_files"][:limit]],
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
                    "symbols": dict(raw.get("symbols") or {}),
                    "metadata": dict(raw.get("metadata") or {}),
                }
            )
        return normalized

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
        merged = {str(item.get("asset_id") or item.get("file_id")): item for item in existing}
        for item in incoming:
            key = str(item.get("asset_id") or item.get("file_id"))
            merged[key] = item
        return list(merged.values())

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
            "list",
            "show",
            "which",
            "what",
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

    def _matches_nanite_query(self, item: dict[str, Any], query: str) -> bool:
        settings = item.get("settings") if isinstance(item.get("settings"), dict) else {}
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        enabled_value = settings.get("nanite_enabled", properties.get("nanite_enabled"))
        if "开启" in query or "enabled" in query or "enable" in query:
            return enabled_value is True or str(enabled_value).lower() in {"true", "enabled", "1", "yes"}
        return _contains_text(settings, "nanite") or _contains_text(properties, "nanite")
