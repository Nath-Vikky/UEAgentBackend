from __future__ import annotations

from pathlib import Path

from app.core.settings import Settings


def ensure_storage_dirs(settings: Settings) -> None:
    for directory in [
        settings.storage_dir,
        settings.upload_dir,
        settings.artifact_dir,
        settings.kb_dir,
        f"{settings.kb_dir}/raw",
        f"{settings.kb_dir}/normalized",
        f"{settings.kb_dir}/failed",
    ]:
        Path(directory).mkdir(parents=True, exist_ok=True)


def task_artifact_dir(settings: Settings, task_id: str) -> Path:
    path = Path(settings.artifact_dir) / "tasks" / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path

