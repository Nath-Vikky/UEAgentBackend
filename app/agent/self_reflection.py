from __future__ import annotations

from typing import Any


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _check(check_id: str, status: str, summary: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def build_self_reflection(
    *,
    route_type: str,
    output_language: str,
    answer_text: str,
    confidence: float,
    answer_generation_mode: str,
    retrieved_docs: list[dict[str, Any]] | None = None,
    inventory_items: list[dict[str, Any]] | None = None,
    project_file_result: dict[str, Any] | None = None,
    live_llm_used: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    retrieved_count = len(retrieved_docs or [])
    inventory_count = len(inventory_items or [])
    project_file_status = (project_file_result or {}).get("status")
    project_file_used = project_file_status == "completed"
    evidence_count = retrieved_count + inventory_count + (1 if project_file_used else 0)
    warning_items = list(warnings or [])

    checks = [
        _check(
            "answer_present",
            "passed" if answer_text.strip() else "failed",
            _localized(
                output_language,
                "回答文本已生成。" if answer_text.strip() else "回答文本为空。",
                "Answer text is present." if answer_text.strip() else "Answer text is empty.",
            ),
        ),
        _check(
            "evidence_available",
            "passed" if evidence_count > 0 or route_type == "direct_answer" else "warning",
            _localized(
                output_language,
                f"可用证据数量：{evidence_count}。",
                f"Available evidence count: {evidence_count}.",
            ),
            {
                "retrieved_count": retrieved_count,
                "inventory_count": inventory_count,
                "project_file_used": project_file_used,
            },
        ),
        _check(
            "confidence_floor",
            "passed" if confidence >= 0.4 or route_type == "direct_answer" else "warning",
            _localized(
                output_language,
                f"当前置信度：{confidence:.2f}。",
                f"Current confidence: {confidence:.2f}.",
            ),
        ),
    ]

    if warning_items:
        checks.append(
            _check(
                "degraded_warnings",
                "warning",
                _localized(
                    output_language,
                    f"存在 {len(warning_items)} 条降级或警告信息。",
                    f"There are {len(warning_items)} degraded/warning item(s).",
                ),
                {"warnings": warning_items},
            )
        )

    recommendations: list[str] = []
    grounding_level = "project_grounded"
    status = "passed"
    if not answer_text.strip():
        status = "needs_context"
        grounding_level = "insufficient_answer"
        recommendations.append(
            _localized(output_language, "请补充更具体的问题或重新提交项目上下文。", "Provide a more specific question or refresh project context.")
        )
    elif route_type == "project_qa" and evidence_count == 0:
        status = "needs_context"
        grounding_level = "insufficient_evidence"
        recommendations.append(
            _localized(output_language, "建议刷新知识库、提交 Project Inventory，或让前端传入当前文件。", "Refresh the KB, submit Project Inventory, or pass the current file from the frontend.")
        )
    elif route_type == "project_qa" and confidence < 0.4:
        status = "needs_context"
        grounding_level = "low_confidence"
        recommendations.append(
            _localized(output_language, "当前证据置信度偏低，建议补充更精确的关键词或项目资料。", "Evidence confidence is low; add more precise keywords or project material.")
        )
    elif route_type == "direct_answer":
        grounding_level = "general_llm" if live_llm_used else "fallback"
        status = "passed" if live_llm_used else "degraded"
        if not live_llm_used:
            recommendations.append(
                _localized(output_language, "配置 LLM 后普通聊天会得到更自然的回答。", "Configure an LLM for more natural direct chat responses.")
            )
    elif warning_items:
        status = "degraded"

    return {
        "version": "self_reflection_v1",
        "status": status,
        "grounding_level": grounding_level,
        "answer_generation_mode": answer_generation_mode,
        "confidence": confidence,
        "evidence_counts": {
            "retrieved_docs": retrieved_count,
            "inventory_items": inventory_count,
            "project_file_used": 1 if project_file_used else 0,
        },
        "checks": checks,
        "recommendations": recommendations,
    }
