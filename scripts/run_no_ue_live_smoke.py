from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


ENHANCED_INPUT_MARKERS = (
    "ACharacter",
    "UEnhancedInputComponent",
    "UInputAction",
    "UInputMappingContext",
    "BindAction",
    "AddMappingContext",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backend smoke checks without launching Unreal Editor."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/no-ue-live-smoke-latest.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Keep the configured OPENAI_API_KEY/runtime profile instead of forcing deterministic fallback.",
    )
    return parser.parse_args()


@contextmanager
def _isolated_runtime(*, live_llm: bool) -> Iterator[Path]:
    runtime_root = Path(".smoke-runtime") / f"no-ue-{uuid.uuid4().hex}"
    storage_dir = runtime_root / "storage"
    mock_path = runtime_root / "web-results.json"
    shutil.rmtree(runtime_root, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    mock_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "rank": 1,
                        "title": "Enhanced Input in Unreal Engine",
                        "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input",
                        "domain": "dev.epicgames.com",
                        "snippet": (
                            "Enhanced Input uses Input Actions, Mapping Contexts, "
                            "UEnhancedInputComponent, BindAction, and AddMappingContext."
                        ),
                        "source_type": "official",
                        "score": 0.92,
                        "provider": "mock",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    overrides = {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "STORAGE_DIR": str(storage_dir.resolve()),
        "UPLOAD_DIR": str((storage_dir / "uploads").resolve()),
        "ARTIFACT_DIR": str((storage_dir / "artifacts").resolve()),
        "KB_DIR": str((storage_dir / "kb").resolve()),
        "KB_SOURCE_PATHS": "./knowledge",
        "EMBEDDING_ENABLED": "false",
        "RAG_MODE": "lexical",
        "WEB_SEARCH_ENABLED": "true",
        "WEB_SEARCH_PROVIDER": "mock",
        "WEB_SEARCH_MOCK_RESULTS_PATH": str(mock_path.resolve()),
        "WEB_SEARCH_ALLOWED_DOMAINS": "dev.epicgames.com",
        "WEB_SEARCH_DOMAIN_BOOSTS": "dev.epicgames.com:0.25",
        "WEB_MEMORY_ENABLED": "false",
    }
    if not live_llm:
        overrides["OPENAI_API_KEY"] = ""

    previous = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        os.environ[key] = value
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    try:
        yield runtime_root
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        shutil.rmtree(runtime_root, ignore_errors=True)


def _post_code_generate(client: TestClient, *, query: str, index: int) -> dict[str, Any]:
    response = client.post(
        "/api/v1/tasks/code-generate",
        json={
            "task_type": "code_generate",
            "session": {
                "session_id": f"no_ue_codegen_{index}",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "RushBa",
                "active_panel": "CodeGenerator",
                "current_module": "RushBa",
            },
            "payload": {
                "user_query": query,
                "requirement_description": query,
                "target_type": "ue_cpp",
            },
            "ui_state": {"active_view": "user", "selected_panel": "CodeGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    data = body.get("data", {}) if isinstance(body, dict) else {}
    generated_items = data.get("generated_items") if isinstance(data.get("generated_items"), list) else []
    code_blob = "\n".join(str(item.get("code") or "") for item in generated_items if isinstance(item, dict))
    paths = [str(item.get("file_path") or "") for item in generated_items if isinstance(item, dict)]
    marker_hits = {marker: marker in code_blob for marker in ENHANCED_INPUT_MARKERS}
    return {
        "name": f"code_generate_enhanced_input_{index}",
        "ok": response.status_code == 200 and all(marker_hits.values()),
        "status_code": response.status_code,
        "query": query,
        "generation_mode": data.get("generation_mode"),
        "preflight_status": (data.get("preflight_report") or {}).get("status"),
        "paths": paths,
        "marker_hits": marker_hits,
        "warnings": data.get("warnings") or body.get("warnings") if isinstance(body, dict) else [],
    }


def _post_web_search_chat(client: TestClient) -> dict[str, Any]:
    query = "请联网查一下 UE Enhanced Input 官方文档"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "no_ue_web_search_chat",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "RushBa",
                "active_panel": "AgentChat",
            },
            "payload": {
                "user_query": query,
                "use_web_search": True,
                "disable_local_search": True,
                "web_search_max_results": 3,
            },
            "ui_state": {"active_view": "debug", "selected_panel": "AgentChat"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    data = body.get("data", {}) if isinstance(body, dict) else {}
    debug_view = body.get("debug_view", {}) if isinstance(body, dict) else {}
    web_search = data.get("web_search") or debug_view.get("web_search") or {}
    tools = debug_view.get("tools") if isinstance(debug_view.get("tools"), list) else []
    tool_called = any(item.get("tool_id") == "web_search_knowledge" for item in tools if isinstance(item, dict))
    return {
        "name": "agent_chat_web_search_tool",
        "ok": (
            response.status_code == 200
            and web_search.get("status") == "completed"
            and bool(web_search.get("items"))
            and tool_called
        ),
        "status_code": response.status_code,
        "route_type": (body.get("intent") or {}).get("route_type") if isinstance(body, dict) else None,
        "web_search_status": web_search.get("status"),
        "web_search_reason": web_search.get("reason"),
        "web_search_trigger_reason": web_search.get("trigger_reason"),
        "web_search_item_count": len(web_search.get("items") or []),
        "web_search_tool_called": tool_called,
        "assistant_excerpt": str((body.get("assistant_message") or "") if isinstance(body, dict) else "")[:240],
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime(live_llm=args.live_llm):
        with TestClient(create_app()) as client:
            checks = [
                _post_code_generate(
                    client,
                    query="角色增强输入代码怎么写",
                    index=1,
                ),
                _post_code_generate(
                    client,
                    query="角色输入增强的代码怎么写",
                    index=2,
                ),
                _post_web_search_chat(client),
            ]

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "live_llm" if args.live_llm else "deterministic_fallback_with_mock_web_search",
        "overall_ok": all(item["ok"] for item in checks),
        "checks": checks,
        "notes": [
            "This smoke test does not launch Unreal Editor.",
            "Default mode disables live LLM and uses a mock controlled Web Search provider.",
            "web_search_tool_called=true means the backend Project QA path invoked the Web Search tool trace.",
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
