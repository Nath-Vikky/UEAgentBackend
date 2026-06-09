from __future__ import annotations

import re
from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.requests import UnifiedTaskRequest
from app.services.code_write_service import build_code_write_plan
from app.services.kb_service import KnowledgeBaseService
from app.services.local_search_service import LocalSearchService
from app.services.llm_service import ChatRuntimeConfig, LLMService
from app.tools.code_generate import generate_code_draft
from app.tools.code_preflight import build_code_generation_preflight
from app.tools.retrieval import retrieve_support_notes


def _language_from_file_path(file_path: str) -> str:
    lowered = file_path.lower()
    if lowered.endswith((".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cpp", ".cxx")):
        return "cpp"
    if lowered.endswith(".cs"):
        return "csharp"
    if lowered.endswith(".py"):
        return "python"
    if lowered.endswith((".json", ".ini", ".yaml", ".yml", ".toml")):
        return "config"
    return "text"


def _generated_items_from_draft(code_draft: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, (file_path, code_text) in enumerate(code_draft.items(), start=1):
        items.append(
            {
                "item_id": f"generated_{index}",
                "label": file_path.split("/")[-1],
                "file_path": file_path,
                "language": _language_from_file_path(file_path),
                "code": code_text,
            }
        )
    return items


def _normalize_generated_items(items: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("content") or "").strip()
        if not code:
            continue
        file_path = str(item.get("file_path") or item.get("path") or item.get("label") or f"draft_{index}.txt").strip()
        label = str(item.get("label") or file_path.split("/")[-1] or f"Generated Item {index}").strip()
        normalized.append(
            {
                "item_id": f"generated_{index}",
                "label": label,
                "file_path": file_path,
                "language": str(item.get("language") or _language_from_file_path(file_path)).strip(),
                "code": code,
                "write_status": "not_written",
                "is_virtual": True,
            }
        )
    return normalized


_CODE_FENCE_RE = re.compile(r"```(?P<language>[A-Za-z0-9_+.#-]*)\s*\n(?P<code>.*?)```", re.DOTALL)
_FILE_PATH_HINT_RE = re.compile(
    r"(?:file|path|filename|source|文件|路径)\s*[:：]\s*`?(?P<path>[^`\r\n]+)`?",
    re.IGNORECASE,
)
_SOURCE_PATH_RE = re.compile(
    r"(?P<path>(?:Source|Plugins)/[A-Za-z0-9_./-]+\.(?:h|hpp|hh|inl|c|cc|cpp|cxx|cs|py|txt|md|json|ini))",
    re.IGNORECASE,
)


def _module_name_for_request(request: UnifiedTaskRequest) -> str:
    raw = str(
        request.payload.get("target_module")
        or request.payload.get("module_name")
        or request.context.current_module
        or request.context.project_name
        or "YourModule"
    ).strip()
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", raw)
    return cleaned or "YourModule"


def _fallback_path_for_llm_item(*, request: UnifiedTaskRequest, language: str, index: int) -> str:
    module_name = _module_name_for_request(request)
    normalized_language = language.lower().strip()
    if normalized_language in {"cpp", "c++", "cxx", "cc"}:
        return f"Source/{module_name}/Private/GeneratedSnippet{index}.cpp"
    if normalized_language in {"h", "hpp", "header"}:
        return f"Source/{module_name}/Public/GeneratedSnippet{index}.h"
    if normalized_language in {"csharp", "cs"}:
        return f"Source/{module_name}/GeneratedSnippet{index}.cs"
    if normalized_language == "python":
        return f"Scripts/GeneratedSnippet{index}.py"
    return f"generated_snippet_{index}.txt"


def _path_hint_before(text: str, fence_start: int) -> str:
    prefix = text[:fence_start]
    recent = "\n".join(prefix.splitlines()[-4:])
    for pattern in (_FILE_PATH_HINT_RE, _SOURCE_PATH_RE):
        matches = list(pattern.finditer(recent))
        if matches:
            return matches[-1].group("path").strip().strip("`'\" ")
    return ""


def _looks_like_code(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "#include",
        "uclass",
        "ustruct",
        "ufunction",
        "ue_log",
        "void ",
        "class ",
        "for (",
        "for(",
        "while (",
        "if (",
        "return ",
    )
    return any(marker in lowered for marker in markers)


def _normalize_llm_text_generated_items(text: str, *, request: UnifiedTaskRequest) -> list[dict[str, Any]]:
    raw_text = str(text or "").strip()
    if not raw_text:
        return []

    items: list[dict[str, Any]] = []
    for index, match in enumerate(_CODE_FENCE_RE.finditer(raw_text), start=1):
        code = match.group("code").strip()
        if not code:
            continue
        language = match.group("language").strip() or "cpp"
        file_path = _path_hint_before(raw_text, match.start()) or _fallback_path_for_llm_item(
            request=request,
            language=language,
            index=index,
        )
        items.append(
            {
                "label": file_path.split("/")[-1],
                "file_path": file_path,
                "language": _language_from_file_path(file_path) if file_path else language,
                "code": code,
            }
        )

    if not items and _looks_like_code(raw_text):
        file_path = _fallback_path_for_llm_item(request=request, language="cpp", index=1)
        items.append(
            {
                "label": file_path.split("/")[-1],
                "file_path": file_path,
                "language": _language_from_file_path(file_path),
                "code": raw_text,
            }
        )

    return _normalize_generated_items(items)


def _reference_excerpt(item: dict[str, Any], limit: int = 500) -> str:
    return str(item.get("snippet") or item.get("text") or "").strip()[:limit]


def _local_search_docs(local_search: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item["item_id"],
            "doc_id": item["source_path"],
            "title": item["title"],
            "source_path": item["source_path"],
            "domain": item["domain"],
            "section_path": f"lines:{item['line_start']}-{item['line_end']}",
            "text": item["snippet"],
            "snippet": item["snippet"],
            "lexical_score": item["score"],
            "semantic_score": 0.0,
            "final_score": item["score"],
            "matched_terms": item["matched_terms"],
            "retrieval_source": "local_grep",
        }
        for item in local_search.get("items", [])
    ]


def _local_search_citations(local_search: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "title": item["title"],
            "source": item["source_path"],
            "section_path": f"lines:{item['line_start']}-{item['line_end']}",
            "snippet": item["snippet"][:220],
            "score": item["score"],
            "domain": item["domain"],
            "retrieval_source": "local_grep",
        }
        for item in local_search.get("items", [])[:3]
    ]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_enhanced_input_character_request(query: str, request: UnifiedTaskRequest) -> bool:
    text = " ".join(
        [
            query,
            str(request.payload.get("user_query") or ""),
            str(request.payload.get("requirement_description") or ""),
            str(request.payload.get("target_type") or ""),
        ]
    ).lower()
    enhanced_terms = (
        "enhanced input",
        "enhancedinput",
        "input action",
        "input mapping",
        "mapping context",
        "uinputaction",
        "uinputmappingcontext",
        "uenhancedinputcomponent",
        "增强输入",
        "输入增强",
        "增强输入系统",
        "输入动作",
        "映射上下文",
    )
    character_terms = ("character", "player", "pawn", "角色", "玩家", "玩家角色")
    target_type = str(request.payload.get("target_type") or "").lower()
    return any(term in text for term in enhanced_terms) and (
        any(term in text for term in character_terms)
        or target_type in {"character", "player_character", "ue_character", "ue_cpp_character"}
    )


def _missing_enhanced_input_markers(generated_items: list[dict[str, Any]]) -> list[str]:
    joined = "\n".join(
        [
            *(str(item.get("file_path") or "") for item in generated_items),
            *(str(item.get("code") or "") for item in generated_items),
        ]
    ).lower()
    required_terms = {
        "character_base": ("acharacter", "gameframework/character.h"),
        "input_action": ("uinputaction", "inputaction"),
        "mapping_context": ("uinputmappingcontext", "inputmappingcontext"),
        "enhanced_input_component": ("uenhancedinputcomponent", "enhancedinputcomponent"),
        "bind_action": ("bindaction",),
        "add_mapping_context": ("addmappingcontext",),
    }
    return [
        marker
        for marker, terms in required_terms.items()
        if not any(term in joined for term in terms)
    ]


def _llm_generation_rejection_reason(
    *,
    request: UnifiedTaskRequest,
    query: str,
    generated_items: list[dict[str, Any]],
) -> str:
    if not _is_enhanced_input_character_request(query, request):
        return ""
    missing = _missing_enhanced_input_markers(generated_items)
    if missing:
        return "enhanced_input_incomplete:" + ",".join(missing)
    return ""


class CodeGenerationService:
    def __init__(
        self,
        *,
        kb_service: KnowledgeBaseService,
        llm_service: LLMService,
    ) -> None:
        self.kb_service = kb_service
        self.llm_service = llm_service

    def execute(
        self,
        *,
        request: UnifiedTaskRequest,
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        query = str(
            request.payload.get("requirement_description")
            or request.payload.get("user_query")
            or (request.session.messages[-1].content if request.session.messages else "")
        ).strip()
        domain_filters = list(
            request.payload.get("domain_filters")
            or ["code_reference", "examples", "engine_notes", "prompt_packs", "project_docs"]
        )
        support = retrieve_support_notes(
            self.kb_service,
            query=query or "Generate a UE code draft.",
            context=request.context,
            output_language=output_language,
            domain_filters=domain_filters,
            extra_payload={"disable_local_search": True},
        )
        support_agentic_rag = dict(support.get("retrieval_trace", {}).get("agentic_rag") or {})
        support_quality_gate = dict(support.get("retrieval_quality_gate") or {})
        local_search_query = str(
            support_agentic_rag.get("selected_query")
            or query
            or "Generate a UE code draft."
        )
        local_search = LocalSearchService(self.kb_service.settings).search(
            query=local_search_query,
            domain_filters=domain_filters,
            top_k=6,
        )
        local_docs = _local_search_docs(local_search)
        local_citations = _local_search_citations(local_search)
        support_warnings = list(support["warnings"])
        if local_docs:
            support_warnings = [
                item
                for item in support_warnings
                if item not in {"no_retrieval_hits", "evidence_insufficient"}
            ]
        merged_docs = [*local_docs, *support["retrieved_docs"]]
        merged_citations = [*local_citations, *support["citations"]]
        reference_lookup = {
            "reference_count": len(merged_docs),
            "rag_reference_count": len(support["retrieved_docs"]),
            "local_reference_count": len(local_docs),
            "domains": sorted({item.get("domain") for item in merged_docs if item.get("domain")}),
            "sources": [{"title": item["title"], "source": item["source"]} for item in merged_citations],
            "local_search": local_search["summary"],
            "local_search_query": local_search_query,
            "agentic_rag": support_agentic_rag,
            "retrieval_quality_gate": support_quality_gate,
        }

        support_for_generation = {
            **support,
            "retrieved_docs": merged_docs,
            "citations": merged_citations,
            "local_search": local_search,
        }
        llm_attempt = self._generate_with_llm(
            request=request,
            query=query,
            support=support_for_generation,
            chat_config=chat_config,
        )
        template_result = generate_code_draft(
            {
                **request.payload,
                "target_module": request.payload.get("target_module")
                or request.payload.get("module_name")
                or request.context.current_module
                or request.context.project_name,
                "reference_items": merged_docs,
            }
        )

        llm_rejection_reason = ""
        if llm_attempt["ok"] and llm_attempt["generated_items"]:
            llm_rejection_reason = _llm_generation_rejection_reason(
                request=request,
                query=query,
                generated_items=llm_attempt["generated_items"],
            )
            if llm_rejection_reason:
                llm_attempt["warnings"].append(f"llm_generation_rejected:{llm_rejection_reason}")

        if llm_attempt["ok"] and llm_attempt["generated_items"] and not llm_rejection_reason:
            generated_items = llm_attempt["generated_items"]
            generation_mode = (
                "live_llm_reference_augmented"
                if reference_lookup["reference_count"]
                else "live_llm_direct"
            )
            summary = str(llm_attempt["summary"] or "").strip() or template_result["explanation"]
            notes = llm_attempt["notes"]
            usage = llm_attempt["usage"]
            tool_summary = "Generated structured code with a live LLM."
        else:
            generated_items = template_result["generated_items"]
            generation_mode = (
                "template_reference_augmented_fallback"
                if reference_lookup["reference_count"]
                else "template_direct_fallback"
            )
            summary = template_result["explanation"]
            notes = [*template_result.get("assumptions", []), *template_result.get("known_risks", [])]
            usage = {}
            tool_summary = template_result["explanation"]

        code_draft = {item["file_path"]: item["code"] for item in generated_items}
        create_write_proposal = _truthy(request.payload.get("create_write_proposal")) or str(
            request.payload.get("write_mode") or ""
        ).strip().lower() in {"proposal", "write_proposal", "confirmed_write"}
        write_plan = build_code_write_plan(
            project_root=str(request.payload.get("project_root") or request.context.project_root or ""),
            generated_items=generated_items,
            allow_overwrite_existing=_truthy(request.payload.get("allow_overwrite_existing")),
        ) if create_write_proposal else {
            "status": "disabled",
            "reason": "write_proposal_not_requested",
            "written_to_disk": False,
            "files": [],
            "summary": {"ready_count": 0, "blocked_count": 0, "file_count": 0},
        }
        result = {
            **template_result,
            "code_draft": code_draft,
            "file_structure_suggestions": [item["file_path"] for item in generated_items],
            "generated_items": generated_items,
            "generation_mode": generation_mode,
            "summary": summary,
            "notes": notes,
            "write_policy": {
                "mode": "non_destructive",
                "written_to_disk": False,
                "proposal_requested": create_write_proposal,
                "proposal_status": write_plan["status"],
                "message": (
                    "Generated items are virtual drafts. A write proposal is available for confirmation."
                    if write_plan["status"] == "ready"
                    else "Generated items are virtual drafts returned in the API response; the backend does not create files."
                ),
            },
            "write_plan": write_plan,
            "reference_lookup": reference_lookup,
            "retrieved_references": merged_citations,
            "supporting_notes": support["answer"],
            "local_search": local_search,
        }
        preflight_report = build_code_generation_preflight(
            result=result,
            requirement=query,
            target_module=str(
                request.payload.get("target_module")
                or request.payload.get("module_name")
                or request.context.current_module
                or request.context.project_name
                or ""
            ),
        )
        result["preflight_report"] = preflight_report

        step_results = [
            {
                "step_id": "retrieve_code_references",
                "title": "Retrieve Code References",
                "status": "completed",
                "summary": f"Retrieved {reference_lookup['reference_count']} code reference chunk(s).",
                "details": {
                    "domains": reference_lookup["domains"],
                    "sources": reference_lookup["sources"],
                    "local_search": local_search["summary"],
                },
            },
            {
                "step_id": "generate_draft",
                "title": "Generate Draft",
                "status": "completed",
                "summary": tool_summary,
                "details": {
                    "generation_mode": generation_mode,
                    "files": result["file_structure_suggestions"],
                },
            },
            {
                "step_id": "preflight_generated_code",
                "title": "Preflight Generated Code",
                "status": preflight_report["status"],
                "summary": (
                    f"Code preflight found {preflight_report['summary']['finding_count']} finding(s)."
                ),
                "details": preflight_report,
            },
        ]

        tools = [
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {reference_lookup['reference_count']} code-support chunk(s).",
            },
            {
                "tool_id": "local_grep_code_reference",
                "status": "completed" if local_docs else "skipped",
                "summary": f"Matched {len(local_docs)} local markdown/code reference file(s).",
            },
            {
                "tool_id": "live_llm_code_generate" if llm_attempt["ok"] else "generate_code_draft",
                "status": "completed",
                "summary": tool_summary,
            },
            {
                "tool_id": "preflight_generated_code",
                "status": preflight_report["status"],
                "summary": (
                    f"Checked {preflight_report['summary']['checked_item_count']} generated item(s); "
                    f"{preflight_report['summary']['finding_count']} finding(s)."
                ),
            },
        ]

        artifacts = [
            {
                "artifact_type": "code_draft",
                "label": "Generated Code Draft",
                "filename": "code_draft.json",
                "content": code_draft,
            },
            {
                "artifact_type": "code_generation_bundle",
                "label": "Code Generation Bundle",
                "filename": "code_generation_bundle.json",
                "content": result,
            },
        ]
        action_proposals = [
            {
                "title": "Review Generated Draft",
                "proposal_type": "code_patch",
                "before_summary": "No files have been written to the workspace.",
                "after_summary": "Selected generated files could be adopted manually after review.",
                "rationale": "The backend generates non-destructive code results and does not write directly into the project.",
                "risk_flags": "LOW",
                "dry_run_preview": {"files": result["file_structure_suggestions"]},
                "display_hints": {"panel": "CodeGenerator"},
                "requires_confirmation": False,
                "confirmation": {"state": "not_required"},
            }
        ]
        if create_write_proposal and write_plan["status"] == "ready":
            action_proposals.append(
                {
                    "title": "Write Generated Code Files",
                    "proposal_type": "write_code_files",
                    "before_summary": "No generated code files have been written to the UE project.",
                    "after_summary": (
                        f"Write {write_plan['summary']['ready_count']} generated file(s) "
                        "under the configured project root."
                    ),
                    "rationale": (
                        "The user explicitly requested a write proposal; the backend will only write "
                        "safe relative Source/ or Plugins/ files after confirmation."
                    ),
                    "risk_flags": "MEDIUM",
                    "dry_run_preview": {
                        "write_plan": write_plan,
                        "write_policy": result["write_policy"],
                        "generated_item_count": len(generated_items),
                    },
                    "display_hints": {
                        "panel": "CodeGenerator",
                        "requires_diff_preview": True,
                        "confirm_label": "Write files",
                    },
                    "requires_confirmation": True,
                    "confirmation": {"state": "pending"},
                }
            )
        elif create_write_proposal and write_plan["status"] != "ready":
            result["write_policy"]["message"] = (
                f"Write proposal was requested but blocked: {write_plan.get('reason')}"
            )

        return {
            "result": result,
            "step_results": step_results,
            "retrieval_trace": {
                **support["retrieval_trace"],
                "local_search": local_search,
                "agentic_rag": support_agentic_rag,
                "retrieval_quality_gate": support_quality_gate,
                "retrieved_docs": [
                    *local_docs,
                    *support["retrieval_trace"].get("retrieved_docs", []),
                ],
            },
            "tools": tools,
            "warnings": [
                *support_warnings,
                *(["local_search_no_matches"] if not local_docs else []),
                *(["write_proposal_blocked"] if create_write_proposal and write_plan["status"] != "ready" else []),
                *(
                    [f"code_preflight_{preflight_report['status']}"]
                    if preflight_report["status"] != "passed"
                    else []
                ),
                *llm_attempt["warnings"],
            ],
            "artifacts": artifacts,
            "action_proposals": action_proposals,
            "usage": usage,
        }

    def _generate_with_llm(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        support: dict[str, Any],
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        available, reason = self.llm_service.availability(chat_config)
        if not available:
            return {
                "ok": False,
                "generated_items": [],
                "summary": "",
                "notes": [],
                "usage": {},
                "warnings": [reason],
            }

        messages = self._generation_messages(
            request=request,
            query=query,
            support=support,
        )
        result = self.llm_service.complete_json_object(messages=messages, config=chat_config)
        if not result["ok"]:
            text_generated_items = _normalize_llm_text_generated_items(str(result.get("text") or ""), request=request)
            if text_generated_items:
                return {
                    "ok": True,
                    "generated_items": text_generated_items,
                    "summary": "Generated code from the LLM text response after structured JSON parsing failed.",
                    "notes": [
                        "The model returned code-like text instead of the requested JSON schema.",
                        "The backend extracted the code as a non-destructive draft.",
                    ],
                    "usage": result["usage"],
                    "warnings": [f"structured_json_failed:{result['reason']}", "llm_text_fallback_used"],
                }
            retry = self._generate_with_llm_text(
                request=request,
                query=query,
                support=support,
                chat_config=chat_config,
                fallback_from=result,
            )
            if retry["ok"]:
                return retry
            return {
                "ok": False,
                "generated_items": [],
                "summary": "",
                "notes": [],
                "usage": result["usage"],
                "warnings": [result["reason"], result["error"]] if result.get("error") else [result["reason"]],
            }

        payload = result["payload"] or {}
        generated_items = _normalize_generated_items(payload.get("generated_items"))
        if not generated_items:
            retry = self._generate_with_llm_text(
                request=request,
                query=query,
                support=support,
                chat_config=chat_config,
                fallback_from=result,
            )
            if retry["ok"]:
                return retry
        return {
            "ok": bool(generated_items),
            "generated_items": generated_items,
            "summary": str(payload.get("summary") or "").strip(),
            "notes": [str(item).strip() for item in payload.get("notes") or [] if str(item).strip()],
            "usage": result["usage"],
            "warnings": [] if generated_items else ["empty_generated_items"],
        }

    def _generate_with_llm_text(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        support: dict[str, Any],
        chat_config: ChatRuntimeConfig,
        fallback_from: dict[str, Any],
    ) -> dict[str, Any]:
        if str(fallback_from.get("reason") or "") not in {"json_parse_failed", "completed"}:
            return {
                "ok": False,
                "generated_items": [],
                "summary": "",
                "notes": [],
                "usage": fallback_from.get("usage") or {},
                "warnings": [f"llm_text_retry_skipped:{fallback_from.get('reason') or 'unknown'}"],
            }

        result = self.llm_service.complete(
            messages=self._generation_text_messages(request=request, query=query, support=support),
            config=chat_config,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "generated_items": [],
                "summary": "",
                "notes": [],
                "usage": result.get("usage") or fallback_from.get("usage") or {},
                "warnings": [
                    f"structured_generation_failed:{fallback_from.get('reason') or 'unknown'}",
                    f"text_generation_failed:{result.get('reason') or 'unknown'}",
                ],
            }
        generated_items = _normalize_llm_text_generated_items(str(result.get("text") or ""), request=request)
        return {
            "ok": bool(generated_items),
            "generated_items": generated_items,
            "summary": (
                "Generated code from a live LLM text fallback."
                if generated_items
                else ""
            ),
            "notes": [
                "Structured JSON generation did not provide usable generated_items.",
                "A text fallback was used and parsed into non-destructive generated items.",
            ] if generated_items else [],
            "usage": result.get("usage") or fallback_from.get("usage") or {},
            "warnings": (
                [f"structured_generation_failed:{fallback_from.get('reason') or 'unknown'}", "llm_text_retry_used"]
                if generated_items
                else ["empty_generated_items", "llm_text_retry_empty"]
            ),
        }

    def _generation_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        support: dict[str, Any],
    ) -> list[dict[str, str]]:
        context_summary = build_context_summary(request)
        references: list[str] = []
        for index, item in enumerate(support["retrieved_docs"][:3], start=1):
            references.append(
                "\n".join(
                    [
                        f"[R{index}] {item['title']}",
                        f"Source: {item.get('source_path') or item.get('title')}",
                        f"Domain: {item.get('domain')}",
                        f"Excerpt: {_reference_excerpt(item)}",
                    ]
                )
            )
        review_issue_lines: list[str] = []
        for index, item in enumerate(list(request.payload.get("review_issues") or [])[:8], start=1):
            if not isinstance(item, dict):
                continue
            review_issue_lines.append(
                " | ".join(
                    part
                    for part in (
                        f"{index}. severity={item.get('severity') or 'unknown'}",
                        f"rule={item.get('rule_id') or item.get('title') or 'review_finding'}",
                        f"line={item.get('line')}" if item.get("line") else "",
                        f"suggestion={item.get('suggestion') or ''}",
                    )
                    if part
                )
            )
        fix_draft_items = []
        fix_draft = request.payload.get("fix_draft") if isinstance(request.payload.get("fix_draft"), dict) else {}
        for item in list(fix_draft.get("items") or [])[:6]:
            if isinstance(item, dict):
                text = str(item.get("suggested_change") or item.get("text") or item.get("summary") or "").strip()
                if text:
                    fix_draft_items.append(f"- {text}")
        system_prompt = (
            "You generate non-destructive code drafts for a local Unreal Engine assistant backend. "
            "Return JSON only with this exact schema: "
            '{"summary":"...","generated_items":[{"label":"...","file_path":"...","language":"...","code":"..."}],"notes":["..."]}. '
            "Do not wrap the JSON in markdown fences. "
            "When project-specific reference snippets are provided, align naming, structure, and style with them. "
            "When no reference snippets are provided, still solve the user's requested behavior directly using general Unreal C++ knowledge. "
            "Do not return an empty Actor skeleton unless the user explicitly asked for a skeleton. "
            "When review findings are provided, generate a focused fix draft that addresses those findings first. "
            "For Unreal C++ requests, prefer Source/<Module>/Public/<ClassName>.h and "
            "Source/<Module>/Private/<ClassName>.cpp instead of draft.txt. "
            "For Character or Enhanced Input requests, generate ACharacter-based code with UInputMappingContext, "
            "UInputAction references, UEnhancedInputComponent bindings, and a reminder to add the EnhancedInput module. "
            "For interaction component, line trace, or subsystem requests, prefer the matching UE base class "
            "(UActorComponent or UGameInstanceSubsystem) and include concrete method bodies instead of empty skeletons. "
            "For HTTP, WebSocket, DeveloperSettings, Gameplay Tags, threading, replication, or GAS requests, "
            "identify the correct UE module dependencies and lifecycle cleanup points. "
            "Do not claim that any file has been written to disk."
        )
        user_prompt = "\n\n".join(
            [
                f"Requirement:\n{query or 'Generate a useful starter implementation.'}",
                f"Target type: {request.payload.get('target_type') or 'ue_cpp_class'}",
                f"Context summary:\n{context_summary or '(none)'}",
                "Review findings from previous agent phase:",
                "\n".join(review_issue_lines) if review_issue_lines else "(none)",
                "Review fix hints:",
                "\n".join(fix_draft_items) if fix_draft_items else "(none)",
                "Reference snippets:",
                "\n\n".join(references) if references else "(none)",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _generation_text_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        support: dict[str, Any],
    ) -> list[dict[str, str]]:
        base_messages = self._generation_messages(request=request, query=query, support=support)
        text_system = (
            "The previous structured JSON code-generation attempt was not usable. "
            "Now return a concise non-destructive code draft as plain text. "
            "For each generated file, write a line `File: Source/<Module>/Public/<Name>.h` or "
            "`File: Source/<Module>/Private/<Name>.cpp`, followed by one fenced code block. "
            "If the request is a small behavior such as a countdown printed to the console, implement that behavior directly. "
            "Do not only return a generic BeginPlay/Tick skeleton unless that is the requested behavior. "
            "Do not claim files were written to disk."
        )
        return [
            {"role": "system", "content": text_system},
            *base_messages[1:],
        ]
