from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.audit import AuditLogModel


def create_audit_log(db: Session, audit_log: AuditLogModel) -> AuditLogModel:
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log
