from __future__ import annotations

from app.core.settings import Settings


def qdrant_available(settings: Settings) -> tuple[bool, str]:
    try:
        from qdrant_client import QdrantClient
    except Exception:
        return False, "qdrant_client_not_installed"

    try:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        client.get_collections()
        return True, "connected"
    except Exception as exc:
        return False, f"qdrant_unavailable:{exc.__class__.__name__}"

