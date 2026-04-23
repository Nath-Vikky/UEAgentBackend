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
        limit: int = 20,
    ) -> dict[str, Any]:
        needle = query.lower().strip()
        inferred_type = asset_type or self._infer_asset_type(needle)
        assets = self.list_assets(project_id=project_id, asset_type=inferred_type, query=query, limit=limit)
        if not assets and "nanite" in needle:
            assets = [
                item
                for item in self.list_assets(project_id=project_id, asset_type="StaticMesh", limit=10000)
                if self._matches_nanite_query(item, needle)
            ][:limit]
        if not assets and self._looks_like_asset_listing(needle):
            assets = self.list_assets(project_id=project_id, asset_type=inferred_type, limit=limit)
        code_files = []
        if self._looks_like_code_query(needle):
            code_files = self.list_code_files(project_id=project_id, query=query, limit=limit)
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
                **self.summary(project_id),
                "query": query,
                "inferred_asset_type": inferred_type,
                "asset_match_count": len(assets),
                "code_file_match_count": len(code_files),
            },
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
                    "properties": dict(raw.get("properties") or {}),
                    "settings": dict(raw.get("settings") or {}),
                    "metadata": dict(raw.get("metadata") or {}),
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
        snapshot_id = snapshot_id or store.get("latest_snapshot_id")
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
            for key in ("asset_path", "asset_name", "asset_type", "package_path", "tags", "properties", "settings")
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
        return any(token in query for token in ("cpp", ".cpp", ".h", "c++", "代码", "类", "module", "模块"))

    def _looks_like_asset_listing(self, query: str) -> bool:
        return any(token in query for token in ("asset", "assets", "资产", "有哪些", "列表", "settings", "属性", "设置"))

    def _matches_nanite_query(self, item: dict[str, Any], query: str) -> bool:
        settings = item.get("settings") if isinstance(item.get("settings"), dict) else {}
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        enabled_value = settings.get("nanite_enabled", properties.get("nanite_enabled"))
        if "开启" in query or "enabled" in query or "enable" in query:
            return enabled_value is True or str(enabled_value).lower() in {"true", "enabled", "1", "yes"}
        return _contains_text(settings, "nanite") or _contains_text(properties, "nanite")
