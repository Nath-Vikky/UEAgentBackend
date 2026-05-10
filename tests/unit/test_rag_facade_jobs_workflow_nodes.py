from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.settings import Settings
from app.rag import retrieve_knowledge
from app.rag.ingestion.jobs import InProcessIngestionJobQueue
from app.schemas.requests import ContextInput
from app.workflows.nodes import (
    aggregate_step_results_node,
    append_step_result_node,
    record_tool_output_node,
)
from app.workflows.state import WorkflowState


def _chunk(*, chunk_id: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        chunk_id=chunk_id,
        doc_id="doc_demo",
        title="Demo Doc",
        source_path="knowledge/demo.md",
        domain="engine_notes",
        section_path="Demo",
        text=text,
        metadata_json={},
        module=None,
        doc_type="reference",
    )


def test_rag_facade_returns_retrieval_result_without_agentic_round() -> None:
    settings = Settings(
        openai_api_key="",
        embedding_enabled=False,
        rag_mode="lexical",
        rag_top_k=2,
    )
    result = retrieve_knowledge(
        query="Actor lifecycle BeginPlay",
        context=ContextInput(project_name="DemoProject"),
        payload={"domain_filters": ["engine_notes"]},
        chunks=[_chunk(chunk_id="chunk_a", text="Actor lifecycle uses BeginPlay and Tick.")],
        settings=settings,
        output_language="en-US",
        use_agentic=False,
    )

    assert result["result"].retrieved_docs
    assert result["agentic_rag"]["enabled"] is False
    assert result["warnings"] == result["result"].warnings


def test_in_process_ingestion_job_queue_tracks_lifecycle() -> None:
    async def _run() -> None:
        queue = InProcessIngestionJobQueue()
        queued = await queue.enqueue({"source_paths": ["knowledge"]}, job_id="job_demo")
        assert queued.status == "queued"

        running = await queue.next_job()
        assert running.job_id == "job_demo"
        assert running.status == "running"

        completed = queue.complete("job_demo", {"document_count": 2})
        assert completed.status == "completed"
        assert completed.result == {"document_count": 2}
        assert queue.snapshot()[0]["status"] == "completed"

    asyncio.run(_run())


def test_workflow_nodes_record_steps_tools_and_summary() -> None:
    state = WorkflowState(
        run_id="run_demo",
        task_id="task_demo",
        session_id="session_demo",
        task_type="code_review",
        raw_input={},
    )

    append_step_result_node(
        state,
        step_id="collect",
        title="Collect",
        summary="Collected inputs.",
    )
    record_tool_output_node(state, tool_id="review_ue_cpp_files", output={"issue_count": 1})
    aggregate_step_results_node(state)

    assert state.step_results[0]["step_id"] == "collect"
    assert state.tool_outputs["review_ue_cpp_files"]["issue_count"] == 1
    assert state.tool_outputs["workflow_summary"]["step_count"] == 1
    assert state.tool_outputs["workflow_summary"]["status_counts"] == {"completed": 1}
