from __future__ import annotations

from app.db.models.runtime_profile import RuntimeProfileModel


def runtime_profile_to_dict(profile: RuntimeProfileModel) -> dict:
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "description": profile.description,
        "chat_model": profile.chat_model,
        "embedding_model": profile.embedding_model,
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "rag_top_k": profile.rag_top_k,
        "rerank_top_n": profile.rerank_top_n,
        "allow_streaming": profile.allow_streaming,
        "debug_mode": profile.debug_mode,
        "tool_timeout_ms": profile.tool_timeout_ms,
        "cost_guard_usd": profile.cost_guard_usd,
        "is_active": profile.is_active,
        "is_default": profile.is_default,
        "is_builtin": profile.is_builtin,
    }

