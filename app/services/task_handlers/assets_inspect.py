from __future__ import annotations

from typing import Any

from app.i18n.language import localized as _localized
from app.schemas.common import UserViewBlock
from app.services.editor_operation_service import EditorOperationService
from app.services.task_handlers.base import TaskExecutionContext
from app.skills.executors import AssetsInspectSkillExecutor


class AssetsInspectHandler:
    """Runs asset inspection and attaches safe editor-operation proposals."""

    handler_id = "assets_inspect"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        executor = AssetsInspectSkillExecutor(
            kb_service=host.kb_service,
            llm_service=host.llm_service,
            base_debug_builder=host._base_debug,
        )
        execution = executor.execute(
            request=context.request,
            routing=context.routing,
            trace_id=context.trace_id,
            output_language=context.output_language,
            chat_config=context.chat_config,
        )
        proposal = EditorOperationService(host.db).build_asset_inspect_rename_proposal(
            execution=execution,
            request=context.request,
        )
        if proposal:
            execution["action_proposals"] = list(execution.get("action_proposals") or []) + [proposal]
            execution["data"]["editor_operation_proposals"] = [proposal]
            execution["user_view"]["blocks"] = list(execution["user_view"].get("blocks") or []) + [
                UserViewBlock(
                    block_type="editor_operation_proposal",
                    title=_localized(
                        context.output_language,
                        "可确认的编辑器操作",
                        "Confirmable Editor Operation",
                    ),
                    text=_localized(
                        context.output_language,
                        "已根据资产检查结果生成重命名提案。确认后由 UE 插件执行，后端不会直接修改编辑器资产。",
                        "A rename proposal was generated from the asset inspection result. "
                        "The UE plugin executes it after confirmation; the backend does not "
                        "directly modify editor assets.",
                    ),
                    data={"proposal": proposal},
                ).model_dump(mode="json")
            ]
            execution["debug_view"]["side_effects"] = list(
                execution["debug_view"].get("side_effects") or []
            ) + [
                {
                    "proposal_id": proposal["proposal_id"],
                    "proposal_type": "editor_operation",
                    "operation_type": "rename_selected_asset",
                    "tool_id": "editor_rename_asset",
                    "side_effect_level": "confirmed_write",
                    "execution_state": "not_executed_without_confirmation",
                    "written_by_backend": False,
                }
            ]
        return execution
