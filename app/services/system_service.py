from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import CAPABILITIES, SUPPORTED_LANGUAGES, UI_RECOMMENDATIONS
from app.core.settings import Settings
from app.core.startup_checks import collect_startup_checks
from app.observability.redaction import redact_payload
from app.observability.telemetry import service_health_snapshot
from app.services.kb_service import KnowledgeBaseService
from app.services.runtime_profile_service import RuntimeProfileService


class SystemService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.runtime_profiles = RuntimeProfileService(db, settings)
        self.kb = KnowledgeBaseService(db, settings)

    def health(self) -> dict:
        database_status = "ok"
        database_error = None
        try:
            self.db.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - exercised in runtime only
            database_status = "error"
            database_error = str(exc)

        return {
            "service_status": "ok" if database_status == "ok" else "degraded",
            "version": self.settings.app_version,
            "environment": self.settings.app_env,
            "database": {
                "status": database_status,
                "url": redact_payload({"database_url": self.settings.database_url})["database_url"],
                "error": database_error,
            },
            "storage": {
                "storage_dir": str(Path(self.settings.storage_dir).resolve()),
                "upload_dir": str(Path(self.settings.upload_dir).resolve()),
                "artifact_dir": str(Path(self.settings.artifact_dir).resolve()),
            },
            "startup_checks": collect_startup_checks(
                self.settings,
                database_status=database_status,
                database_error=database_error,
            ),
            "observability": service_health_snapshot(),
        }

    def bootstrap(self) -> dict:
        profiles = self.runtime_profiles.list_payload()
        default_profile = next(
            (
                profile
                for profile in profiles["profiles"]
                if profile["profile_id"] == profiles["default_profile_id"]
            ),
            None,
        )
        return {
            "service_status": "ok",
            "version": self.settings.app_version,
            "capabilities": CAPABILITIES,
            "supported_languages": SUPPORTED_LANGUAGES,
            "default_profile": default_profile or {},
            "knowledge_base_summary": self.kb.status(),
            "ui_recommendations": UI_RECOMMENDATIONS,
        }

    def capabilities(self) -> dict:
        return CAPABILITIES

    def settings_snapshot(self) -> dict:
        payload = {
            "app": {
                "env": self.settings.app_env,
                "name": self.settings.app_name,
                "version": self.settings.app_version,
                "host": self.settings.app_host,
                "port": self.settings.app_port,
                "root_path": self.settings.app_root_path,
                "cors_origins": self.settings.app_cors_origins,
            },
            "models": {
                "chat_model": self.settings.chat_model,
                "embedding_model": self.settings.embedding_model,
                "embedding_enabled": self.settings.embedding_enabled,
            },
            "rag": {
                "rag_mode": self.settings.rag_mode,
                "rag_top_k": self.settings.rag_top_k,
                "rag_rerank_top_n": self.settings.rag_rerank_top_n,
                "rag_fallback_mode": self.settings.rag_fallback_mode,
                "qdrant_url": self.settings.qdrant_url,
                "qdrant_collection": self.settings.qdrant_collection,
            },
            "observability": {
                "langsmith_tracing": self.settings.langsmith_tracing,
                "langsmith_project": self.settings.langsmith_project,
                "debug_json_snapshot": self.settings.debug_json_snapshot,
                "metrics_endpoint": "/metrics",
                "alerts_endpoint": "/api/v1/system/alerts",
                "otel_mode": "local_stub",
            },
            "safety": {
                "default_task_cost_guard_usd": self.settings.default_profile_cost_guard_usd,
                "session_cost_guard_usd": self.settings.session_cost_guard_usd,
                "alert_error_rate_threshold": self.settings.alert_error_rate_threshold,
                "alert_p95_latency_ms": self.settings.alert_p95_latency_ms,
                "alert_hourly_cost_usd": self.settings.alert_hourly_cost_usd,
            },
            "storage": {
                "storage_dir": self.settings.storage_dir,
                "upload_dir": self.settings.upload_dir,
                "artifact_dir": self.settings.artifact_dir,
                "kb_dir": self.settings.kb_dir,
            },
        }
        return redact_payload(payload)
