from __future__ import annotations

from typing import Any

from app.core.settings import Settings


def qdrant_available(settings: Settings) -> tuple[bool, str]:
    try:
        client = _client(settings)
        client.get_collections()
        return True, "connected"
    except Exception as exc:
        return False, f"qdrant_unavailable:{exc.__class__.__name__}"


def drop_collection(settings: Settings) -> None:
    client = _client(settings)
    try:
        client.delete_collection(collection_name=settings.qdrant_collection)
    except Exception:
        # Missing collection is fine for best-effort rebuilds.
        return


def upsert_chunk_vectors(settings: Settings, points: list[dict[str, Any]]) -> None:
    if not points:
        return
    client = _client(settings)
    models = _models()
    vector_size = len(points[0]["vector"])
    ensure_collection(settings, vector_size)
    client.upsert(
        collection_name=settings.qdrant_collection,
        points=[
            models.PointStruct(
                id=item["id"],
                vector=item["vector"],
                payload=item["payload"],
            )
            for item in points
        ],
        wait=True,
    )


def search_similar_chunks(
    settings: Settings,
    query_vector: list[float],
    *,
    top_k: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    client = _client(settings)
    limit = max(top_k * 4, top_k)
    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    filtered: list[dict[str, Any]] = []
    for item in hits:
        payload = dict(item.payload or {})
        if not _payload_matches(payload, filters):
            continue
        filtered.append(
            {
                "chunk_id": str(payload.get("chunk_id") or item.id),
                "score": float(item.score),
                "payload": payload,
            }
        )
        if len(filtered) >= top_k:
            break
    return filtered


def ensure_collection(settings: Settings, vector_size: int) -> None:
    client = _client(settings)
    try:
        client.get_collection(collection_name=settings.qdrant_collection)
        return
    except Exception:
        pass
    models = _models()
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def _payload_matches(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    domains = list(filters.get("domains") or [])
    if domains and payload.get("domain") not in domains:
        return False
    module = filters.get("module")
    if module and payload.get("module") not in {module, None, ""}:
        return False
    doc_type = filters.get("doc_type")
    if doc_type and payload.get("doc_type") != doc_type:
        return False
    return True


def _client(settings: Settings):
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


def _models():
    from qdrant_client import models

    return models
