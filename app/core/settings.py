from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


StringListSetting = Annotated[list[str], NoDecode]


def _parse_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return []

    # Dotenv values are sometimes wrapped in quotes, e.g. '["http://localhost:3000"]'.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
        if not text:
            return []

    if text.startswith("[") and text.endswith("]"):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(decoded, list):
                return [str(item).strip() for item in decoded if str(item).strip()]

    return [item.strip().strip("'\"") for item in text.split(",") if item.strip().strip("'\"")]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    app_name: str = "UE Agent Backend"
    app_version: str = "0.1.0"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_root_path: str = ""
    app_cors_origins: StringListSetting = Field(default_factory=lambda: ["http://127.0.0.1"])
    log_level: str = "INFO"
    debug_json_snapshot: bool = True

    database_url: str = "sqlite:///./storage/app.db"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "ue_agent_default"

    openai_api_key: str = ""
    openai_base_url: str = ""
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-large"
    embedding_enabled: bool = False

    langsmith_tracing: bool = True
    langsmith_api_key: str = ""
    langsmith_project: str = "ue-agent-dev"

    rag_mode: str = "hybrid"
    rag_top_k: int = 8
    rag_rerank_top_n: int = 20
    rag_fallback_mode: str = "lexical_only"

    storage_dir: str = "./storage"
    upload_dir: str = "./storage/uploads"
    artifact_dir: str = "./storage/artifacts"
    kb_dir: str = "./storage/kb"
    kb_source_paths: StringListSetting = Field(default_factory=lambda: ["./knowledge"])
    kb_max_file_bytes: int = 5_000_000
    kb_chunk_size: int = 600
    kb_chunk_overlap: int = 100

    mcp_tool_adapter_enabled: bool = False
    mcp_stdio_command: str = ""
    mcp_stdio_args: StringListSetting = Field(default_factory=list)
    mcp_allowed_tools: StringListSetting = Field(default_factory=list)
    mcp_stdio_timeout_ms: int = 3000

    default_profile_id: str = "default"
    default_profile_name: str = "Default"
    default_profile_temperature: float = 0.2
    default_profile_max_tokens: int = 1200
    default_profile_allow_streaming: bool = True
    default_profile_debug_mode: bool = True
    default_profile_tool_timeout_ms: int = 30000
    default_profile_cost_guard_usd: float = 3.0
    session_cost_guard_usd: float = 10.0
    alert_error_rate_threshold: float = 0.2
    alert_p95_latency_ms: int = 2000
    alert_hourly_cost_usd: float = 5.0
    alert_rag_miss_rate: float = 0.4
    alert_kb_import_failure_rate: float = 0.2
    alert_pending_proposals_threshold: int = 5
    alert_pending_proposal_age_minutes: int = 60

    @field_validator("app_cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> list[str]:
        return _parse_string_list(value)

    @field_validator("kb_source_paths", mode="before")
    @classmethod
    def _parse_kb_source_paths(cls, value: Any) -> list[str]:
        return _parse_string_list(value)

    @field_validator("mcp_stdio_args", "mcp_allowed_tools", mode="before")
    @classmethod
    def _parse_mcp_string_lists(cls, value: Any) -> list[str]:
        return _parse_string_list(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
