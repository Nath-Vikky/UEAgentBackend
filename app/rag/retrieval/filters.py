from __future__ import annotations

from app.schemas.requests import ContextInput


def build_filters(context: ContextInput, payload: dict) -> dict:
    domain_filters = payload.get("domain_filters") or context.kb_domains_hint or []
    if isinstance(domain_filters, str):
        domain_filters = [domain_filters]
    return {
        "domains": domain_filters,
        "module": payload.get("module") or context.current_module,
        "doc_type": payload.get("doc_type"),
    }

