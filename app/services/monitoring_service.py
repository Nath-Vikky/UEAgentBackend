from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.repositories.kb import latest_import_job
from app.db.repositories.proposals import list_pending_proposals
from app.db.repositories.tasks import list_recent_tasks


class MonitoringService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def alerts_snapshot(self) -> dict:
        tasks = list_recent_tasks(self.db, limit=200)
        pending_proposals = list_pending_proposals(self.db)
        latest_job = latest_import_job(self.db)
        now = datetime.now(UTC)

        total_tasks = len(tasks)
        failed_tasks = sum(1 for task in tasks if task.status == "failed")
        error_rate = failed_tasks / total_tasks if total_tasks else 0.0

        latencies = sorted(
            int((task.usage_json or {}).get("latency_ms", 0) or 0)
            for task in tasks
            if isinstance(task.usage_json, dict)
        )
        if latencies:
            p95_index = max(0, ceil(0.95 * len(latencies)) - 1)
            p95_latency_ms = latencies[p95_index]
        else:
            p95_latency_ms = 0

        one_hour_ago = now - timedelta(hours=1)
        hourly_cost_usd = round(
            sum(
                float((task.usage_json or {}).get("estimated_cost_usd", 0.0) or 0.0)
                for task in tasks
                if task.created_at and self._as_utc(task.created_at) >= one_hour_ago
            ),
            4,
        )

        project_qa_tasks = [task for task in tasks if task.route_type == "project_qa"]
        rag_miss_rate = (
            sum(
                1
                for task in project_qa_tasks
                if not (task.retrieval_trace_json or {}).get("retrieved_docs")
            )
            / len(project_qa_tasks)
            if project_qa_tasks
            else 0.0
        )

        kb_failure_rate = 0.0
        if latest_job and isinstance(latest_job.stats_json, dict):
            failed = int(latest_job.stats_json.get("failed", 0) or 0)
            sources = int(latest_job.stats_json.get("sources", 0) or 0)
            kb_failure_rate = failed / sources if sources else 0.0

        oldest_pending_age_minutes = 0
        if pending_proposals:
            oldest_pending = min(
                (self._as_utc(item.created_at) for item in pending_proposals if item.created_at),
                default=None,
            )
            if oldest_pending:
                oldest_pending_age_minutes = int((now - oldest_pending).total_seconds() / 60)

        items = [
            self._build_alert(
                alert_id="error_rate_high",
                current_value=round(error_rate, 4),
                threshold=self.settings.alert_error_rate_threshold,
                active=error_rate >= self.settings.alert_error_rate_threshold,
                message="Task failure rate is above the configured threshold.",
            ),
            self._build_alert(
                alert_id="p95_latency_high",
                current_value=p95_latency_ms,
                threshold=self.settings.alert_p95_latency_ms,
                active=p95_latency_ms >= self.settings.alert_p95_latency_ms,
                message="P95 task latency is above the configured threshold.",
            ),
            self._build_alert(
                alert_id="hourly_cost_high",
                current_value=hourly_cost_usd,
                threshold=self.settings.alert_hourly_cost_usd,
                active=hourly_cost_usd >= self.settings.alert_hourly_cost_usd,
                message="Hourly model cost is above the configured threshold.",
            ),
            self._build_alert(
                alert_id="rag_miss_rate_high",
                current_value=round(rag_miss_rate, 4),
                threshold=self.settings.alert_rag_miss_rate,
                active=rag_miss_rate >= self.settings.alert_rag_miss_rate,
                message="Project-QA retrieval miss rate is above the configured threshold.",
            ),
            self._build_alert(
                alert_id="kb_import_failure_rate_high",
                current_value=round(kb_failure_rate, 4),
                threshold=self.settings.alert_kb_import_failure_rate,
                active=kb_failure_rate >= self.settings.alert_kb_import_failure_rate,
                message="Knowledge-base import failure rate is above the configured threshold.",
            ),
            self._build_alert(
                alert_id="proposal_backlog_high",
                current_value=len(pending_proposals),
                threshold=self.settings.alert_pending_proposals_threshold,
                active=len(pending_proposals) >= self.settings.alert_pending_proposals_threshold,
                message="Pending proposal backlog is above the configured threshold.",
            ),
            self._build_alert(
                alert_id="proposal_age_high",
                current_value=oldest_pending_age_minutes,
                threshold=self.settings.alert_pending_proposal_age_minutes,
                active=oldest_pending_age_minutes >= self.settings.alert_pending_proposal_age_minutes,
                message="The oldest pending proposal has been waiting too long.",
            ),
        ]
        active_items = [item for item in items if item["active"]]
        return {
            "summary": {
                "tasks_checked": total_tasks,
                "project_qa_tasks_checked": len(project_qa_tasks),
                "pending_proposals": len(pending_proposals),
                "oldest_pending_age_minutes": oldest_pending_age_minutes,
                "hourly_cost_usd": hourly_cost_usd,
                "p95_latency_ms": p95_latency_ms,
                "error_rate": round(error_rate, 4),
                "rag_miss_rate": round(rag_miss_rate, 4),
                "kb_import_failure_rate": round(kb_failure_rate, 4),
                "active_alerts": len(active_items),
            },
            "items": items,
        }

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _build_alert(
        self,
        *,
        alert_id: str,
        current_value: int | float,
        threshold: int | float,
        active: bool,
        message: str,
    ) -> dict:
        return {
            "alert_id": alert_id,
            "active": active,
            "severity": "warning" if active else "ok",
            "current_value": current_value,
            "threshold": threshold,
            "message": message,
        }
