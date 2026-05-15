from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.core.settings import Settings
from app.services.web_search_service import (
    WebSearchService,
    is_explicit_web_search_request,
    should_trigger_web_search,
)


def _runtime_root(name: str) -> Path:
    return Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"


def _write_mock_results(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "title": "Enhanced Input in Unreal Engine",
                        "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input-in-unreal-engine",
                        "snippet": "Enhanced Input lets projects map Input Actions and Mapping Contexts.",
                        "source_type": "official",
                    },
                    {
                        "title": "Forum answer",
                        "url": "https://forums.example.com/thread",
                        "snippet": "A community discussion about input.",
                    },
                    {
                        "title": "Unsafe local result",
                        "url": "http://127.0.0.1/private",
                        "snippet": "This must never be returned.",
                        "always_include": True,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_web_search_disabled_by_default() -> None:
    service = WebSearchService(Settings(_env_file=None))

    status = service.status()
    result = service.search(query="search official Unreal Engine Enhanced Input docs")

    assert status["enabled"] is False
    assert result["status"] == "skipped"
    assert result["reason"] == "disabled_by_settings"
    assert result["items"] == []


def test_mock_web_search_returns_allowed_public_results() -> None:
    runtime_root = _runtime_root("web-search")
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        mock_path = _write_mock_results(runtime_root / "web-results.json")
        service = WebSearchService(
            Settings(
                _env_file=None,
                web_search_enabled=True,
                web_search_provider="mock",
                web_search_mock_results_path=str(mock_path),
                web_search_allowed_domains=["dev.epicgames.com"],
                web_search_domain_boosts=["dev.epicgames.com:0.25"],
            )
        )

        result = service.search(query="Enhanced Input official docs", trigger_reason="explicit_user_request")
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    assert result["status"] == "completed"
    assert result["reason"] == "matched"
    assert result["items"][0]["domain"] == "dev.epicgames.com"
    assert result["items"][0]["source_type"] == "official"
    assert result["summary"]["skipped_domain_count"] == 1
    assert result["summary"]["queries_used"] == 1


def test_web_search_trigger_policy_prefers_explicit_or_low_evidence_ue_queries() -> None:
    runtime_root = _runtime_root("web-search-policy")
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        settings = Settings(
            _env_file=None,
            web_search_enabled=True,
            web_search_provider="mock",
            web_search_mock_results_path=str(_write_mock_results(runtime_root / "web-results.json")),
        )

        assert is_explicit_web_search_request("请联网查一下 UE 官方文档")
        assert should_trigger_web_search(
            query="普通闲聊不用搜索",
            evidence_sufficient=False,
            settings=settings,
            explicit=False,
        ) == (False, "not_ue_or_no_explicit_search")
        assert should_trigger_web_search(
            query="UE Enhanced Input 怎么配置",
            evidence_sufficient=False,
            settings=settings,
            explicit=False,
        ) == (True, "kb_evidence_insufficient_for_ue_topic")
        assert should_trigger_web_search(
            query="UE Enhanced Input 怎么配置",
            evidence_sufficient=True,
            settings=settings,
            explicit=False,
        ) == (False, "kb_evidence_sufficient")
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def test_brave_web_search_requires_api_key() -> None:
    service = WebSearchService(
        Settings(
            _env_file=None,
            web_search_enabled=True,
            web_search_provider="brave",
        )
    )

    status = service.status()
    result = service.search(query="Unreal Engine official docs", trigger_reason="manual_smoke")

    assert status["status"] == "degraded"
    assert status["reason"] == "api_key_missing"
    assert result["status"] == "error"
    assert result["reason"] == "api_key_missing"


def test_brave_web_search_maps_api_response(monkeypatch) -> None:
    service = WebSearchService(
        Settings(
            _env_file=None,
            web_search_enabled=True,
            web_search_provider="brave",
            web_search_api_key="test-key",
            web_search_allowed_domains=["dev.epicgames.com"],
            web_search_domain_boosts=["dev.epicgames.com:0.25"],
        )
    )

    def fake_request_json(**kwargs):
        assert kwargs["headers"]["X-Subscription-Token"] == "test-key"
        assert kwargs["params"]["q"] == "Enhanced Input official docs"
        return {
            "web": {
                "results": [
                    {
                        "title": "Enhanced Input in Unreal Engine",
                        "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input-in-unreal-engine",
                        "description": "Enhanced Input uses Input Actions and Mapping Contexts.",
                    },
                    {
                        "title": "Untrusted mirror",
                        "url": "https://example.com/unreal",
                        "description": "Should be skipped by allowed-domain policy.",
                    },
                ]
            }
        }

    monkeypatch.setattr(service, "_request_json", fake_request_json)

    result = service.search(query="Enhanced Input official docs", trigger_reason="manual_smoke")

    assert result["status"] == "completed"
    assert result["reason"] == "matched"
    assert result["provider"] == "brave"
    assert result["items"][0]["domain"] == "dev.epicgames.com"
    assert result["items"][0]["source_type"] == "official"
    assert result["summary"]["skipped_domain_count"] == 1
