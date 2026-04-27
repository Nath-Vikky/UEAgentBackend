from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.core.settings import Settings
from app.core.startup_checks import collect_startup_checks


def _runtime_root() -> Path:
    root = Path(".test-runtime") / f"startup-checks-{uuid.uuid4().hex}"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_startup_checks_warn_when_llm_key_is_missing() -> None:
    root = _runtime_root()
    try:
        knowledge_dir = root / "knowledge"
        knowledge_dir.mkdir()
        storage_dir = root / "storage"
        storage_dir.mkdir()

        settings = Settings(
            openai_api_key="",
            storage_dir=str(storage_dir),
            upload_dir=str(storage_dir / "uploads"),
            artifact_dir=str(storage_dir / "artifacts"),
            kb_dir=str(storage_dir / "kb"),
            kb_source_paths=[str(knowledge_dir)],
        )

        report = collect_startup_checks(settings, database_status="ok")

        llm_check = next(item for item in report["checks"] if item["check_id"] == "llm_api_key")
        assert report["blocking"] is False
        assert llm_check["status"] == "warning"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_startup_checks_marks_empty_chat_model_as_error() -> None:
    root = _runtime_root()
    try:
        settings = Settings(
            chat_model="",
            storage_dir=str(root / "storage"),
            upload_dir=str(root / "storage" / "uploads"),
            artifact_dir=str(root / "storage" / "artifacts"),
            kb_dir=str(root / "storage" / "kb"),
            kb_source_paths=[str(root / "missing-knowledge")],
        )

        report = collect_startup_checks(settings, database_status="ok")

        chat_model_check = next(item for item in report["checks"] if item["check_id"] == "chat_model")
        assert report["blocking"] is True
        assert chat_model_check["status"] == "error"
    finally:
        shutil.rmtree(root, ignore_errors=True)
