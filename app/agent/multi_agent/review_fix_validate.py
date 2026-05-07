from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.multi_agent.chain import run_timed_node
from app.agent.multi_agent.schemas import AgentChainResult, AgentNodeResult, DecisionGate
from app.schemas.common import CitationPreview, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService
from app.skills.executors import CodeGenerateSkillExecutor, CodeReviewSkillExecutor
from app.tools.code_review import review_ue_cpp_files


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _citation_previews(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        CitationPreview(
            title=item["title"],
            source=item["source"],
            snippet=item.get("snippet"),
        ).model_dump(mode="json")
        for item in citations[:3]
    ]


def _severity_score(summary: dict[str, Any]) -> int:
    return int(summary.get("high") or 0) * 4 + int(summary.get("medium") or 0) * 2 + int(summary.get("low") or 0)


def should_generate_fix_draft(severity_summary: dict[str, Any]) -> DecisionGate:
    high = int(severity_summary.get("high") or 0)
    medium = int(severity_summary.get("medium") or 0)
    low = int(severity_summary.get("low") or 0)
    if high > 0:
        return DecisionGate(
            gate_id="review_to_fix",
            status="passed",
            reason="high_severity_findings",
            details={"high": high, "medium": medium, "low": low, "threshold": "high > 0 or medium >= 3"},
        )
    if medium >= 3:
        return DecisionGate(
            gate_id="review_to_fix",
            status="passed",
            reason="multiple_medium_findings",
            details={"high": high, "medium": medium, "low": low, "threshold": "high > 0 or medium >= 3"},
        )
    return DecisionGate(
        gate_id="review_to_fix",
        status="skipped",
        reason="below_fix_generation_threshold",
        details={"high": high, "medium": medium, "low": low, "threshold": "high > 0 or medium >= 3"},
    )


def _generated_code_bundle(generated_items: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for item in generated_items[:6]:
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        path = str(item.get("file_path") or item.get("label") or "generated")
        sections.append(f"// File: {path}\n{code}")
    return "\n\n".join(sections)


def _chain_summary_text(
    *,
    output_language: str,
    review_summary: dict[str, Any],
    generated_count: int,
    validation_issue_count: int,
    gate: DecisionGate,
) -> str:
    issue_count = sum(int(review_summary.get(key) or 0) for key in ("high", "medium", "low"))
    if gate.status == "passed":
        return _localized(
            output_language,
            f"已完成多阶段代码审查链：发现 {issue_count} 个规则风险，生成 {generated_count} 个非破坏式修复草案，并完成草案校验。",
            f"Multi-agent code review chain completed: found {issue_count} rule finding(s), generated {generated_count} non-destructive fix draft file(s), and validated the draft.",
        )
    return _localized(
        output_language,
        f"已完成多阶段代码审查链：发现 {issue_count} 个规则风险，未达到自动生成修复草案阈值，本次仅输出审查与验证建议。",
        f"Multi-agent code review chain completed: found {issue_count} rule finding(s), below fix-generation threshold, so only review and validation advice was returned.",
    )


@dataclass(slots=True)
class ReviewFixValidateChain:
    kb_service: KnowledgeBaseService
    llm_service: LLMService
    base_debug_builder: Callable[..., dict[str, Any]]

    def run(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chain_result = AgentChainResult(chain_id="review_fix_validate", status="running")

        review_execution, review_node = run_timed_node(
            node_id="review",
            role="ReviewerAgent",
            input_summary="Run deterministic UE C++ review with optional LLM synthesis.",
            runner=lambda: self._run_review(
                request=request,
                routing=routing,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                output_language=output_language,
                chat_config=chat_config,
                context_bundle=context_bundle,
            ),
            output_summary=self._review_output_summary,
            data_summary=self._review_data_summary,
            warnings=lambda item: list((item.get("data") or {}).get("warnings") or []),
        )
        chain_result.phase_results.append(review_node)
        review_data = dict(review_execution.get("data") or {})
        severity_summary = dict(review_data.get("severity_summary") or {})
        gate = should_generate_fix_draft(severity_summary)
        chain_result.decision_gates.append(gate)

        generate_execution: dict[str, Any] | None = None
        generate_node: AgentNodeResult | None = None
        if gate.status == "passed" and not review_execution.get("errors"):
            generate_request = self._build_generate_request(request, review_data)
            generate_routing = self._phase_routing(routing, selected_tool_id="generate_code_draft")
            generate_execution, generate_node = run_timed_node(
                node_id="fix_draft",
                role="FixDraftAgent",
                input_summary="Generate non-destructive code drafts from review findings.",
                runner=lambda: self._run_generate(
                    request=generate_request,
                    routing=generate_routing,
                    trace_id=trace_id,
                    output_language=output_language,
                    chat_config=chat_config,
                    context_bundle=context_bundle,
                ),
                output_summary=self._generate_output_summary,
                data_summary=self._generate_data_summary,
                warnings=lambda item: list((item.get("data") or {}).get("warnings") or []),
            )
            chain_result.phase_results.append(generate_node)
        else:
            chain_result.phase_results.append(
                AgentNodeResult(
                    node_id="fix_draft",
                    role="FixDraftAgent",
                    status="skipped",
                    input_summary="Review findings did not pass the fix-generation gate.",
                    output_summary=gate.reason,
                    data={"decision_gate": gate.to_dict()},
                )
            )

        validation_report, validation_node = run_timed_node(
            node_id="validate",
            role="ValidationAgent",
            input_summary="Validate generated draft when available, otherwise keep review validation checklist.",
            runner=lambda: self._run_validate(request=request, generate_execution=generate_execution),
            output_summary=lambda item: str(item.get("summary") or ""),
            data_summary=lambda item: {
                "issue_count": len(item.get("issue_list") or []),
                "severity_summary": item.get("severity_summary") or {},
                "validated_generated_code": bool(item.get("validated_generated_code")),
            },
        )
        chain_result.phase_results.append(validation_node)

        return self._project_result(
            request=request,
            routing=routing,
            trace_id=trace_id,
            output_language=output_language,
            review_execution=review_execution,
            generate_execution=generate_execution,
            validation_report=validation_report,
            chain_result=chain_result,
            context_bundle=context_bundle,
        )

    def _run_review(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return CodeReviewSkillExecutor(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self.base_debug_builder,
        ).execute(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
            context_bundle=context_bundle,
        )

    def _run_generate(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return CodeGenerateSkillExecutor(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self.base_debug_builder,
        ).execute(
            request=request,
            routing=routing,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
            context_bundle=context_bundle,
        )

    def _run_validate(
        self,
        *,
        request: UnifiedTaskRequest,
        generate_execution: dict[str, Any] | None,
    ) -> dict[str, Any]:
        generated_items = list(((generate_execution or {}).get("data") or {}).get("generated_items") or [])
        code_bundle = _generated_code_bundle(generated_items)
        if not code_bundle:
            return {
                "summary": "No generated draft was produced; keep the original review validation checklist.",
                "issue_list": [],
                "severity_summary": {"high": 0, "medium": 0, "low": 0},
                "validated_generated_code": False,
            }
        validation = review_ue_cpp_files(
            {
                "user_query": "Validate generated fix draft for common UE C++ risks.",
                "code": code_bundle,
                "review_focus": "Validate generated fix draft",
            },
            request.context,
        )
        return {**validation, "validated_generated_code": True}

    def _build_generate_request(
        self,
        request: UnifiedTaskRequest,
        review_data: dict[str, Any],
    ) -> UnifiedTaskRequest:
        issue_list = list(review_data.get("issue_list") or [])
        fix_draft = dict(review_data.get("fix_draft") or {})
        review_scope = dict(review_data.get("review_scope") or {})
        payload = {
            **request.payload,
            "user_query": self._fix_generation_query(request, issue_list),
            "requirement_description": self._fix_generation_query(request, issue_list),
            "review_source": {
                "file_path": review_scope.get("file_path"),
                "source_kind": review_scope.get("source_kind"),
                "line_count": review_scope.get("line_count"),
            },
            "review_issues": issue_list[:8],
            "fix_draft": fix_draft,
            "create_write_proposal": False,
            "write_mode": "draft",
        }
        return request.model_copy(update={"task_type": "code_generate", "payload": payload})

    @staticmethod
    def _fix_generation_query(request: UnifiedTaskRequest, issues: list[dict[str, Any]]) -> str:
        original = str(
            request.payload.get("requirement_description")
            or request.payload.get("user_query")
            or (request.session.messages[-1].content if request.session.messages else "")
            or "Generate a UE C++ fix draft."
        ).strip()
        issue_titles = ", ".join(str(item.get("title") or item.get("rule_id") or "finding") for item in issues[:4])
        if issue_titles:
            return f"{original}\nGenerate a non-destructive UE C++ fix draft for these review findings: {issue_titles}."
        return f"{original}\nGenerate a non-destructive UE C++ fix draft if useful."

    @staticmethod
    def _phase_routing(routing: dict[str, Any], *, selected_tool_id: str) -> dict[str, Any]:
        route = {**dict(routing.get("route") or {}), "selected_tool_id": selected_tool_id}
        return {**routing, "route": route}

    @staticmethod
    def _review_output_summary(execution: dict[str, Any]) -> str:
        data = execution.get("data") or {}
        summary = data.get("severity_summary") or {}
        return (
            f"Found {len(data.get('issue_list') or [])} issue(s): "
            f"high={summary.get('high', 0)}, medium={summary.get('medium', 0)}, low={summary.get('low', 0)}."
        )

    @staticmethod
    def _review_data_summary(execution: dict[str, Any]) -> dict[str, Any]:
        data = execution.get("data") or {}
        return {
            "issue_count": len(data.get("issue_list") or []),
            "severity_summary": data.get("severity_summary") or {},
            "llm_analysis": data.get("llm_analysis") or {},
        }

    @staticmethod
    def _generate_output_summary(execution: dict[str, Any]) -> str:
        data = execution.get("data") or {}
        return f"Generated {len(data.get('generated_items') or [])} draft item(s)."

    @staticmethod
    def _generate_data_summary(execution: dict[str, Any]) -> dict[str, Any]:
        data = execution.get("data") or {}
        return {
            "generated_count": len(data.get("generated_items") or []),
            "file_structure_suggestions": data.get("file_structure_suggestions") or [],
            "write_policy": data.get("write_policy") or {},
        }

    def _project_result(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        review_execution: dict[str, Any],
        generate_execution: dict[str, Any] | None,
        validation_report: dict[str, Any],
        chain_result: AgentChainResult,
        context_bundle: dict[str, Any] | None,
    ) -> dict[str, Any]:
        review_data = dict(review_execution.get("data") or {})
        generate_data = dict((generate_execution or {}).get("data") or {})
        generated_items = list(generate_data.get("generated_items") or [])
        gate = chain_result.decision_gates[0]
        chain_result.status = "completed" if not review_execution.get("errors") else "failed"
        chain_summary = chain_result.summary()
        user_text = _chain_summary_text(
            output_language=output_language,
            review_summary=dict(review_data.get("severity_summary") or {}),
            generated_count=len(generated_items),
            validation_issue_count=len(validation_report.get("issue_list") or []),
            gate=gate,
        )
        base_debug = self.base_debug_builder(
            request=request,
            routing=routing,
            trace_id=trace_id,
            context_bundle=context_bundle,
        )
        blocks = [
            UserViewBlock(
                block_type="summary",
                title=_localized(output_language, "多 Agent 链路摘要", "Multi-Agent Chain Summary"),
                text=user_text,
                data={
                    "chain": chain_summary,
                    "write_policy": {
                        "mode": "non_destructive",
                        "written_to_disk": False,
                        "requires_user_review_before_adoption": True,
                    },
                },
            ).model_dump(mode="json"),
            UserViewBlock(
                block_type="phase_result",
                title=_localized(output_language, "阶段 1：代码审查", "Phase 1: Review"),
                text=self._review_output_summary(review_execution),
                data=self._review_data_summary(review_execution),
            ).model_dump(mode="json"),
        ]
        if generated_items:
            blocks.append(
                UserViewBlock(
                    block_type="generated_items",
                    title=_localized(output_language, "阶段 2：修复草案", "Phase 2: Fix Draft"),
                    text="\n".join(f"{item.get('file_path')} ({item.get('write_status', 'not_written')})" for item in generated_items),
                    data={"generated_items": generated_items},
                ).model_dump(mode="json")
            )
        else:
            blocks.append(
                UserViewBlock(
                    block_type="phase_result",
                    title=_localized(output_language, "阶段 2：修复草案", "Phase 2: Fix Draft"),
                    text=gate.reason,
                    data={"decision_gate": gate.to_dict()},
                ).model_dump(mode="json")
            )
        blocks.append(
            UserViewBlock(
                block_type="phase_result",
                title=_localized(output_language, "阶段 3：草案校验", "Phase 3: Validation"),
                text=str(validation_report.get("summary") or ""),
                data={
                    "issue_list": validation_report.get("issue_list") or [],
                    "severity_summary": validation_report.get("severity_summary") or {},
                    "validated_generated_code": bool(validation_report.get("validated_generated_code")),
                },
            ).model_dump(mode="json")
        )
        for block in (review_execution.get("user_view") or {}).get("blocks") or []:
            if block.get("block_type") in {"llm_analysis", "issues", "recommendations", "fix_draft", "validation_plan"}:
                blocks.append(block)

        data = {
            "multi_agent": chain_summary,
            "review_phase": review_data,
            "generate_phase": generate_data,
            "validate_phase": validation_report,
            "generated_items": generated_items,
            "write_policy": {
                "mode": "non_destructive",
                "written_to_disk": False,
                "proposal_requested": False,
                "message": "Multi-agent chain only returns drafts and validation notes; it never writes to the UE project.",
            },
            "sources": review_data.get("sources") or [],
            "citations": review_data.get("citations") or [],
            "warnings": [
                *list(review_data.get("warnings") or []),
                *list(generate_data.get("warnings") or []),
                *list(chain_result.warnings),
            ],
        }
        step_results = [
            *chain_result.step_results,
            *[self._node_step(item) for item in chain_result.phase_results],
        ]
        tools = [
            {
                "tool_id": "multi_agent_code_review_and_fix",
                "status": chain_result.status,
                "summary": user_text,
            },
            *list((review_execution.get("debug_view") or {}).get("tools") or []),
        ]
        if generate_execution:
            tools.extend(list((generate_execution.get("debug_view") or {}).get("tools") or []))
        tools.append(
            {
                "tool_id": "validate_generated_fix",
                "status": "completed",
                "summary": str(validation_report.get("summary") or ""),
            }
        )
        retrieval_trace = review_execution.get("retrieval_trace") or {}
        base_debug["retrieval"] = retrieval_trace
        base_debug["local_search"] = retrieval_trace.get("local_search", {})
        base_debug["tools"] = tools
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["multi_agent"] = chain_summary
        base_debug["warnings"] = data["warnings"]

        usage = dict(review_execution.get("usage") or {})
        generate_usage = dict((generate_execution or {}).get("usage") or {})
        for key in ("input_tokens", "output_tokens", "estimated_cost_usd"):
            if key in generate_usage:
                usage[key] = usage.get(key, 0) + generate_usage.get(key, 0)

        return {
            "user_view": {
                "title": _localized(output_language, "多 Agent 代码审查链", "Multi-Agent Code Review Chain"),
                "text": user_text,
                "blocks": blocks,
                "citations_preview": _citation_previews(review_data.get("citations") or []),
                "quick_actions": [],
                "status_hint": "multi_agent_complete",
            },
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": retrieval_trace,
            "planner_diagnostics": {**dict(routing.get("route") or {}), "execution_mode": "multi_agent_chain"},
            "step_results": step_results,
            "action_proposals": [],
            "errors": list(review_execution.get("errors") or []),
            "assistant_message": user_text,
            "artifacts": [
                *list(review_execution.get("artifacts") or []),
                *list((generate_execution or {}).get("artifacts") or []),
                {
                    "artifact_type": "multi_agent_chain_report",
                    "label": "Multi-Agent Chain Report",
                    "filename": "multi_agent_chain_report.json",
                    "content": data,
                },
            ],
            "usage": usage,
        }

    @staticmethod
    def _node_step(node: AgentNodeResult) -> dict[str, Any]:
        return {
            "step_id": f"multi_agent_{node.node_id}",
            "title": f"{node.role}: {node.node_id}",
            "status": node.status,
            "summary": node.output_summary,
            "details": node.to_dict(),
        }
