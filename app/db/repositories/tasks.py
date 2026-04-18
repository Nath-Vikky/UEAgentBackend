from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.task import TaskArtifactModel, TaskEventModel, TaskModel
from app.utils.time import now_utc


def create_task(db: Session, task: TaskModel) -> TaskModel:
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def add_task_event(db: Session, event: TaskEventModel) -> TaskEventModel:
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def add_task_artifact(db: Session, artifact: TaskArtifactModel) -> TaskArtifactModel:
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def save_task(db: Session, task: TaskModel) -> TaskModel:
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_recent_tasks(db: Session, limit: int = 20) -> list[TaskModel]:
    statement = select(TaskModel).order_by(desc(TaskModel.created_at)).limit(limit)
    return list(db.scalars(statement))


def get_task(db: Session, task_id: str) -> TaskModel | None:
    return db.get(TaskModel, task_id)


def get_task_by_run_id(db: Session, run_id: str) -> TaskModel | None:
    statement = select(TaskModel).where(TaskModel.run_id == run_id)
    return db.scalars(statement).first()


def list_task_events(db: Session, task_id: str) -> list[TaskEventModel]:
    statement = select(TaskEventModel).where(TaskEventModel.task_id == task_id)
    events = list(db.scalars(statement))
    return sorted(
        events,
        key=lambda item: (
            int(item.payload_json.get("seq", 0)),
            item.created_at.isoformat() if item.created_at else "",
        ),
    )


def list_task_artifacts(db: Session, task_id: str) -> list[TaskArtifactModel]:
    statement = select(TaskArtifactModel).where(TaskArtifactModel.task_id == task_id)
    return list(db.scalars(statement))


def mark_task_cancelled(db: Session, task: TaskModel) -> TaskModel:
    task.status = "cancelled"
    task.finish_reason = "cancelled_by_user"
    task.completed_at = now_utc()
    return save_task(db, task)
