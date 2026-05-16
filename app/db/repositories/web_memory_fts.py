from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models.web_memory import WebMemoryEntryModel
from app.utils.time import now_utc


FTS_TABLE = "web_memory_entries_fts"


@dataclass(slots=True)
class WebMemoryFtsResult:
    status: str
    reason: str
    items: list[tuple[WebMemoryEntryModel, float]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def ensure_web_memory_fts(db: Session) -> dict[str, Any]:
    if db.get_bind().dialect.name != "sqlite":
        return {"available": False, "reason": "non_sqlite_dialect"}
    try:
        db.execute(
            text(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE}
                USING fts5(entry_id UNINDEXED, title, domain, snippet)
                """
            )
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        return {"available": False, "reason": "fts5_unavailable", "error": str(exc)}
    return {"available": True, "reason": "ready"}


def sync_web_memory_fts_entries(
    db: Session,
    entries: list[WebMemoryEntryModel],
) -> dict[str, Any]:
    status = ensure_web_memory_fts(db)
    if not status["available"]:
        return {"synced_count": 0, **status}
    try:
        for entry in entries:
            db.execute(text(f"DELETE FROM {FTS_TABLE} WHERE entry_id = :entry_id"), {"entry_id": entry.entry_id})
            db.execute(
                text(
                    f"""
                    INSERT INTO {FTS_TABLE}(entry_id, title, domain, snippet)
                    VALUES (:entry_id, :title, :domain, :snippet)
                    """
                ),
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title or "",
                    "domain": entry.domain or "",
                    "snippet": entry.snippet or "",
                },
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        return {"available": False, "reason": "fts5_sync_failed", "error": str(exc), "synced_count": 0}
    return {"available": True, "reason": "synced", "synced_count": len(entries)}


def search_web_memory_fts_entries(
    db: Session,
    *,
    terms: list[str],
    domain_hints: list[str] | None = None,
    limit: int = 10,
) -> WebMemoryFtsResult:
    status = ensure_web_memory_fts(db)
    if not status["available"]:
        return WebMemoryFtsResult(status="unavailable", reason=status["reason"], diagnostics=status)
    match_query = _fts_match_query(terms)
    if not match_query:
        return WebMemoryFtsResult(status="skipped", reason="empty_query", diagnostics=status)

    params: dict[str, Any] = {
        "match_query": match_query,
        "checked_at": now_utc(),
        "limit": max(1, min(limit, 50)),
    }
    domain_clause = ""
    clean_domains = [item.lower().strip() for item in domain_hints or [] if item.strip()]
    if clean_domains:
        parts: list[str] = []
        for index, domain in enumerate(clean_domains):
            key = f"domain_{index}"
            parts.append(f"lower(e.domain) LIKE :{key}")
            params[key] = f"%{domain}%"
        domain_clause = " AND (" + " OR ".join(parts) + ")"

    try:
        rows = db.execute(
            text(
                f"""
                SELECT e.entry_id AS entry_id, bm25({FTS_TABLE}) AS rank_score
                FROM {FTS_TABLE}
                JOIN web_memory_entries AS e ON e.entry_id = {FTS_TABLE}.entry_id
                WHERE {FTS_TABLE} MATCH :match_query
                  AND (e.expires_at IS NULL OR e.expires_at > :checked_at)
                  {domain_clause}
                ORDER BY rank_score ASC
                LIMIT :limit
                """
            ),
            params,
        ).mappings()
    except SQLAlchemyError as exc:
        db.rollback()
        return WebMemoryFtsResult(
            status="unavailable",
            reason="fts5_search_failed",
            diagnostics={"available": False, "error": str(exc), "match_query": match_query},
        )

    ranked_rows = list(rows)
    if not ranked_rows:
        return WebMemoryFtsResult(
            status="completed",
            reason="no_fts_match",
            diagnostics={"available": True, "match_query": match_query, "candidate_count": 0},
        )

    entry_ids = [str(row["entry_id"]) for row in ranked_rows]
    entries = {
        entry.entry_id: entry
        for entry in db.scalars(select(WebMemoryEntryModel).where(WebMemoryEntryModel.entry_id.in_(entry_ids)))
    }
    items: list[tuple[WebMemoryEntryModel, float]] = []
    for index, row in enumerate(ranked_rows, 1):
        entry = entries.get(str(row["entry_id"]))
        if not entry:
            continue
        items.append((entry, _rank_to_score(row.get("rank_score"), index)))
    return WebMemoryFtsResult(
        status="completed",
        reason="matched" if items else "entries_missing",
        items=items,
        diagnostics={"available": True, "match_query": match_query, "candidate_count": len(items)},
    )


def _fts_match_query(terms: list[str]) -> str:
    clean_terms = [term.strip().replace('"', '""') for term in terms if term.strip()]
    return " OR ".join(f'"{term}"' for term in clean_terms[:12])


def _rank_to_score(rank: Any, position: int) -> float:
    try:
        value = abs(float(rank))
    except (TypeError, ValueError):
        value = float(position)
    return max(0.0, min(1.0, 1.0 / (1.0 + value + position * 0.05)))
