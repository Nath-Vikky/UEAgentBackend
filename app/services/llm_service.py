from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.settings import Settings
from app.db.models.runtime_profile import RuntimeProfileModel
from app.observability.metrics import default_usage


@dataclass(frozen=True, slots=True)
class ChatRuntimeConfig:
    profile_id: str
    profile_name: str
    model: str
    temperature: float
    max_tokens: int
    timeout_ms: int


def chat_runtime_config(
    settings: Settings,
    profile: RuntimeProfileModel | None = None,
) -> ChatRuntimeConfig:
    if profile:
        return ChatRuntimeConfig(
            profile_id=profile.profile_id,
            profile_name=profile.name,
            model=profile.chat_model,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            timeout_ms=profile.tool_timeout_ms,
        )
    return ChatRuntimeConfig(
        profile_id=settings.default_profile_id,
        profile_name=settings.default_profile_name,
        model=settings.chat_model,
        temperature=settings.default_profile_temperature,
        max_tokens=settings.default_profile_max_tokens,
        timeout_ms=settings.default_profile_tool_timeout_ms,
    )


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    fragments.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                fragments.append(text_value.strip())
        return "\n".join(fragments).strip()
    return ""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
        if "```" in stripped:
            stripped = stripped.rsplit("```", 1)[0]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("json_object_not_found")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("json_object_expected")
    return payload


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def availability(self, config: ChatRuntimeConfig) -> tuple[bool, str]:
        if not self.settings.openai_api_key:
            return (False, "missing_openai_api_key")
        if not config.model:
            return (False, "missing_chat_model")
        return (True, "ready")

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        available, reason = self.availability(config)
        if not available:
            return {
                "ok": False,
                "provider": "openai_compatible",
                "reason": reason,
                "error": "",
                "model": config.model,
                "profile_id": config.profile_id,
                "usage": default_usage(),
            }

        url = self._chat_completions_url()
        request_payload = {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self._client_timeout(config)) as client:
                response = client.post(url, headers=headers, json=request_payload)
                response.raise_for_status()
            body = response.json()
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            text = _extract_text(message.get("content"))
            if not text:
                raise ValueError("empty_completion_text")

            usage_payload = body.get("usage") or {}
            return {
                "ok": True,
                "provider": "openai_compatible",
                "reason": "completed",
                "error": "",
                "model": body.get("model") or config.model,
                "profile_id": config.profile_id,
                "finish_reason": choice.get("finish_reason") or "completed",
                "endpoint": url,
                "text": text,
                "usage": {
                    "input_tokens": int(usage_payload.get("prompt_tokens") or 0),
                    "output_tokens": int(usage_payload.get("completion_tokens") or 0),
                    "estimated_cost_usd": 0.0,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
            }
        except Exception as exc:  # pragma: no cover - depends on live remote endpoint
            return {
                "ok": False,
                "provider": "openai_compatible",
                "reason": "request_failed",
                "error": str(exc),
                "model": config.model,
                "profile_id": config.profile_id,
                "usage": default_usage(),
            }

    def classify_agent_chat(
        self,
        *,
        messages: list[dict[str, str]],
        config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        llm_result = self.complete(messages=messages, config=config)
        if not llm_result["ok"]:
            return {
                "ok": False,
                "route_type": None,
                "confidence": 0.0,
                "reason": llm_result["reason"],
                "error": llm_result["error"],
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": llm_result["profile_id"],
                "usage": llm_result["usage"],
            }
        try:
            payload = _extract_json_object(llm_result["text"])
            route_type = str(payload.get("route_type") or "").strip()
            if route_type not in {"direct_answer", "project_qa"}:
                raise ValueError("unsupported_route_type")
            confidence = float(payload.get("confidence") or 0.0)
            return {
                "ok": True,
                "route_type": route_type,
                "confidence": max(0.0, min(confidence, 1.0)),
                "reason": str(payload.get("reason") or "").strip() or "llm_route_judge",
                "error": "",
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": llm_result["profile_id"],
                "usage": llm_result["usage"],
            }
        except Exception as exc:
            return {
                "ok": False,
                "route_type": None,
                "confidence": 0.0,
                "reason": "route_parse_failed",
                "error": str(exc),
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": llm_result["profile_id"],
                "usage": llm_result["usage"],
            }

    def complete_json_object(
        self,
        *,
        messages: list[dict[str, str]],
        config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        llm_result = self.complete(messages=messages, config=config)
        if not llm_result["ok"]:
            return {
                "ok": False,
                "payload": None,
                "reason": llm_result["reason"],
                "error": llm_result["error"],
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": llm_result["profile_id"],
                "usage": llm_result["usage"],
            }
        try:
            payload = _extract_json_object(llm_result["text"])
            return {
                "ok": True,
                "payload": payload,
                "reason": "completed",
                "error": "",
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": llm_result["profile_id"],
                "text": llm_result["text"],
                "usage": llm_result["usage"],
            }
        except Exception as exc:
            return {
                "ok": False,
                "payload": None,
                "reason": "json_parse_failed",
                "error": str(exc),
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": llm_result["profile_id"],
                "text": llm_result["text"],
                "usage": llm_result["usage"],
            }

    def _chat_completions_url(self) -> str:
        base_url = (self.settings.openai_base_url or "").strip().rstrip("/")
        if not base_url:
            base_url = "https://api.openai.com/v1"
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    @staticmethod
    def _client_timeout(config: ChatRuntimeConfig) -> httpx.Timeout:
        read_timeout = max(config.timeout_ms, 1000) / 1000
        return httpx.Timeout(
            connect=min(read_timeout, 15.0),
            read=read_timeout,
            write=min(read_timeout, 15.0),
            pool=min(read_timeout, 15.0),
        )
