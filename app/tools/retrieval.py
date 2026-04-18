from __future__ import annotations

from typing import Any

from app.schemas.requests import ContextInput
from app.services.kb_service import KnowledgeBaseService


def retrieve_support_notes(
    kb_service: KnowledgeBaseService,
    *,
    query: str,
    context: ContextInput,
    output_language: str,
    domain_filters: list[str],
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "user_query": query,
        "domain_filters": domain_filters,
        **(extra_payload or {}),
    }
    return kb_service.project_qa(
        query=query,
        context=context,
        payload=payload,
        output_language=output_language,
    )
