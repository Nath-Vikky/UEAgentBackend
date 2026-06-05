from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.agent.self_reflection import build_self_reflection
from app.agent.tool_planner import (
    build_project_qa_deterministic_tool_plan,
    build_project_qa_result_contracts,
    build_react_lite_tool_plan,
    build_react_lite_trace,
    tool_call_input,
)
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext
from app.services.task_handlers.view_helpers import citation_previews
from app.tools.context import ToolContext
from app.tools.executor_runtime import execute_tool_with_context
from app.tools.project_file import (
    project_file_candidate,
    project_file_fallback_answer,
)
from app.tools.registry import get_tool_spec


def _focus_inventory_query_kwargs(context_bundle: dict[str, Any]) -> dict[str, Any]:
    active_context = dict(context_bundle.get("active_context") or {})
    level_actor = dict(active_context.get("level_actor") or {})
    material = dict(active_context.get("material") or {})
    return {
        "selected_actor_references": [
            str(item or "").strip()
            for item in list(level_actor.get("selected_actor_references") or [])
            if str(item or "").strip()
        ],
        "current_actor_reference": str(level_actor.get("current_actor_reference") or "").strip() or None,
        "selected_material_instance_paths": [
            str(item or "").strip()
            for item in list(material.get("selected_material_instance_paths") or [])
            if str(item or "").strip()
        ],
        "current_material_instance_path": str(material.get("current_material_instance_path") or "").strip() or None,
    }


class ProjectQAHandler:
    """Runs Project QA over KB, local search, inventory, file reads, and LLM synthesis."""

    handler_id = "project_qa"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language
        stream_sink = context.stream_sink

        query = request.payload.get("user_query") or (
            request.session.messages[-1].content if request.session.messages else ""
        )
        query_text = str(query)
        deterministic_tool_plan = build_project_qa_deterministic_tool_plan(query=query_text, routing=routing)
        tool_plan = build_react_lite_tool_plan(
            request=request,
            query=query_text,
            deterministic_plan=deterministic_tool_plan,
            chat_config=context.chat_config,
            llm_service=host.llm_service,
            output_language_label=_language_label(output_language),
            rag_top_k=host.settings.rag_top_k,
        )
        if tool_plan["use_knowledge"]:
            host._emit_stream_event(
                stream_sink,
                "tool_call",
                {"tool_id": "retrieve_project_knowledge", "query": query_text},
                run_id=context.run_id,
                task_id=context.task_id,
            )
        qa_result = (
            host.kb_service.project_qa(
                query=query_text,
                context=request.context,
                payload=request.payload,
                output_language=output_language,
                source_task_id=context.task_id,
            )
            if tool_plan["use_knowledge"]
            else host._empty_project_qa_result(query=query_text)
        )
        if tool_plan["use_knowledge"]:
            host._emit_stream_event(
                stream_sink,
                "tool_result",
                {
                    "tool_id": "retrieve_project_knowledge",
                    "status": "completed",
                    "matched_count": len(qa_result.get("retrieved_docs", [])),
                },
                run_id=context.run_id,
                task_id=context.task_id,
            )
        if tool_plan["use_inventory"]:
            host._emit_stream_event(
                stream_sink,
                "tool_call",
                {"tool_id": "query_project_inventory", "query": query_text},
                run_id=context.run_id,
                task_id=context.task_id,
            )
        inventory_tool_input = tool_call_input(tool_plan, "query_project_inventory")
        inventory_fields = inventory_tool_input.get("fields")
        if not isinstance(inventory_fields, list):
            inventory_fields = []
        focus_inventory_kwargs = _focus_inventory_query_kwargs(context.context_bundle)
        selected_actor_references = inventory_tool_input.get("selected_actor_references")
        if not isinstance(selected_actor_references, list):
            selected_actor_references = focus_inventory_kwargs["selected_actor_references"]
        selected_material_instance_paths = inventory_tool_input.get("selected_material_instance_paths")
        if not isinstance(selected_material_instance_paths, list):
            selected_material_instance_paths = focus_inventory_kwargs["selected_material_instance_paths"]
        inventory_result = (
            host.inventory_service.query(
                query=str(inventory_tool_input.get("query") or query_text),
                project_id=str(
                    inventory_tool_input.get("project_id") or host._inventory_project_id(request) or ""
                ),
                asset_path=str(inventory_tool_input.get("asset_path") or ""),
                asset_type=str(inventory_tool_input.get("asset_type") or "") or None,
                fields=[str(item) for item in inventory_fields],
                selected_assets=list(request.context.selected_assets or []),
                selected_actor_references=[str(item) for item in selected_actor_references],
                current_actor_reference=(
                    str(
                        inventory_tool_input.get("current_actor_reference")
                        or focus_inventory_kwargs["current_actor_reference"]
                        or ""
                    ).strip()
                    or None
                ),
                selected_material_instance_paths=[str(item) for item in selected_material_instance_paths],
                current_material_instance_path=(
                    str(
                        inventory_tool_input.get("current_material_instance_path")
                        or focus_inventory_kwargs["current_material_instance_path"]
                        or ""
                    ).strip()
                    or None
                ),
                limit=int(inventory_tool_input.get("limit") or 8),
            )
            if tool_plan["use_inventory"]
            else host._empty_inventory_result(query=query_text)
        )
        if tool_plan["use_inventory"]:
            host._emit_stream_event(
                stream_sink,
                "tool_result",
                {
                    "tool_id": "query_project_inventory",
                    "status": "completed",
                    "matched_count": len(inventory_result.get("items", [])),
                },
                run_id=context.run_id,
                task_id=context.task_id,
            )
        if tool_plan["use_project_file"]:
            host._emit_stream_event(
                stream_sink,
                "tool_call",
                {
                    "tool_id": "read_project_file",
                    "file_path": project_file_candidate(request)["file_path"],
                },
                run_id=context.run_id,
                task_id=context.task_id,
            )
        if tool_plan["use_project_file"]:
            project_file_spec = get_tool_spec("read_project_file")
            assert project_file_spec is not None
            project_file_context = ToolContext(
                tool_id="read_project_file",
                task_id=context.task_id,
                run_id=context.run_id,
                trace_id=context.trace_id,
                user_query=query_text,
                payload=tool_call_input(tool_plan, "read_project_file") or project_file_candidate(request),
                active_context=request.context.model_dump(mode="json"),
                runtime_options=request.runtime_options.model_dump(mode="json"),
                timeout_ms=project_file_spec.timeout_ms,
                metadata={"source": "project_qa"},
            )
            project_file_tool_result = execute_tool_with_context(project_file_context)
            project_file_result = project_file_tool_result.output
        else:
            project_file_context = None
            project_file_tool_result = None
            project_file_result = {
                "status": "skipped",
                "reason": "tool_plan_skipped_project_file_read",
                "file_path": project_file_candidate(request)["file_path"],
            }
        if tool_plan["use_project_file"]:
            host._emit_stream_event(
                stream_sink,
                "tool_result",
                {
                    "tool_id": "read_project_file",
                    "status": project_file_result.get("status", "skipped"),
                    "file_path": project_file_result.get("file_path"),
                    "bytes_read": project_file_result.get("bytes_read"),
                },
                run_id=context.run_id,
                task_id=context.task_id,
            )
        qa_result["inventory_items"] = inventory_result["items"]
        qa_result["inventory_summary"] = inventory_result["summary"]
        qa_result["project_file"] = project_file_result
        inventory_freshness = dict((inventory_result.get("summary") or {}).get("freshness") or {})
        if tool_plan["use_inventory"] and inventory_freshness.get("status") == "stale":
            qa_result["warnings"] = list(qa_result.get("warnings") or [])
            if "project_inventory_snapshot_stale" not in qa_result["warnings"]:
                qa_result["warnings"].append("project_inventory_snapshot_stale")
        base_debug = host._base_debug(
            request=request,
            routing=routing,
            trace_id=context.trace_id,
            context_bundle=context.context_bundle,
        )
        llm_result = {
            "ok": False,
            "reason": "not_attempted",
            "error": "",
            "provider": "openai_compatible",
            "model": context.chat_config.model,
            "profile_id": context.chat_config.profile_id,
            "usage": {},
        }
        answer_generation_mode = qa_result.get("answer_mode") or "retrieval_summary_fallback"
        if tool_plan["use_inventory"]:
            inventory_requires_snapshot = host._inventory_fact_query_requires_snapshot(query_text)
            if inventory_result["items"]:
                qa_result["answer"] = host._inventory_fallback_answer(
                    inventory_result=inventory_result,
                    output_language=output_language,
                )
                qa_result["confidence"] = max(float(qa_result["confidence"]), 0.72)
                answer_generation_mode = "inventory_summary_fallback"
            elif inventory_requires_snapshot:
                qa_result["answer"] = host._inventory_fallback_answer(
                    inventory_result=inventory_result,
                    output_language=output_language,
                )
                fallback_confidence = 0.25 if inventory_result["summary"].get("has_snapshot") else 0.12
                qa_result["confidence"] = fallback_confidence
                qa_result["sources"] = []
                qa_result["citations"] = []
                qa_result["retrieved_docs"] = []
                qa_result["warnings"] = list(qa_result.get("warnings") or [])
                qa_result["warnings"].append(
                    "inventory_no_matching_items"
                    if inventory_result["summary"].get("has_snapshot")
                    else "inventory_snapshot_required"
                )
                quality_gate = dict(qa_result.get("retrieval_quality_gate") or {})
                quality_gate.update(
                    {
                        "status": "warning",
                        "evidence_sufficient": False,
                        "evidence_insufficient": True,
                        "reason": "inventory_snapshot_required",
                        "retrieved_count": 0,
                        "rag_retrieved_count": 0,
                        "local_retrieved_count": 0,
                    }
                )
                qa_result["retrieval_quality_gate"] = quality_gate
                retrieval_trace = dict(qa_result.get("retrieval_trace") or {})
                retrieval_trace["retrieved_docs"] = []
                retrieval_trace["reason"] = "inventory_snapshot_required"
                retrieval_trace["retrieval_quality_gate"] = quality_gate
                qa_result["retrieval_trace"] = retrieval_trace
                answer_generation_mode = "inventory_summary_fallback"
        if (
            answer_generation_mode == "retrieval_summary_fallback"
            and not qa_result.get("answer")
            and project_file_result.get("status") != "skipped"
        ):
            qa_result["answer"] = project_file_fallback_answer(
                project_file_result=project_file_result,
                output_language=output_language,
            )
            answer_generation_mode = "project_file_fallback"
            qa_result["confidence"] = max(
                float(qa_result["confidence"]),
                0.55 if project_file_result.get("status") == "completed" else 0.25,
            )
        has_project_file_context = project_file_result.get("status") == "completed"
        if answer_generation_mode != "knowledge_catalog" and (
            qa_result["retrieved_docs"] or inventory_result["items"] or has_project_file_context
        ):
            complete_kwargs: dict[str, Any] = {
                "messages": host._project_qa_messages(
                    request=request,
                    query=query_text,
                    qa_result=qa_result,
                    project_file_result=project_file_result,
                    output_language=output_language,
                    context_bundle=context.context_bundle,
                ),
                "config": context.chat_config,
            }
            if stream_sink:
                complete_kwargs["stream_sink"] = (
                    lambda text_delta: host._emit_stream_event(
                        stream_sink,
                        "assistant_delta",
                        {"text": text_delta},
                        run_id=context.run_id,
                        task_id=context.task_id,
                    )
                )
            llm_result = host.llm_service.complete(**complete_kwargs)
            if llm_result["ok"]:
                qa_result["answer"] = llm_result["text"]
                answer_generation_mode = "llm_synthesized"

        react_loop = build_react_lite_trace(
            query=query_text,
            tool_plan=tool_plan,
            qa_result=qa_result,
            inventory_result=inventory_result,
            project_file_result=project_file_result,
            answer_generation_mode=answer_generation_mode,
            rag_top_k=host.settings.rag_top_k,
        )
        result_contracts = build_project_qa_result_contracts(
            tool_plan=tool_plan,
            qa_result=qa_result,
            inventory_result=inventory_result,
            project_file_result=project_file_result,
        )
        self_reflection = build_self_reflection(
            route_type="project_qa",
            output_language=output_language,
            answer_text=str(qa_result.get("answer") or ""),
            confidence=float(qa_result.get("confidence") or 0.0),
            answer_generation_mode=answer_generation_mode,
            retrieved_docs=qa_result.get("retrieved_docs", []),
            inventory_items=inventory_result.get("items", []),
            project_file_result=project_file_result,
            live_llm_used=bool(llm_result.get("ok")),
            warnings=qa_result.get("warnings", []),
        )

        confidence = qa_result["confidence"]
        step_results = [
            {
                "step_id": "classify_intent",
                "title": "Intent Classification",
                "status": "completed",
                "summary": routing["intent"]["reason"],
                "details": routing["intent"],
            },
            {
                "step_id": "retrieve_knowledge",
                "title": "Knowledge Retrieval",
                "status": "completed" if tool_plan["use_knowledge"] else "skipped",
                "summary": _localized(
                    output_language,
                    (
                        f"检索到 {len(qa_result['retrieved_docs'])} 个相关片段。"
                        if tool_plan["use_knowledge"]
                        else "本次问题优先查询项目快照，未触发知识库检索。"
                    ),
                    (
                        f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunks."
                        if tool_plan["use_knowledge"]
                        else "This question used project inventory first, so knowledge retrieval was not triggered."
                    ),
                ),
                "details": qa_result["retrieval_trace"],
            },
            {
                "step_id": "query_project_inventory",
                "title": "Project Inventory Query",
                "status": "completed" if tool_plan["use_inventory"] else "skipped",
                "summary": _localized(
                    output_language,
                    (
                        f"命中 {len(inventory_result['items'])} 条项目快照记录。"
                        if tool_plan["use_inventory"]
                        else "本次问题未选择 Project Inventory 工具。"
                    ),
                    (
                        f"Matched {len(inventory_result['items'])} project inventory item(s)."
                        if tool_plan["use_inventory"]
                        else "Project Inventory was not selected for this question."
                    ),
                ),
                "details": inventory_result["summary"],
            },
            {
                "step_id": "read_project_file",
                "title": "Read Project File",
                "status": project_file_result.get("status", "skipped")
                if tool_plan["use_project_file"]
                else "skipped",
                "summary": _localized(
                    output_language,
                    (
                        f"读取项目文件：{project_file_result.get('file_path')}。"
                        if project_file_result.get("status") == "completed"
                        else f"未读取项目文件：{project_file_result.get('reason') or 'not_selected'}。"
                    ),
                    (
                        f"Read project file: {project_file_result.get('file_path')}."
                        if project_file_result.get("status") == "completed"
                        else f"Did not read a project file: {project_file_result.get('reason') or 'not_selected'}."
                    ),
                ),
                "details": {
                    key: value
                    for key, value in project_file_result.items()
                    if key != "text_excerpt"
                },
            },
            {
                "step_id": "compose_answer",
                "title": "Answer Composition",
                "status": "completed",
                "summary": (
                    _localized(
                        output_language,
                        "已使用配置好的聊天模型整合检索证据并生成回答。",
                        "Synthesized the answer from retrieved evidence with the configured chat model.",
                    )
                    if llm_result["ok"]
                    else _localized(
                        output_language,
                        "当前未使用在线聊天模型，直接返回检索摘要作为项目问答结果。",
                        "Returned the retrieval summary directly because no live chat model was used.",
                    )
                ),
                "details": {
                    "confidence": qa_result["confidence"],
                    "sources": qa_result["sources"],
                    "answer_generation_mode": answer_generation_mode,
                    "llm_reason": llm_result["reason"],
                    "model": llm_result["model"],
                    "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
                },
            },
        ]
        quick_actions = [
            QuickAction(
                action_id="refresh_kb" if confidence < 0.4 else "inspect_debug_view",
                label=_localized(
                    output_language,
                    "刷新知识库" if confidence < 0.4 else "查看调试信息",
                    "Refresh knowledge base" if confidence < 0.4 else "Open debug view",
                ),
            ).model_dump(mode="json")
        ]
        evidence_terms = host._project_qa_evidence_terms(qa_result.get("retrieved_docs", []))
        if evidence_terms and answer_generation_mode != "llm_synthesized":
            evidence_text = _localized(
                output_language,
                "证据关键词：" + ", ".join(evidence_terms),
                "Evidence highlights: " + ", ".join(evidence_terms),
            )
            if evidence_text not in str(qa_result.get("answer") or ""):
                qa_result["answer"] = f"{qa_result['answer']}\n\n{evidence_text}"
        user_view = {
            "title": _localized(output_language, "项目问答结果", "Project QA Result"),
            "text": qa_result["answer"],
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "检索摘要", "Retrieval Summary"),
                    text=_localized(
                        output_language,
                        f"命中 {len(qa_result['retrieved_docs'])} 个知识库片段、{len(inventory_result['items'])} 条项目快照记录、项目文件读取状态 {project_file_result.get('status')}，当前置信度 {confidence:.2f}。",
                        f"Retrieved {len(qa_result['retrieved_docs'])} KB chunk(s), {len(inventory_result['items'])} inventory item(s), project file status {project_file_result.get('status')}, with confidence {confidence:.2f}.",
                    ),
                    data={
                        "confidence": confidence,
                        "kb_chunk_count": len(qa_result["retrieved_docs"]),
                        "inventory_item_count": len(inventory_result["items"]),
                        "project_file_status": project_file_result.get("status"),
                        "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
                    },
                ).model_dump(mode="json")
            ],
            "citations_preview": citation_previews(qa_result["citations"]),
            "quick_actions": quick_actions,
            "status_hint": "low_confidence" if confidence < 0.4 else "evidence_retrieved",
        }
        data = {
            "answer": qa_result["answer"],
            "sources": qa_result["sources"],
            "confidence": qa_result["confidence"],
            "retrieved_docs": qa_result["retrieved_docs"],
            "filters_applied": qa_result["filters_applied"],
            "citations": qa_result["citations"],
            "warnings": qa_result["warnings"],
            "answer_mode": qa_result.get("answer_mode", answer_generation_mode),
            "catalog": qa_result.get("catalog", {}),
            "local_search": qa_result.get("local_search", {}),
            "web_memory": qa_result.get("web_memory", {}),
            "web_memory_store": qa_result.get("web_memory_store", {}),
            "web_search": qa_result.get("web_search", {}),
            "source_arbitration": qa_result.get("source_arbitration", {}),
            "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
            "knowledge_curation": qa_result.get("knowledge_curation", {}),
            "inventory": inventory_result,
            "project_file": project_file_result,
            "answer_generation": {
                "mode": answer_generation_mode,
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": context.chat_config.profile_id,
            },
            "react_loop": react_loop,
            "tool_plan": tool_plan,
            "tool_contracts": {
                "input_contracts": tool_plan.get("input_contracts", []),
                "result_contracts": result_contracts,
            },
            "self_reflection": self_reflection,
            "context_summary": build_context_summary(request),
            "context_bundle": context.context_bundle,
        }
        base_debug["retrieval"] = qa_result["retrieval_trace"]
        base_debug["local_search"] = qa_result.get("local_search", {})
        base_debug["web_memory"] = qa_result.get("web_memory", {})
        base_debug["web_memory_store"] = qa_result.get("web_memory_store", {})
        base_debug["web_search"] = qa_result.get("web_search", {})
        base_debug["source_arbitration"] = qa_result.get("source_arbitration", {})
        base_debug["retrieval_quality_gate"] = qa_result.get("retrieval_quality_gate", {})
        base_debug["knowledge_curation"] = qa_result.get("knowledge_curation", {})
        base_debug["inventory"] = inventory_result
        base_debug["project_file"] = {
            key: value for key, value in project_file_result.items() if key != "text_excerpt"
        }
        if project_file_tool_result is not None:
            base_debug["project_file_tool_result"] = project_file_tool_result.to_debug_entry(
                context=project_file_context
            )
        base_debug["tools"] = [
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed" if tool_plan["use_knowledge"] else "skipped",
                "summary": (
                    f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunk(s)."
                    if tool_plan["use_knowledge"]
                    else "Skipped by Project QA tool plan."
                ),
            },
            {
                "tool_id": "query_project_inventory",
                "status": "completed" if tool_plan["use_inventory"] else "skipped",
                "summary": (
                    f"Matched {len(inventory_result['items'])} project inventory item(s)."
                    if tool_plan["use_inventory"]
                    else "Skipped by Project QA tool plan."
                ),
            },
            {
                "tool_id": "read_project_file",
                "status": (
                    project_file_result.get("status", "skipped")
                    if tool_plan["use_project_file"]
                    else "skipped"
                ),
                "summary": (
                    f"Read project file {project_file_result.get('file_path')}."
                    if project_file_result.get("status") == "completed"
                    else f"Skipped or blocked project file read ({project_file_result.get('reason')})."
                ),
            },
            {
                "tool_id": "llm_answer_synthesis",
                "status": "completed" if llm_result["ok"] else "skipped",
                "summary": (
                    f"Used model {llm_result['model']} for final answer synthesis."
                    if llm_result["ok"]
                    else f"Skipped live answer synthesis ({llm_result['reason']})."
                ),
            },
        ]
        web_search_result = qa_result.get("web_search") or {}
        if web_search_result.get("status") != "skipped":
            base_debug["tools"].append(
                {
                    "tool_id": "web_search_knowledge",
                    "status": web_search_result.get("status", "skipped"),
                    "summary": (
                        f"Controlled Web Search returned {len(web_search_result.get('items', []))} result(s)."
                        if web_search_result.get("status") == "completed"
                        else f"Controlled Web Search failed or degraded ({web_search_result.get('reason', 'unknown')})."
                    ),
                }
            )
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["tool_plan"] = tool_plan
        base_debug["tool_contracts"] = {
            "input_contracts": tool_plan.get("input_contracts", []),
            "result_contracts": result_contracts,
        }
        base_debug["react_loop"] = react_loop
        base_debug["self_reflection"] = self_reflection
        base_debug["warnings"] = qa_result["warnings"] + (
            [] if llm_result["ok"] or llm_result["reason"] == "not_attempted" else [llm_result["reason"]]
        )
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": qa_result["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": qa_result["answer"],
            "artifacts": [],
            "usage": llm_result["usage"],
        }


def _language_label(language: str) -> str:
    return "Simplified Chinese" if language.startswith("zh") else "English"
