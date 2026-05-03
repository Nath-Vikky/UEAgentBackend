from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.observability.redaction import redact_payload
from app.services.mcp_tool_adapter import build_mcp_adapter_status
from app.tools.contracts import validate_tool_registry


def _check(
    *,
    check_id: str,
    title: str,
    status: str,
    severity: str,
    message: str,
    remediation: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "title": title,
        "status": status,
        "severity": severity,
        "message": message,
        "remediation": remediation,
        "details": details or {},
    }


def _path_status(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path)
    resolved = path.resolve()
    return {
        "path": raw_path,
        "resolved_path": str(resolved),
        "exists": resolved.exists(),
        "is_dir": resolved.is_dir(),
    }


def collect_startup_checks(
    settings: Settings,
    *,
    database_status: str = "unchecked",
    database_error: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    if settings.openai_api_key.strip():
        checks.append(
            _check(
                check_id="llm_api_key",
                title="LLM API Key",
                status="ok",
                severity="info",
                message="OPENAI_API_KEY is configured.",
                details=redact_payload({"openai_api_key": settings.openai_api_key}),
            )
        )
    else:
        checks.append(
            _check(
                check_id="llm_api_key",
                title="LLM API Key",
                status="warning",
                severity="warning",
                message="OPENAI_API_KEY is empty; LLM calls will use deterministic fallback paths.",
                remediation="Configure OPENAI_API_KEY, and optionally OPENAI_BASE_URL / CHAT_MODEL, before testing live LLM synthesis.",
            )
        )

    checks.append(
        _check(
            check_id="chat_model",
            title="Chat Model",
            status="ok" if settings.chat_model.strip() else "error",
            severity="info" if settings.chat_model.strip() else "error",
            message=(
                f"CHAT_MODEL is `{settings.chat_model}`."
                if settings.chat_model.strip()
                else "CHAT_MODEL is empty."
            ),
            remediation="Set CHAT_MODEL to an OpenAI-compatible chat model name." if not settings.chat_model.strip() else "",
        )
    )

    checks.append(
        _check(
            check_id="database",
            title="Database Connectivity",
            status="ok" if database_status == "ok" else database_status,
            severity="error" if database_status == "error" else "info",
            message=(
                "Database connectivity check passed."
                if database_status == "ok"
                else "Database connectivity has not been checked yet."
                if database_status == "unchecked"
                else f"Database connectivity check failed: {database_error}"
            ),
            remediation="Check DATABASE_URL and SQLite file permissions." if database_status == "error" else "",
            details=redact_payload({"database_url": settings.database_url, "error": database_error}),
        )
    )

    storage_paths = [
        _path_status(settings.storage_dir),
        _path_status(settings.upload_dir),
        _path_status(settings.artifact_dir),
        _path_status(settings.kb_dir),
    ]
    missing_storage = [item for item in storage_paths if not item["exists"] or not item["is_dir"]]
    checks.append(
        _check(
            check_id="storage_dirs",
            title="Storage Directories",
            status="ok" if not missing_storage else "warning",
            severity="info" if not missing_storage else "warning",
            message=(
                "Storage directories are present."
                if not missing_storage
                else "Some storage directories are missing; the app will try to create them during startup."
            ),
            remediation="Run the backend from the project root or create the configured storage directories." if missing_storage else "",
            details={"paths": storage_paths},
        )
    )

    kb_sources = [_path_status(path) for path in settings.kb_source_paths]
    missing_kb_sources = [item for item in kb_sources if not item["exists"] or not item["is_dir"]]
    checks.append(
        _check(
            check_id="kb_source_paths",
            title="Knowledge Source Paths",
            status="ok" if kb_sources and not missing_kb_sources else "warning",
            severity="info" if kb_sources and not missing_kb_sources else "warning",
            message=(
                "Knowledge source paths are present."
                if kb_sources and not missing_kb_sources
                else "One or more KB source paths are missing; local retrieval may have too little project knowledge."
            ),
            remediation="Set KB_SOURCE_PATHS to existing folders such as ./knowledge, or create the missing folders." if missing_kb_sources or not kb_sources else "",
            details={"paths": kb_sources},
        )
    )

    qdrant_configured = bool(settings.qdrant_url.strip())
    checks.append(
        _check(
            check_id="qdrant_config",
            title="Vector Store Configuration",
            status="ok" if not settings.embedding_enabled or qdrant_configured else "warning",
            severity="info" if not settings.embedding_enabled or qdrant_configured else "warning",
            message=(
                "Embedding is disabled; lexical retrieval fallback remains available."
                if not settings.embedding_enabled
                else f"Embedding is enabled and QDRANT_URL is `{settings.qdrant_url}`. Network reachability is not probed during startup."
                if qdrant_configured
                else "Embedding is enabled but QDRANT_URL is empty."
            ),
            remediation="Start Qdrant or set EMBEDDING_ENABLED=false when only using lexical retrieval." if settings.embedding_enabled else "",
            details=redact_payload(
                {
                    "embedding_enabled": settings.embedding_enabled,
                    "qdrant_url": settings.qdrant_url,
                    "qdrant_collection": settings.qdrant_collection,
                }
            ),
        )
    )

    tool_registry_report = validate_tool_registry()
    checks.append(
        _check(
            check_id="tool_registry_contracts",
            title="Tool Registry Contracts",
            status="ok" if tool_registry_report["ok"] else "error",
            severity="info" if tool_registry_report["ok"] else "error",
            message=(
                f"Tool registry contracts are valid for {tool_registry_report['tool_count']} tools."
                if tool_registry_report["ok"]
                else f"Tool registry has {tool_registry_report['issue_count']} contract issue(s)."
            ),
            remediation="Fix app/tools/registry.py schema, side-effect, or route metadata." if not tool_registry_report["ok"] else "",
            details=tool_registry_report,
        )
    )

    mcp_status = build_mcp_adapter_status(settings)
    mcp_check_status = (
        "ok"
        if mcp_status["status"] in {"disabled", "ready"}
        else "warning"
    )
    checks.append(
        _check(
            check_id="mcp_tool_adapter",
            title="MCP Tool Adapter",
            status=mcp_check_status,
            severity="info" if mcp_check_status == "ok" else "warning",
            message=(
                "MCP Tool Adapter is disabled; HTTP remains the primary UE frontend/backend protocol."
                if mcp_status["status"] == "disabled"
                else "MCP Tool Adapter is configured and ready for optional read-only tool transport."
                if mcp_status["status"] == "ready"
                else f"MCP Tool Adapter is enabled but not ready: {mcp_status['reason']}."
            ),
            remediation=(
                "Set MCP_TOOL_ADAPTER_ENABLED=false, or configure MCP_STDIO_COMMAND and MCP_ALLOWED_TOOLS."
                if mcp_check_status == "warning"
                else ""
            ),
            details=redact_payload(mcp_status),
        )
    )

    counts = {
        "ok": sum(1 for item in checks if item["status"] == "ok"),
        "warning": sum(1 for item in checks if item["status"] == "warning"),
        "error": sum(1 for item in checks if item["status"] == "error"),
        "unchecked": sum(1 for item in checks if item["status"] == "unchecked"),
    }
    return {
        "status": "error" if counts["error"] else "warning" if counts["warning"] else "ok",
        "blocking": counts["error"] > 0,
        "counts": counts,
        "checks": checks,
    }
