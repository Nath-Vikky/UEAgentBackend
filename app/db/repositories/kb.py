from __future__ import annotations

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.db.models.kb import KBChunkModel, KBDocumentModel, KBImportJobModel


def create_import_job(db: Session, job: KBImportJobModel) -> KBImportJobModel:
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_import_job(db: Session, job: KBImportJobModel) -> KBImportJobModel:
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_import_job(db: Session, job_id: str) -> KBImportJobModel | None:
    return db.get(KBImportJobModel, job_id)


def latest_import_job(db: Session) -> KBImportJobModel | None:
    statement = select(KBImportJobModel).order_by(desc(KBImportJobModel.created_at)).limit(1)
    return db.scalars(statement).first()


def clear_documents(db: Session) -> None:
    db.execute(delete(KBChunkModel))
    db.execute(delete(KBDocumentModel))
    db.commit()


def replace_document(
    db: Session,
    document: KBDocumentModel,
    chunks: list[KBChunkModel],
) -> None:
    existing_by_source = db.scalars(
        select(KBDocumentModel).where(KBDocumentModel.source_path == document.source_path)
    ).first()
    existing_by_doc_id = db.get(KBDocumentModel, document.doc_id)
    existing_documents = [
        item
        for item in (existing_by_source, existing_by_doc_id)
        if item is not None
    ]
    seen_doc_ids: set[str] = set()
    for existing in existing_documents:
        if existing.doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(existing.doc_id)
        db.execute(delete(KBChunkModel).where(KBChunkModel.doc_id == existing.doc_id))
        db.delete(existing)
    if seen_doc_ids:
        db.commit()

    db.add(document)
    for chunk in chunks:
        db.add(chunk)
    db.commit()


def kb_counts(db: Session) -> dict[str, int]:
    return {
        "documents": db.scalar(select(func.count()).select_from(KBDocumentModel)) or 0,
        "chunks": db.scalar(select(func.count()).select_from(KBChunkModel)) or 0,
        "jobs": db.scalar(select(func.count()).select_from(KBImportJobModel)) or 0,
    }


def list_chunks(db: Session) -> list[KBChunkModel]:
    statement = select(KBChunkModel).order_by(KBChunkModel.created_at.desc())
    return list(db.scalars(statement))


def list_documents(db: Session) -> list[KBDocumentModel]:
    statement = select(KBDocumentModel).order_by(desc(KBDocumentModel.updated_at))
    return list(db.scalars(statement))


def get_document(db: Session, doc_id: str) -> KBDocumentModel | None:
    return db.get(KBDocumentModel, doc_id)


def delete_document(db: Session, document: KBDocumentModel) -> None:
    db.execute(delete(KBChunkModel).where(KBChunkModel.doc_id == document.doc_id))
    db.delete(document)
    db.commit()
