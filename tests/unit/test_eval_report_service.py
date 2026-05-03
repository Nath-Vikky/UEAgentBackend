from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.core.settings import Settings
from app.services.eval_report_service import EvalReportService


def _runtime_root() -> Path:
    root = Path("storage") / "test-eval-report-service" / uuid.uuid4().hex
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_eval_report_service_lists_and_reads_local_reports() -> None:
    root = _runtime_root()
    evals_dir = root / "artifacts" / "evals"
    evals_dir.mkdir(parents=True)
    report_path = evals_dir / "project-benchmark-latest.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-03T10:00:00+00:00",
                "rag_summary": {"hit_at_k": 0.8},
                "task_summary": {"pass_rate": 0.9},
                "performance": {"p95_latency_ms": 1200},
                "cases": [{"case_id": "case_1"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path.with_suffix(".md").write_text("# Benchmark\n\nReadable report.", encoding="utf-8")

    service = EvalReportService(Settings(artifact_dir=str(root / "artifacts")))
    listing = service.list_reports()
    detail = service.get_report("project-benchmark-latest.json")

    assert listing["summary"]["report_count"] == 1
    assert listing["items"][0]["report_type"] == "project_benchmark"
    assert listing["items"][0]["summary"]["rag_summary"]["hit_at_k"] == 0.8
    assert detail is not None
    assert detail["item"]["markdown_path"].endswith("project-benchmark-latest.md")
    assert detail["markdown_preview"].startswith("# Benchmark")


def test_eval_report_service_rejects_path_traversal() -> None:
    root = _runtime_root()
    service = EvalReportService(Settings(artifact_dir=str(root / "artifacts")))

    assert service.get_report("../project-benchmark-latest.json") is None
    assert service.get_report("project-benchmark-latest.md") is None
