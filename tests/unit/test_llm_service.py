from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.llm_service import ChatRuntimeConfig, LLMService


def _config() -> ChatRuntimeConfig:
    return ChatRuntimeConfig(
        profile_id="default",
        profile_name="Default",
        model="test-model",
        temperature=0.0,
        max_tokens=64,
        timeout_ms=1000,
    )


def _usage() -> dict[str, Any]:
    return {
        "input_tokens": 1,
        "output_tokens": 1,
        "estimated_cost_usd": 0.0,
        "latency_ms": 1,
    }


def test_classify_agent_chat_success_json(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": '{"route_type":"direct_answer","confidence":0.8,"reason":"casual question"}',
            "usage": _usage(),
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    result = LLMService(Settings(openai_api_key="test")).classify_agent_chat(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(),
    )

    assert result["ok"] is True
    assert result["route_type"] == "direct_answer"
    assert result["confidence"] == 0.8
    assert result["reason"] == "casual question"


def test_classify_agent_chat_invalid_json_returns_structured_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": "not json",
            "usage": _usage(),
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    result = LLMService(Settings(openai_api_key="test")).classify_agent_chat(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(),
    )

    assert result["ok"] is False
    assert result["route_type"] is None
    assert result["reason"] == "route_parse_failed"
    assert result["error"]


def test_classify_agent_chat_llm_failure_returns_structured_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": False,
            "reason": "request_failed",
            "error": "boom",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "usage": _usage(),
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    result = LLMService(Settings(openai_api_key="test")).classify_agent_chat(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(),
    )

    assert result["ok"] is False
    assert result["route_type"] is None
    assert result["reason"] == "request_failed"
    assert result["error"] == "boom"


def test_complete_json_object_accepts_common_llm_json_like_output(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": (
                "```json\n"
                "{summary: \"Review completed.\", "
                "issues: [{title: \"Load in Tick\", reason: \"Runs every frame.\"}], "
                "recommendations: [\"Move loading to BeginPlay\",],}\n"
                "```"
            ),
            "usage": _usage(),
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    result = LLMService(Settings(openai_api_key="test")).complete_json_object(
        messages=[{"role": "user", "content": "review"}],
        config=_config(),
    )

    assert result["ok"] is True
    assert result["payload"]["summary"] == "Review completed."
    assert result["payload"]["issues"][0]["title"] == "Load in Tick"
    assert result["payload"]["recommendations"] == ["Move loading to BeginPlay"]


def test_complete_json_object_accepts_python_style_dict_output(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": "{'summary': 'Looks clean', 'issues': [], 'recommendations': ['Add tests']}",
            "usage": _usage(),
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    result = LLMService(Settings(openai_api_key="test")).complete_json_object(
        messages=[{"role": "user", "content": "review"}],
        config=_config(),
    )

    assert result["ok"] is True
    assert result["payload"]["summary"] == "Looks clean"
    assert result["payload"]["recommendations"] == ["Add tests"]
