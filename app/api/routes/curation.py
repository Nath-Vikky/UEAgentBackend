from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.rag.curation import build_web_memory_curation_suggestions, write_curation_artifact
from app.services.web_memory_service import WebMemoryService
from app.utils.time import now_utc

router = APIRouter(prefix="/curation", tags=["curation"])


class CurationDecisionRequest(BaseModel):
    reviewer: str = ""
    comment: str = ""
    reason: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


def _curation_candidates(
    *,
    db: Session,
    settings: Settings,
    limit: int,
    min_score: float,
) -> dict:
    recent = WebMemoryService(db, settings).list_recent(limit=max(limit * 3, limit, 20))
    return build_web_memory_curation_suggestions(
        items=recent.get("items", []),
        limit=limit,
        min_score=min_score,
    )


def _find_candidate(curation_result: dict, candidate_id: str) -> dict | None:
    for item in curation_result.get("candidates", []):
        if isinstance(item, dict) and item.get("candidate_id") == candidate_id:
            return item
    return None


def _curation_output_dir(settings: Settings) -> Path:
    path = Path(settings.storage_dir) / "curation"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.get("/candidates")
def list_curation_candidates(
    limit: int = Query(default=20, ge=1, le=100),
    min_score: float = Query(default=0.45, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    result = _curation_candidates(db=db, settings=settings, limit=limit, min_score=min_score)
    return {
        "success": True,
        "source": "web_memory",
        "result": result,
        "writes_to_kb": False,
        "auto_apply": False,
    }


@router.get("/candidates/{candidate_id}")
def get_curation_candidate(
    candidate_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    result = _curation_candidates(db=db, settings=settings, limit=limit, min_score=min_score)
    candidate = _find_candidate(result, candidate_id)
    if not candidate:
        raise APIError(404, "curation_candidate_not_found", f"Curation candidate `{candidate_id}` was not found.")
    return {"success": True, "candidate": candidate, "writes_to_kb": False}


@router.post("/candidates/{candidate_id}/approve")
def approve_curation_candidate(
    candidate_id: str,
    request: CurationDecisionRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    result = _curation_candidates(db=db, settings=settings, limit=100, min_score=0.0)
    candidate = _find_candidate(result, candidate_id)
    if not candidate:
        raise APIError(404, "curation_candidate_not_found", f"Curation candidate `{candidate_id}` was not found.")
    decision = request or CurationDecisionRequest()
    single_candidate_result = {
        **result,
        "status": "suggested",
        "candidate_count": 1,
        "candidates": [
            {
                **candidate,
                "review_decision": {
                    "state": "approved_for_manual_distillation",
                    "reviewer": decision.reviewer,
                    "comment": decision.comment,
                    "metadata": decision.metadata,
                    "decided_at": now_utc().isoformat(),
                },
            }
        ],
        "writes_to_kb": False,
        "auto_apply": False,
    }
    artifact = write_curation_artifact(
        single_candidate_result,
        output_dir=_curation_output_dir(settings),
        prefix="kb-curation-approved",
    )
    return {
        "success": True,
        "candidate_id": candidate_id,
        "decision_state": "approved_for_manual_distillation",
        "artifact": artifact,
        "writes_to_kb": False,
        "next_step": "Review and rewrite the artifact manually before adding a distilled note to knowledge/.",
    }


@router.post("/candidates/{candidate_id}/reject")
def reject_curation_candidate(
    candidate_id: str,
    request: CurationDecisionRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    result = _curation_candidates(db=db, settings=settings, limit=100, min_score=0.0)
    candidate = _find_candidate(result, candidate_id)
    if not candidate:
        raise APIError(404, "curation_candidate_not_found", f"Curation candidate `{candidate_id}` was not found.")
    decision = request or CurationDecisionRequest()
    payload = {
        "candidate_id": candidate_id,
        "decision_state": "rejected",
        "reason": decision.reason or decision.comment,
        "reviewer": decision.reviewer,
        "metadata": decision.metadata,
        "decided_at": now_utc().isoformat(),
        "candidate": candidate,
        "writes_to_kb": False,
    }
    rejected_dir = _curation_output_dir(settings) / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    marker_path = rejected_dir / f"{candidate_id}.json"
    marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "candidate_id": candidate_id,
        "decision_state": "rejected",
        "marker_path": marker_path.as_posix(),
        "writes_to_kb": False,
    }


@router.post("/candidates/{candidate_id}/{decision}")
def decide_curation_candidate_alias(
    candidate_id: str,
    decision: Literal["approve", "reject"],
    request: CurationDecisionRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    if decision == "approve":
        return approve_curation_candidate(candidate_id, request, db, settings)
    return reject_curation_candidate(candidate_id, request, db, settings)

