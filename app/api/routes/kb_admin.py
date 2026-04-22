from __future__ import annotations

from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import KnowledgeBaseImportRequest, KnowledgeBaseRefreshRequest
from app.schemas.responses import (
    KnowledgeBaseDocumentResponse,
    KnowledgeBaseDocumentsResponse,
    KnowledgeBaseJobResponse,
    KnowledgeBaseStatusResponse,
)
from app.services.kb_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


@router.get("/status", response_model=KnowledgeBaseStatusResponse)
def kb_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseStatusResponse:
    return KnowledgeBaseStatusResponse(
        success=True,
        summary=KnowledgeBaseService(db, settings).status(),
    )


@router.post("/refresh", response_model=KnowledgeBaseJobResponse)
def kb_refresh(
    request: KnowledgeBaseRefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    result = KnowledgeBaseService(db, settings).refresh(
        source_paths=request.source_paths or None,
        force_rebuild=request.force_rebuild,
    )
    return KnowledgeBaseJobResponse(success=True, job=result["job"])


@router.post("/import", response_model=KnowledgeBaseJobResponse)
def kb_import(
    request: KnowledgeBaseImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    result = KnowledgeBaseService(db, settings).import_payload(request)
    return KnowledgeBaseJobResponse(success=True, job=result["job"])


@router.get("/import-jobs/{job_id}", response_model=KnowledgeBaseJobResponse)
def kb_import_job(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    job = KnowledgeBaseService(db, settings).get_job(job_id)
    if not job:
        raise APIError(404, "kb_job_not_found", f"KB import job `{job_id}` was not found.")
    return KnowledgeBaseJobResponse(success=True, job=job)


@router.get("/jobs/{job_id}", response_model=KnowledgeBaseJobResponse)
def kb_job_alias(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    return kb_import_job(job_id, db, settings)


@router.post("/reindex", response_model=KnowledgeBaseJobResponse)
def kb_reindex(
    request: KnowledgeBaseRefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    result = KnowledgeBaseService(db, settings).reindex(source_paths=request.source_paths or None)
    return KnowledgeBaseJobResponse(success=True, job=result["job"])


@router.post("/import-jobs/{job_id}/retry", response_model=KnowledgeBaseJobResponse)
def kb_retry_import_job(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    result = KnowledgeBaseService(db, settings).retry_job(job_id)
    if not result:
        raise APIError(404, "kb_job_not_found", f"KB import job `{job_id}` was not found.")
    return KnowledgeBaseJobResponse(success=True, job=result["job"])


@router.post("/jobs/{job_id}/retry", response_model=KnowledgeBaseJobResponse)
def kb_retry_job_alias(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseJobResponse:
    return kb_retry_import_job(job_id, db, settings)


@router.get("/documents", response_model=KnowledgeBaseDocumentsResponse)
def kb_documents(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseDocumentsResponse:
    return KnowledgeBaseDocumentsResponse(
        success=True,
        items=KnowledgeBaseService(db, settings).list_documents(),
    )


@router.get("/documents/{doc_id}", response_model=KnowledgeBaseDocumentResponse)
def kb_document_detail(
    doc_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseDocumentResponse:
    item = KnowledgeBaseService(db, settings).get_document(doc_id)
    if not item:
        raise APIError(404, "kb_document_not_found", f"KB document `{doc_id}` was not found.")
    return KnowledgeBaseDocumentResponse(success=True, item=item)


@router.delete("/documents/{doc_id}", response_model=KnowledgeBaseDocumentResponse)
def kb_delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> KnowledgeBaseDocumentResponse:
    item = KnowledgeBaseService(db, settings).delete_document(doc_id)
    if not item:
        raise APIError(404, "kb_document_not_found", f"KB document `{doc_id}` was not found.")
    return KnowledgeBaseDocumentResponse(success=True, item=item)
