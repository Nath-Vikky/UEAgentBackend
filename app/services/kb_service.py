from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.models.kb import KBChunkModel, KBDocumentModel, KBImportJobModel
from app.db.repositories.kb import (
    clear_documents,
    create_import_job,
    delete_document,
    get_document,
    get_import_job,
    kb_counts,
    latest_import_job,
    list_chunks,
    list_documents,
    replace_document,
    update_import_job,
)
from app.rag.ingestion.chunkers import chunk_text
from app.rag.ingestion.capabilities import ingestion_capabilities
from app.rag.ingestion.dedup import content_hash
from app.rag.ingestion.jobs import utc_now
from app.rag.ingestion.loaders import discover_source_paths
from app.rag.ingestion.parsers import parse_path
from app.rag.retrieval.hybrid import retrieve
from app.rag.schemas import ParsedDocument
from app.schemas.requests import ContextInput, KnowledgeBaseImportRequest


class KnowledgeBaseService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.kb_root = Path(settings.kb_dir)
        self.raw_dir = self.kb_root / "raw"
        self.normalized_dir = self.kb_root / "normalized"
        self.failed_dir = self.kb_root / "failed"

    def status(self) -> dict[str, Any]:
        from app.rag.indexing.embeddings import embedding_available
        from app.rag.indexing.qdrant_store import qdrant_available

        counts = kb_counts(self.db)
        latest_job_model = latest_import_job(self.db)
        qdrant_ok, qdrant_reason = qdrant_available(self.settings)
        embedding_ok = embedding_available(self.settings)
        ingestion = ingestion_capabilities()
        documents = list_documents(self.db)
        domain_counts: dict[str, int] = {}
        for document in documents:
            domain = document.domain or "unknown"
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        lexical_ready = counts["chunks"] > 0
        embedding_ready = bool(self.settings.embedding_enabled and embedding_ok)
        vector_store_ready = bool(qdrant_ok and embedding_ready)
        degraded_reasons: list[str] = []
        if not lexical_ready:
            degraded_reasons.append("no_indexed_chunks")
        if self.settings.rag_mode != "lexical":
            if not self.settings.embedding_enabled:
                degraded_reasons.append("embedding_disabled")
            elif not embedding_ok:
                degraded_reasons.append("embedding_unavailable")
            if not qdrant_ok:
                degraded_reasons.append(qdrant_reason)
        effective_mode = self.settings.rag_mode
        if self.settings.rag_mode != "lexical" and not vector_store_ready:
            effective_mode = self.settings.rag_fallback_mode
        readiness_status = (
            "empty"
            if not lexical_ready
            else "ready"
            if self.settings.rag_mode == "lexical" or vector_store_ready
            else "degraded"
        )
        return {
            "enabled": True,
            "mode": self.settings.rag_mode,
            "fallback_mode": self.settings.rag_fallback_mode,
            "effective_mode": effective_mode,
            "rag_readiness": {
                "status": readiness_status,
                "lexical_ready": lexical_ready,
                "embedding_configured": self.settings.embedding_enabled,
                "embedding_ready": embedding_ready,
                "vector_store_ready": vector_store_ready,
                "usable_for_project_qa": lexical_ready,
                "degraded_reasons": degraded_reasons,
                "indexed_documents": counts["documents"],
                "indexed_chunks": counts["chunks"],
                "domain_counts": domain_counts,
                "eval_command": "python scripts/run_rag_eval.py --dataset tests/eval/rag_project_qa_dataset.jsonl",
            },
            "ingestion_pipeline": ingestion["pipeline"],
            "format_groups": ingestion["format_groups"],
            "collection": self.settings.qdrant_collection,
            "documents": counts["documents"],
            "chunks": counts["chunks"],
            "jobs": counts["jobs"],
            "embedding_enabled": self.settings.embedding_enabled,
            "embedding_available": embedding_ok,
            "qdrant_available": qdrant_ok,
            "qdrant_reason": qdrant_reason,
            "degraded_mode": self.settings.rag_mode != "lexical" and not (qdrant_ok and embedding_ok),
            "vector_store_enabled": qdrant_ok and embedding_ok,
            "supported_formats": ingestion["supported_formats"],
            "first_class_formats": ingestion["first_class_formats"],
            "enhanced_formats": ingestion["enhanced_formats"],
            "parser_dependencies": ingestion["parser_dependencies"],
            "knowledge_domains": ingestion["knowledge_domains"],
            "source_paths": self.settings.kb_source_paths,
            "latest_job": self._serialize_job(latest_job_model) if latest_job_model else None,
            "message": (
                "Knowledge base is ready."
                if counts["documents"]
                else "Knowledge base is empty. Refresh or import documents to enable project QA."
            ),
        }

    def ensure_seeded(self) -> None:
        counts = kb_counts(self.db)
        if counts["documents"] == 0:
            self.refresh(force_rebuild=False)

    def refresh(
        self,
        *,
        source_paths: list[str] | None = None,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        job = KBImportJobModel(
            job_id=f"job_{uuid.uuid4().hex}",
            mode="refresh",
            status="queued",
            source_summary_json={"source_paths": source_paths or self.settings.kb_source_paths},
            stats_json={"documents": 0, "chunks": 0, "failed": 0},
        )
        create_import_job(self.db, job)
        return self._run_import_job(job, source_paths=source_paths, force_rebuild=force_rebuild)

    def import_payload(self, request: KnowledgeBaseImportRequest) -> dict[str, Any]:
        if request.source_type == "text":
            return self._import_text_payload(request)
        return self.refresh(source_paths=request.source_paths, force_rebuild=False)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = get_import_job(self.db, job_id)
        return self._serialize_job(job) if job else None

    def retry_job(self, job_id: str) -> dict[str, Any] | None:
        job = get_import_job(self.db, job_id)
        if not job:
            return None
        source_paths = list((job.source_summary_json or {}).get("source_paths") or self.settings.kb_source_paths)
        return self.refresh(source_paths=source_paths, force_rebuild=False)

    def reindex(self, *, source_paths: list[str] | None = None) -> dict[str, Any]:
        return self.refresh(source_paths=source_paths or self.settings.kb_source_paths, force_rebuild=True)

    def list_documents(self) -> list[dict[str, Any]]:
        return [self._serialize_document(item) for item in list_documents(self.db)]

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        item = get_document(self.db, doc_id)
        return self._serialize_document(item) if item else None

    def delete_document(self, doc_id: str) -> dict[str, Any] | None:
        item = get_document(self.db, doc_id)
        if not item:
            return None
        serialized = self._serialize_document(item)
        for key in ("raw_storage_path", "normalized_storage_path"):
            path_value = getattr(item, key, None)
            if path_value:
                try:
                    Path(path_value).unlink(missing_ok=True)
                except OSError:
                    pass
        delete_document(self.db, item)
        self._rebuild_vector_index()
        return serialized

    def project_qa(
        self,
        *,
        query: str,
        context: ContextInput,
        payload: dict[str, Any],
        output_language: str,
    ) -> dict[str, Any]:
        self.ensure_seeded()
        chunks = list_chunks(self.db)
        result = retrieve(
            query=query,
            context=context,
            payload=payload,
            chunks=chunks,
            settings=self.settings,
            output_language=output_language,
        )
        answer_text = result.answer
        if output_language.startswith("zh") and not answer_text.startswith("基于"):
            answer_text = "当前未命中足够证据，建议补充文档后重试。"
        return {
            "answer": answer_text,
            "confidence": result.confidence,
            "sources": [
                {"title": item.title, "source": item.source_path, "domain": item.domain}
                for item in result.retrieved_docs
            ],
            "citations": result.citations,
            "retrieved_docs": [
                {
                    "chunk_id": item.chunk_id,
                    "doc_id": item.doc_id,
                    "title": item.title,
                    "source_path": item.source_path,
                    "domain": item.domain,
                    "section_path": item.section_path,
                    "text": item.text[:800],
                    "lexical_score": item.lexical_score,
                    "semantic_score": item.semantic_score,
                    "final_score": item.final_score,
                }
                for item in result.retrieved_docs
            ],
            "filters_applied": result.filters_applied,
            "retrieval_trace": {
                "mode": result.mode,
                "degraded_mode": result.degraded_mode,
                "reason": result.reason,
                "filters_applied": result.filters_applied,
                "retrieved_docs": [
                    {
                        "title": item.title,
                        "source_path": item.source_path,
                        "domain": item.domain,
                        "section_path": item.section_path,
                        "text": item.text[:400],
                        "lexical_score": item.lexical_score,
                        "semantic_score": item.semantic_score,
                        "final_score": item.final_score,
                    }
                    for item in result.retrieved_docs
                ],
            },
            "warnings": result.warnings,
        }

    def _run_import_job(
        self,
        job: KBImportJobModel,
        *,
        source_paths: list[str] | None,
        force_rebuild: bool,
    ) -> dict[str, Any]:
        job.status = "parsing"
        job.started_at = utc_now()
        update_import_job(self.db, job)

        discovered = discover_source_paths(self.settings, source_paths)
        if force_rebuild:
            clear_documents(self.db)

        stats = {"documents": 0, "chunks": 0, "failed": 0, "sources": len(discovered)}
        failures: list[dict[str, str]] = []
        for path in discovered:
            try:
                if path.stat().st_size > self.settings.kb_max_file_bytes:
                    raise ValueError("file_too_large")
                parsed = parse_path(path)
                document, chunks = self._persist_parsed_document(parsed)
                replace_document(self.db, document, chunks)
                stats["documents"] += 1
                stats["chunks"] += len(chunks)
            except Exception as exc:
                stats["failed"] += 1
                failures.append({"source_path": str(path), "reason": str(exc)})
                self._persist_failure(path)

        vector_sync = self._rebuild_vector_index()
        job.status = "completed" if not failures else "completed"
        job.finished_at = utc_now()
        job.stats_json = {**stats, "failures": failures, "vector_sync": vector_sync}
        job.error_message = None if not failures else f"{len(failures)} source(s) failed."
        update_import_job(self.db, job)
        return {"accepted": True, "job": self._serialize_job(job)}

    def _persist_parsed_document(
        self,
        parsed,
    ) -> tuple[KBDocumentModel, list[KBChunkModel]]:
        file_hash = content_hash(parsed.text)
        doc_id = f"doc_{file_hash[:16]}"
        raw_storage_path = self._copy_raw_source(parsed.source_path, file_hash)
        normalized_storage_path = self._write_normalized(doc_id, parsed.text)
        chunks = chunk_text(parsed.text, self.settings, parsed.title)
        document = KBDocumentModel(
            doc_id=doc_id,
            project_id=parsed.project_id,
            domain=parsed.domain,
            source_path=parsed.source_path,
            source_type=parsed.source_type,
            file_hash=file_hash,
            title=parsed.title,
            language=parsed.language,
            doc_type=parsed.doc_type,
            module=parsed.module,
            parser_name=parsed.parser_name,
            status="active",
            token_count=max(1, len(parsed.text.split())),
            raw_storage_path=raw_storage_path,
            normalized_storage_path=normalized_storage_path,
            tags_json=parsed.tags,
            metadata_json=parsed.metadata,
        )
        chunk_models: list[KBChunkModel] = []
        for chunk in chunks:
            chunk_models.append(
                KBChunkModel(
                    chunk_id=f"chunk_{doc_id}_{chunk.chunk_index}",
                    doc_id=doc_id,
                    project_id=parsed.project_id,
                    domain=parsed.domain,
                    source_path=parsed.source_path,
                    title=parsed.title,
                    section_path=chunk.section_path,
                    language=parsed.language,
                    doc_type=parsed.doc_type,
                    module=parsed.module,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                    text=chunk.text,
                    text_hash=content_hash(chunk.text),
                    tags_json=parsed.tags,
                    metadata_json={**parsed.metadata, **chunk.metadata},
                )
            )
        return document, chunk_models

    def _import_text_payload(self, request: KnowledgeBaseImportRequest) -> dict[str, Any]:
        title = request.title or "Imported Text"
        text = (request.text or request.content or "").strip()
        if not text:
            raise ValueError("text or content payload is required when source_type=text")
        source_path = f"text://{title.replace(' ', '_').lower()}"
        normalized_storage_path = self._write_normalized(f"text_{uuid.uuid4().hex[:8]}", text)
        parsed_like = ParsedDocument(
            source_path=source_path,
            source_type="text",
            title=title,
            text=text,
            language="zh-CN" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "en-US",
            parser_name="inline_text",
            doc_type=request.doc_type or self._infer_inline_doc_type(request.domain, text),
            domain=request.domain or "project_docs",
            project_id=request.project_id,
            module=self._string_metadata(request.metadata, "module"),
            tags=request.tags,
            metadata={"import_mode": "text", **request.metadata},
        )
        document, chunks = self._persist_parsed_document(parsed_like)
        document.raw_storage_path = normalized_storage_path
        replace_document(self.db, document, chunks)
        vector_sync = self._rebuild_vector_index()
        return {
            "accepted": True,
            "job": {
                "job_id": f"inline_{document.doc_id}",
                "mode": "import",
                "status": "completed",
                "source_summary": {"source_type": "text", "title": title},
                "stats": {
                    "documents": 1,
                    "chunks": len(chunks),
                    "failed": 0,
                    "vector_sync": vector_sync,
                },
            },
        }

    @staticmethod
    def _infer_inline_doc_type(domain: str | None, text: str) -> str:
        if domain in {"code_reference", "examples"}:
            return "code"
        preview = text[:500]
        code_tokens = ("#include", "UCLASS", "UPROPERTY", "UFUNCTION", "class ", "def ", "namespace ")
        return "code" if any(token in preview for token in code_tokens) else "reference"

    @staticmethod
    def _string_metadata(metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) and value.strip() else None

    def _copy_raw_source(self, source_path: str, file_hash: str) -> str | None:
        path = Path(source_path)
        if not path.exists():
            return None
        target = self.raw_dir / f"{file_hash[:16]}_{path.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        return str(target)

    def _write_normalized(self, doc_id: str, text: str) -> str:
        target = self.normalized_dir / f"{doc_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return str(target)

    def _persist_failure(self, path: Path) -> None:
        target = self.failed_dir / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    def _serialize_job(self, job: KBImportJobModel | None) -> dict[str, Any]:
        if not job:
            return {}
        return {
            "job_id": job.job_id,
            "mode": job.mode,
            "status": job.status,
            "source_summary": job.source_summary_json,
            "stats": job.stats_json,
            "error_message": job.error_message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }

    def _serialize_document(self, document: KBDocumentModel | None) -> dict[str, Any]:
        if not document:
            return {}
        return {
            "doc_id": document.doc_id,
            "project_id": document.project_id,
            "domain": document.domain,
            "source_path": document.source_path,
            "source_type": document.source_type,
            "title": document.title,
            "language": document.language,
            "doc_type": document.doc_type,
            "module": document.module,
            "parser_name": document.parser_name,
            "status": document.status,
            "token_count": document.token_count,
            "raw_storage_path": document.raw_storage_path,
            "normalized_storage_path": document.normalized_storage_path,
            "tags": document.tags_json,
            "metadata": document.metadata_json,
            "chunk_count": len(document.chunks),
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        }

    def _rebuild_vector_index(self) -> dict[str, Any]:
        from app.rag.indexing.embeddings import embed_texts, embedding_available
        from app.rag.indexing.qdrant_store import drop_collection, qdrant_available, upsert_chunk_vectors

        chunks = list_chunks(self.db)
        embedding_ok = embedding_available(self.settings)
        qdrant_ok, qdrant_reason = qdrant_available(self.settings)
        if not chunks:
            if qdrant_ok:
                drop_collection(self.settings)
            return {"status": "empty", "indexed_chunks": 0}
        if not embedding_ok:
            return {"status": "embedding_not_available", "indexed_chunks": 0}
        if not qdrant_ok:
            return {"status": qdrant_reason, "indexed_chunks": 0}

        drop_collection(self.settings)
        indexed = 0
        batch_size = 32
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embed_texts(self.settings, [item.text for item in batch])
            upsert_chunk_vectors(
                self.settings,
                [
                    {
                        "id": item.chunk_id,
                        "vector": vector,
                        "payload": {
                            "chunk_id": item.chunk_id,
                            "doc_id": item.doc_id,
                            "title": item.title,
                            "source_path": item.source_path,
                            "domain": item.domain,
                            "section_path": item.section_path,
                            "module": item.module,
                            "doc_type": item.doc_type,
                            "text": item.text,
                        },
                    }
                    for item, vector in zip(batch, vectors, strict=True)
                ],
            )
            indexed += len(batch)
        return {
            "status": "synced",
            "indexed_chunks": indexed,
            "collection": self.settings.qdrant_collection,
        }
