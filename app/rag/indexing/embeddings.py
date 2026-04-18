from __future__ import annotations

from app.core.settings import Settings


def embedding_available(settings: Settings) -> bool:
    return settings.embedding_enabled and bool(settings.openai_api_key)

