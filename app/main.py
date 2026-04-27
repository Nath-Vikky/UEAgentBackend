from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.errors import install_exception_handlers
from app.api.router import api_router
from app.core.settings import get_settings
from app.core.startup_checks import collect_startup_checks
from app.db.base import Base
from app.db.models import (  # noqa: F401
    AuditLogModel,
    KBChunkModel,
    KBDocumentModel,
    KBImportJobModel,
    MessageModel,
    ProposalDecisionModel,
    ProposalModel,
    RuntimeProfileModel,
    SessionModel,
    TaskArtifactModel,
    TaskEventModel,
    TaskModel,
)
from app.db.session import get_engine, get_session_factory
from app.observability.metrics import render_prometheus_metrics
from app.observability.redaction import redact_payload
from app.services.runtime_profile_service import RuntimeProfileService
from app.utils.paths import ensure_storage_dirs


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging()
    ensure_storage_dirs(settings)
    Base.metadata.create_all(bind=get_engine())
    session_factory = get_session_factory()
    with session_factory() as db:
        RuntimeProfileService(db, settings).ensure_seeded()
    startup_checks = collect_startup_checks(settings, database_status="ok")
    logger = logging.getLogger("ue-agent-backend")
    for item in startup_checks["checks"]:
        if item["status"] in {"warning", "error"}:
            logger.warning(
                "Startup check %s: %s",
                item["check_id"],
                item["message"],
            )
    logging.getLogger("ue-agent-backend").info(
        "Settings summary: %s",
        redact_payload(
            {
                "app_env": settings.app_env,
                "database_url": settings.database_url,
                "qdrant_url": settings.qdrant_url,
                "chat_model": settings.chat_model,
                "embedding_model": settings.embedding_model,
                "langsmith_project": settings.langsmith_project,
            }
        ),
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        root_path=settings.app_root_path,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_exception_handlers(application)
    application.include_router(api_router)

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> PlainTextResponse:
        session_factory = get_session_factory()
        with session_factory() as db:
            return PlainTextResponse(render_prometheus_metrics(db), media_type="text/plain; version=0.0.4")

    return application


app = create_app()
