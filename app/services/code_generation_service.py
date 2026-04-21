from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService
from app.tools.code_generate import generate_code_draft
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
            }
        )
    return normalized


def _reference_excerpt(item: dict[str, Any], limit: int = 500) -> str:
    return str(item.get("snippet") or item.get("text") or "").strip()[:limit]


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
        domain_filters = list(request.payload.get("domain_filters") or ["code_reference", "examples", "project_docs"])
        support = retrieve_support_notes(
            self.kb_service,
            query=query or "Generate a UE code draft.",
            context=request.context,
            output_language=output_language,
            domain_filters=domain_filters,
        )
        reference_lookup = {
            "reference_count": len(support["retrieved_docs"]),
            "domains": sorted({item.get("domain") for item in support["retrieved_docs"] if item.get("domain")}),
            "sources": [{"title": item["title"], "source": item["source"]} for item in support["citations"]],
        }

        llm_attempt = self._generate_with_llm(
            request=request,
            query=query,
            support=support,
            chat_config=chat_config,
        )
        template_result = generate_code_draft(
            {
                **request.payload,
                "reference_items": support["retrieved_docs"],
            }
        )

        if llm_attempt["ok"] and llm_attempt["generated_items"]:
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
        result = {
            **template_result,
            "code_draft": code_draft,
            "file_structure_suggestions": [item["file_path"] for item in generated_items],
            "generated_items": generated_items,
            "generation_mode": generation_mode,
            "summary": summary,
            "notes": notes,
            "reference_lookup": reference_lookup,
            "retrieved_references": support["citations"],
            "supporting_notes": support["answer"],
        }

        step_results = [
            {
                "step_id": "retrieve_code_references",
                "title": "Retrieve Code References",
                "status": "completed",
                "summary": f"Retrieved {reference_lookup['reference_count']} code reference chunk(s).",
                "details": {
                    "domains": reference_lookup["domains"],
                    "sources": reference_lookup["sources"],
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
        ]

        tools = [
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {reference_lookup['reference_count']} code-support chunk(s).",
            },
            {
                "tool_id": "live_llm_code_generate" if llm_attempt["ok"] else "generate_code_draft",
                "status": "completed",
                "summary": tool_summary,
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

        return {
            "result": result,
            "step_results": step_results,
            "retrieval_trace": support["retrieval_trace"],
            "tools": tools,
            "warnings": [*support["warnings"], *llm_attempt["warnings"]],
            "artifacts": artifacts,
            "action_proposals": [
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
            ],
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
        return {
            "ok": bool(generated_items),
            "generated_items": generated_items,
            "summary": str(payload.get("summary") or "").strip(),
            "notes": [str(item).strip() for item in payload.get("notes") or [] if str(item).strip()],
            "usage": result["usage"],
            "warnings": [] if generated_items else ["empty_generated_items"],
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
        system_prompt = (
            "You generate non-destructive code drafts for a local Unreal Engine assistant backend. "
            "Return JSON only with this exact schema: "
            '{"summary":"...","generated_items":[{"label":"...","file_path":"...","language":"...","code":"..."}],"notes":["..."]}. '
            "Do not wrap the JSON in markdown fences. "
            "When project-specific reference snippets are provided, align naming, structure, and style with them. "
            "Do not claim that any file has been written to disk."
        )
        user_prompt = "\n\n".join(
            [
                f"Requirement:\n{query or 'Generate a useful starter implementation.'}",
                f"Target type: {request.payload.get('target_type') or 'ue_cpp_class'}",
                f"Context summary:\n{context_summary or '(none)'}",
                "Reference snippets:",
                "\n\n".join(references) if references else "(none)",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
