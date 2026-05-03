from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.settings import Settings


MAX_MARKDOWN_PREVIEW_CHARS = 8000


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _detect_report_type(path: Path, content: dict[str, Any] | None = None) -> str:
    name = path.name.lower()
    content = content or {}
    if name.startswith("project-benchmark") or "rag_summary" in content or "task_summary" in content:
        return "project_benchmark"
    if name.startswith("rag-eval") or "rag" in name:
        return "rag_eval"
    if name.startswith("task-eval") or "task" in name:
        return "task_eval"
    return "unknown"


def _compact_summary(content: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if isinstance(content.get("summary"), dict):
        summary.update(content["summary"])
    if isinstance(content.get("rag_summary"), dict):
        summary["rag_summary"] = content["rag_summary"]
    if isinstance(content.get("task_summary"), dict):
        summary["task_summary"] = content["task_summary"]
    if isinstance(content.get("performance"), dict):
        summary["performance"] = content["performance"]
    if isinstance(content.get("knowledge_base"), dict):
        summary["knowledge_base"] = content["knowledge_base"]
    if "case_count" not in summary and isinstance(content.get("cases"), list):
        summary["case_count"] = len(content["cases"])
    if "datasets" in content:
        datasets = content["datasets"]
        summary["dataset_count"] = len(datasets) if isinstance(datasets, list) else 1
    return summary


class EvalReportService:
    """Read-only helper for local evaluation artifacts."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.evals_dir = Path(settings.artifact_dir).resolve() / "evals"

    def list_reports(self, limit: int = 20) -> dict[str, Any]:
        files = self._json_report_files()
        items = [self._build_report_card(path) for path in files[:limit]]
        return {
            "summary": {
                "evals_dir": str(self.evals_dir),
                "report_count": len(files),
                "returned_count": len(items),
                "latest_report_id": items[0]["report_id"] if items else None,
            },
            "items": items,
        }

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        path = self._resolve_report_path(report_id)
        if path is None or not path.exists():
            return None
        content = self._load_json(path)
        card = self._build_report_card(path, content)
        markdown_path = path.with_suffix(".md")
        markdown_preview = ""
        if markdown_path.exists():
            markdown_preview = markdown_path.read_text(encoding="utf-8", errors="replace")[
                :MAX_MARKDOWN_PREVIEW_CHARS
            ]
        return {
            "item": card,
            "report": content,
            "markdown_preview": markdown_preview,
        }

    def _json_report_files(self) -> list[Path]:
        if not self.evals_dir.exists():
            return []
        files = [path for path in self.evals_dir.glob("*.json") if path.is_file()]
        return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)

    def _resolve_report_path(self, report_id: str) -> Path | None:
        name = Path(report_id).name
        if name != report_id or not name.endswith(".json"):
            return None
        path = (self.evals_dir / name).resolve()
        try:
            path.relative_to(self.evals_dir)
        except ValueError:
            return None
        return path

    def _build_report_card(self, path: Path, content: dict[str, Any] | None = None) -> dict[str, Any]:
        content = content if content is not None else self._load_json(path)
        markdown_path = path.with_suffix(".md")
        return {
            "report_id": path.name,
            "report_type": _detect_report_type(path, content),
            "generated_at": content.get("generated_at"),
            "summary": _compact_summary(content),
            "json_path": str(path),
            "markdown_path": str(markdown_path) if markdown_path.exists() else "",
            "size_bytes": path.stat().st_size,
            "last_modified": _iso_from_mtime(path),
        }

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"parse_error": str(exc)}
        return data if isinstance(data, dict) else {"value": data}
