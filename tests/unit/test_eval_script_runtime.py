from __future__ import annotations

from app.core.settings import get_settings
from scripts.run_project_benchmark import _isolated_runtime as project_benchmark_runtime
from scripts.run_task_eval import _isolated_runtime as task_eval_runtime


def test_project_benchmark_runtime_aligns_kb_source_paths(monkeypatch) -> None:
    monkeypatch.setenv("KB_SOURCE_PATHS", "../external-only")
    get_settings.cache_clear()

    with project_benchmark_runtime(
        source_paths=["./README.md", "./docs", "./knowledge"],
        use_live_llm=False,
    ):
        settings = get_settings()
        assert settings.kb_source_paths == ["./README.md", "./docs", "./knowledge"]
        assert settings.rag_mode == "lexical"

    get_settings.cache_clear()


def test_task_eval_runtime_aligns_kb_source_paths(monkeypatch) -> None:
    monkeypatch.setenv("KB_SOURCE_PATHS", "../external-only")
    get_settings.cache_clear()

    with task_eval_runtime(source_paths=["./README.md", "./docs"]):
        settings = get_settings()
        assert settings.kb_source_paths == ["./README.md", "./docs"]

    get_settings.cache_clear()
