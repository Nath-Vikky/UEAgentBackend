from __future__ import annotations

import httpx

from app.core.settings import Settings


def embedding_available(settings: Settings) -> bool:
    return settings.embedding_enabled and bool(settings.openai_api_key) and bool(settings.embedding_model)


def embed_query(settings: Settings, text: str) -> list[float]:
    vectors = embed_texts(settings, [text])
    if not vectors:
        raise ValueError("embedding_response_empty")
    return vectors[0]


def embed_texts(settings: Settings, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if not embedding_available(settings):
        raise ValueError("embedding_not_available")
    url = _embeddings_url(settings)
    payload = {
        "model": settings.embedding_model,
        "input": texts,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=max(settings.default_profile_tool_timeout_ms, 1000) / 1000) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    body = response.json()
    items = sorted(body.get("data") or [], key=lambda item: int(item.get("index", 0)))
    vectors: list[list[float]] = []
    for item in items:
        embedding = item.get("embedding") or []
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("embedding_vector_missing")
        vectors.append([float(value) for value in embedding])
    if len(vectors) != len(texts):
        raise ValueError("embedding_vector_count_mismatch")
    return vectors


def _embeddings_url(settings: Settings) -> str:
    base_url = (settings.openai_base_url or "").strip().rstrip("/")
    if not base_url:
        base_url = "https://api.openai.com/v1"
    if base_url.endswith("/embeddings"):
        return base_url
    return f"{base_url}/embeddings"
