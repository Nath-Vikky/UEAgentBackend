from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import app.db.models  # noqa: F401
from app.core.settings import Settings
from app.db.base import Base
from app.db.repositories.web_memory import list_active_web_memory_entries
from app.db.session import get_engine, get_session_factory
from app.rag.curation import (
    build_web_memory_curation_suggestions,
    extract_curation_result,
    write_curation_artifact,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export suggestion-only knowledge curation artifacts for human review."
    )
    parser.add_argument(
        "--input",
        help="Optional JSON file containing a knowledge_curation payload or a task response.",
    )
    parser.add_argument(
        "--output-dir",
        default="storage/curation",
        help="Directory for generated Markdown/JSON artifacts.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum candidates to export.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.45,
        help="Minimum curation_candidate_score when exporting from Web Memory.",
    )
    return parser.parse_args()


def _load_input_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object.")
    result = extract_curation_result(payload)
    if not result:
        raise ValueError("Input JSON does not contain a knowledge_curation payload.")
    return result


def _web_memory_result(*, limit: int, min_score: float) -> dict[str, Any]:
    settings = Settings()
    Base.metadata.create_all(bind=get_engine())
    session_factory = get_session_factory()
    with session_factory() as db:
        entries = list_active_web_memory_entries(db, limit=max(limit * 4, 20))
        items = [
            {
                "query": entry.query,
                "title": entry.title,
                "url": entry.url,
                "domain": entry.domain,
                "snippet": entry.snippet,
                "source_type": entry.source_type,
                "provider": entry.provider,
                "source_score": entry.source_score,
                "quality_score": entry.quality_score,
                "helpful_count": entry.helpful_count or 0,
                "unhelpful_count": entry.unhelpful_count or 0,
                "recall_count": int((entry.metadata_json or {}).get("recall_count") or 0),
                "metadata": dict(entry.metadata_json or {}),
            }
            for entry in entries
        ]
    result = build_web_memory_curation_suggestions(
        items=items,
        limit=limit,
        min_score=min_score,
    )
    result["source"] = {
        "type": "web_memory",
        "web_memory_enabled": settings.web_memory_enabled,
        "candidate_source_count": len(items),
    }
    return result


def main() -> int:
    args = _parse_args()
    if args.input:
        curation_result = _load_input_result(Path(args.input))
    else:
        curation_result = _web_memory_result(limit=args.limit, min_score=args.min_score)

    artifact = write_curation_artifact(
        curation_result,
        output_dir=args.output_dir,
    )
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
