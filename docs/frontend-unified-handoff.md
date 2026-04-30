# UE Frontend Unified Handoff

## 1. 文档用途

这是 UE 前端当前唯一优先阅读的后端交接文档。如果前端只拿一份后端说明，就拿这一份。

最小补充文件：

- `forward.md`
- `app/schemas/requests.py`
- `app/schemas/responses.py`
- `app/schemas/common.py`

## 2. 当前正式范围

前端主菜单只保留 5 个核心功能：

1. `Agent Chat / Project QA`
2. `Code Review`
3. `Code Generate`
4. `Logs Analyze`
5. `Assets Inspect`

以下任务虽然路由仍兼容存在，但应从前端主菜单隐藏：

- `config_generate`
- `config_validate`
- `assets_plan`
- `assets_execute`
- `perf_analyze`

如果前端读取 `GET /api/v1/system/capabilities`，请以这些字段作为菜单依据：

- `supported_task_types`
- `deferred_task_types`
- `feature_catalog`
- `skill_catalog`
- `skill_architecture`

`skill_catalog` 是后端固定内置 Skill 的稳定描述层。前端不需要动态加载 Skill，也不需要把 collector/rules/retrieval/projector 做成 UI；这些字段主要用于菜单、调试说明和能力展示。当前 5 个固定 Skill 是：
- `ProjectQASkill`
- `CodeReviewSkill`
- `CodeGenerateSkill`
- `LogsAnalyzeSkill`
- `AssetsInspectSkill`

特别注意：Code Review 的 UE 工程源码扫描和读取属于 `CodeReviewSkill.architecture.collector`，不是第 6 个主功能。前端仍然只需要渲染文件列表、文件选择和审查按钮。

## 3. 当前前端节奏

当前结论是：后端 5 个核心功能契约已经收口，前端可以开始统一调整 UI。

原因：

- 后端已经把能力范围冻结到 5 个核心功能
- `capabilities`、任务接口、`user_view`、`debug_view` 和文档口径已经对齐
- 前端现在可以一次性集中改菜单和 4 个专用面板，避免零碎返工

前端现在可以做的事：

- 按 5 个核心功能收缩主菜单
- 按本文件的目标 UI 形态重构面板
- 继续只把真实上下文和编辑器采集数据传给后端，不在前端硬编码 RAG 判断

## 4. 前端启动顺序

建议插件打开面板后按下面顺序调用：

1. `GET /api/v1/system/health`
2. `GET /api/v1/system/bootstrap`
3. `GET /api/v1/system/capabilities`
4. `GET /api/v1/system/runtime-profiles`
5. `GET /api/v1/knowledge-base/status`
6. `GET /api/v1/system/settings`
7. `GET /metrics`
8. `GET /api/v1/system/alerts`
9. `POST /api/v1/sessions`
10. `GET /api/v1/sessions/{session_id}`
11. `GET /api/v1/sessions/{session_id}/history`
12. `GET /api/v1/sessions/{session_id}/tasks`
13. `GET /api/v1/tasks/recent`

## 5. 核心接口

### Agent Chat / Project QA

- `POST /api/v1/chat/runs`
- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/user-view`
- `GET /api/v1/chat/runs/{run_id}/debug-view`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/chat/runs/{run_id}/cancel`

### Code Review

- `POST /api/v1/tasks/code-review/files`
- `POST /api/v1/tasks/code-review`

### Code Generate

- `POST /api/v1/tasks/code-generate`

### Logs Analyze

- `POST /api/v1/tasks/logs-analyze`

### Assets Inspect

- `POST /api/v1/tasks/assets-inspect`

### Session / Recovery

- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/history`
- `GET /api/v1/sessions/{session_id}/tasks`
- `POST /api/v1/sessions/{session_id}/clear`

### Shared task recovery

- `GET /api/v1/tasks/recent`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/user-view`
- `GET /api/v1/tasks/{task_id}/debug-view`
- `GET /api/v1/tasks/{task_id}/trace`
- `GET /api/v1/tasks/{task_id}/artifacts`

### Knowledge Base Admin

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`
- `POST /api/v1/knowledge-base/import`
- `POST /api/v1/knowledge-base/reindex`
- `GET /api/v1/knowledge-base/documents`
- `GET /api/v1/knowledge-base/documents/{doc_id}`
- `DELETE /api/v1/knowledge-base/documents/{doc_id}`
- `GET /api/v1/knowledge-base/jobs/{job_id}`
- `POST /api/v1/knowledge-base/jobs/{job_id}/retry`

`POST /api/v1/knowledge-base/import` 的 `source_type=text` 现在同时兼容 `text` 和 `content` 字段，并会保存 `domain`、`doc_type`、`tags`、`metadata`。如果前端后续做“补充知识库”面板，建议先支持文本/code/html 的路径刷新和 inline text 导入，PDF/DOCX 作为增强导入入口即可。

`GET /api/v1/knowledge-base/status` 现在会返回 `ingestion_pipeline`、`format_groups`、`parser_dependencies`、`knowledge_domains`。这些字段适合放到 Debug View 或知识库设置页，不需要作为普通用户主流程强提示。

### Project Inventory

后端新增项目快照接口，供 UE 插件后续把 Asset Registry 和代码文件扫描结果提交给后端。当前它不替代 5 个核心主菜单，但已经最小接入 Agent Chat / Project QA：用户询问项目资产、资产设置或代码文件索引时，后端会优先查询 Project Inventory，并把命中结果放入 `data.inventory` 和 `debug_view.inventory`。

- `POST /api/v1/project-inventory/snapshot`
- `GET /api/v1/project-inventory/summary`
- `GET /api/v1/project-inventory/assets`
- `GET /api/v1/project-inventory/assets/{asset_id}`
- `GET /api/v1/project-inventory/code-files`
- `POST /api/v1/project-inventory/query`

前端扫描边界：

- 代码文件可以复用当前 `Source/Plugins` 扫描结果，提交 `file_path`、`module_name`、`file_type`、`classes` 等摘要。
- 资产必须由 UE 插件通过 Asset Registry / Editor API 采集，后端不直接解析 `.uasset`。
- StaticMesh 建议提交 Nanite、LOD、碰撞、材质槽、三角面摘要。
- Blueprint 建议提交父类、组件、Tick、Replication、接口、暴露变量摘要。
- Material / Texture / World / Niagara / Sound / DataAsset 等常见资产可按 `settings` 和 `properties` 扩展。

前端可以先把这些接口放进 Debug View 或 Monitor，不必立刻做普通用户管理面板。若 UE 插件暂未提交 snapshot，Project QA 会正常降级到知识库 RAG 或普通回答。

## 6. 双视图契约

### User View

用户面板只消费：

- `user_view.title`
- `user_view.text`
- `user_view.blocks`
- `user_view.citations_preview`
- `user_view.quick_actions`
- `user_view.status_hint`

不要自己从 `data` 反推主显示文本。

### Debug View

调试面板建议消费：

- `debug_view.intent`
- `debug_view.route`
- `debug_view.skill`
- `debug_view.retrieval`
- `debug_view.tools`
- `debug_view.step_results`
- `debug_view.metrics`
- `debug_view.session_summary`
- `debug_view.memory_summary`
- `debug_view.raw_result`
- `trace_summary`
- `usage`

`debug_view.skill` 是后端本轮新增的稳定调试块，建议 Debug View 直接展示：
- `skill_id`
- `collector`
- `rules`
- `retrieval_domains`
- `retrieval_active`
- `retrieval_mode`
- `projector_outputs`

同一份信息也会出现在 `data.skill` 和 `trace_summary.skill_id`。普通用户主界面不需要展示这些字段，但前端排查“为什么这次走了 RAG / 为什么没走 RAG / 当前面板对应哪个 Skill”时应优先看这里。

后端内部实现状态：`CodeReviewSkill`、`CodeGenerateSkill`、`LogsAnalyzeSkill`、`AssetsInspectSkill` 已经使用独立 executor。这个变化不改变前端调用方式，前端继续使用当前 5 个核心接口即可；调试时可通过 `debug_view.skill.skill_id` 分别看到本次任务对应的固定 Skill。

## 7. Agent Chat / Project QA 的前后端分工

前端职责：

- 传真实用户消息
- 传真实编辑器上下文
- 不自行判断“这次要不要检索知识库”

后端职责：

- 判断当前应走 `direct_answer` 还是 `project_qa`
- 需要时触发知识库检索
- 返回 citations 与调试路由信息

关键调试字段位于 `debug_view.route`：

- `decision_source`
- `project_signal_strength`
- `context_present`
- `project_hint_count`
- `context_reference_present`
- `explicit_kb_scope`
- `llm_route_decision`

## 8. 目标 UI 形态

后续前端不要再把所有功能都做成同一种聊天 UI。只有 `Agent Chat / Project QA` 保留完整聊天时间线，其余 4 个功能都应做专用面板。

### Agent Chat / Project QA

- 完整聊天时间线
- 底部固定输入框
- 回答中显示 citation/source
- Debug View 可展开 route / retrieval / trace

### Code Review

推荐 UI：

- 文件搜索框
- 代码文件列表
- `Analyze Selected File` 按钮
- 下方结果区

新增接口：

- `POST /api/v1/tasks/code-review/files`

请求体建议：

```json
{
  "project_root": "D:/MyProject",
  "source_roots": ["Source", "Plugins"],
  "query": "MyActor",
  "limit": 200
}
```

选中文件后再提交：

```json
{
  "payload": {
    "project_root": "D:/MyProject",
    "source_roots": ["Source"],
    "file_path": "Source/MyModule/MyActor.cpp"
  }
}
```

### Code Generate

推荐 UI：

- 顶部需求输入框
- `Generate` 按钮
- 时间线里保留用户需求
- 生成结果不要整段堆在聊天气泡里
- 结果应渲染为代码按钮 / Tab / 结果列表

前端重点消费字段：

- `data.generated_items`
- `data.reference_lookup`
- `data.generation_mode`
- `data.retrieved_references`

含义：

- `generated_items`：渲染为代码结果按钮、Tab 或列表
- `reference_lookup`：表示这次是否命中了代码参考
- `generation_mode`：区分 live LLM 生成、参考增强生成或模板回退

### Logs Analyze

推荐 UI：

- 日志来源输入 / 文件选择区
- 日志片段粘贴区，可为空
- 日志预览区，优先展示实际将提交的片段或文件窗口
- `Analyze Log` 按钮
- 结构化结果区
- 可选“发送到聊天”继续追问

日志分析现在不再强制 `log_text`。前端可以三选一提交：

- `log_text` / `selected_log_text` / `log_excerpt` / `error_excerpt` / `error_lines`：用户只粘贴几行 Error/Fatal 时使用。
- `log_file_path` / `log_path` / `file_path`：用户从文件选择器选择日志文件时使用。
- `log_source`：既可以作为来源标签，也可以在看起来像路径时作为兼容路径读取。

建议 payload：

```json
{
  "log_source": "Saved/Logs/MyProject.log",
  "log_file_path": "F:/Epic Games/project/RushBa/Saved/Logs/RushBa.log",
  "selected_log_text": "LogTemp: Error: Access violation...",
  "notes": "用户点击 Play 后崩溃",
  "attachment_paths": ["F:/Epic Games/project/RushBa/Saved/Crashes/CrashContext.runtime-xml"],
  "time_range": {"start": "...", "end": "..."},
  "line_window": {"start": 120, "end": 220}
}
```

读取规则：

- 如果提交了 `log_text` / `selected_log_text` 这类文本片段，后端优先分析片段，不会强制读取整个文件。
- 如果没有提交文本片段，但提交了 `log_file_path`，后端会读取该文件的尾部窗口；如果带 `line_window`，则读取指定行号范围。
- 如果同时提交文本片段和文件路径，默认只把文件路径作为来源记录；只有 `include_file_context=true` 时才额外读取文件上下文。
- `attachment_paths` / `attachments` 只作为辅助文本附件读取，后端仍保持只读，不写入、不删除、不移动任何日志文件。

前端应重点消费 `user_view.blocks` 中的这些结构：

- `Log Summary`
- `LLM Analysis`
- `Issue Families`
- `Suggested Actions`
- `Captured Log Window`
- `Affected Modules / Resources`

Debug View 可查看：

- `data.input_context.input_mode`
- `data.input_context.read_diagnostics`
- `data.input_context.attachment_diagnostics`
- `data.parser_diagnostics.input_collection`
- `data.llm_analysis.status/reason_code/text`
- `data.retrieval_quality_gate.status/reason/top_score/confidence`

日志发现、文件选择和编辑器日志窗口采集仍属于插件职责；后端只读取前端显式传入的文本或路径。

### Assets Inspect

推荐 UI：

- 当前选中资产列表
- `Inspect Selected Assets` 按钮
- 结果分组显示：
  - 命名与规则
  - 类型说明
  - 依赖与关系摘要

建议 payload：

```json
{
  "asset_items": [
    {
      "asset_path": "/Game/Demo/BP_Hero",
      "asset_type": "Blueprint",
      "package_path": "/Game/Demo",
      "dependencies": ["/Game/Demo/SM_Hero"],
      "referencers": ["/Game/Demo/Maps/MainMap"]
    }
  ]
}
```

后端会返回这些重点字段：

- `data.violations`
- `data.rename_suggestions`
- `data.type_insights`
- `data.relationship_summary`
- `data.supporting_notes`

`user_view.blocks` 已按最终面板分组输出：

- `Inspection Summary`
- `Rule Findings`
- `Rename Suggestions`
- `Asset Types`
- `Relationship Summary`
- `Supporting Rules Summary`

## 9. Session 恢复链

建议前端本地持久化 `session_id`。

恢复顺序：

1. `GET /api/v1/sessions/{session_id}`
2. `GET /api/v1/sessions/{session_id}/history`
3. `GET /api/v1/sessions/{session_id}/tasks`
4. 如果 session 不存在，再 `POST /api/v1/sessions`

## 10. 当前边界

- `events/stream` 仍是事件回放，不是 token 实时流
- `code_generate` 不直接写用户工程，也不做编译验证
- 资产关系图仍依赖插件从编辑器侧采集元数据
- 后端契约已可用于前端统一调整；后续若只做后端内部优化，应保持向后兼容

## 11. 2026-04-21 UE 联调修复后的前端注意事项

### Agent Chat / Project QA

后端已修复 LLM 路由复核成功分支返回 `None` 导致的 500。前端仍只需要发送真实聊天消息和编辑器上下文，不需要自己决定是否 RAG。

Debug View 可继续读取：
- `debug_view.route.llm_route_decision.status`
- `debug_view.route.llm_route_decision.route_type`
- `debug_view.route.llm_route_decision.confidence`
- `debug_view.route.llm_route_decision.reason`
- `debug_view.route.llm_route_decision.error`

当 LLM 复核失败、返回非法 JSON 或返回空结构时，后端会把 `status` 标记为 `skipped` 并沿用原始路由，接口不应再 500。

### Code Review 文件列表

`POST /api/v1/tasks/code-review/files` 现在稳定返回以下字段，前端列表优先使用这些字段：

```json
{
  "file_path": "Source/RushBa/MyActor.cpp",
  "label": "MyActor.cpp",
  "module_name": "RushBa",
  "file_type": "cpp",
  "relative_path": "Source/RushBa/MyActor.cpp"
}
```

前端提交审查时继续把 `file_path` 原样放入 `payload.file_path`。接口支持：
- Windows 路径、空格路径、正反斜杠混用、尾部斜杠
- `Source` 和 `Plugins` 扫描
- 按相对路径、文件名、模块名进行大小写不敏感搜索
- 默认 `limit = 200`

列表为空时读取 `scan_diagnostics.empty_reason`：
- `project_file_access_error`
- `source_roots_not_found`
- `query_filtered_empty`
- `no_matching_code_extensions`
- `no_code_files_found`

### Code Review 审查结果调试字段

文件审查成功时，`data.review_scope` 和 `debug_view.raw_result.review_scope` 会包含：
- `resolved_absolute_path`
- `read_status`
- `content_length`
- `applied_focus`
- `source_roots`

如果 `read_status = "error"` 或存在 `load_error`，前端应把结果当成读文件失败提示，而不是普通审查结论。

### Assets Inspect

前端应继续发送 `asset_items[].asset_name`。后端现在会对默认/占位名做确定性 lint，例如：
- `NewMap`
- `Untitled`
- `NewBlueprint`
- `NewMaterial`
- `NewTexture`
- `NewDataAsset`

`World` 类型资产遇到 `NewMap` 这类名称时，后端会返回 warning，并建议使用 `L_` 或 `Map_` 项目语义命名。

前端渲染问题列表时优先读取：
- `user_view.blocks[].block_type == "issues"`
- `user_view.blocks[].data.items[].severity`
- `user_view.blocks[].data.items[].reason`
- `user_view.blocks[].data.items[].suggestion`

### user_view.blocks 类型

后端当前优先使用这些稳定类型：
- `summary`
- `issues`
- `recommendations`
- `generated_items`
- `references`
- `next_steps`

前端可以保留未知 `block_type` 的通用 fallback，但主 UI 建议按以上类型做专门样式。

## 12. 2026-04-21 二次联调补充

### 用户可见语言

前端仍可以本地化 `block_type`、状态枚举、severity、`read_status`、`review_scope` 这类派生 UI 标签；但自然语言解释由后端负责。

后端当前承诺这些用户可见字段跟随最终输出语言：
- `user_view.title`
- `user_view.text`
- `user_view.blocks[].title`
- `user_view.blocks[].text`
- `user_view.blocks[].data.items[].reason`
- `user_view.blocks[].data.items[].suggestion`
- `user_view.quick_actions[].label`

Debug View、raw JSON key、API 字段名、代码符号、文件路径、资产名、`block_type` 枚举仍保持英文或原文。

### Code Review 输出块

`POST /api/v1/tasks/code-review` 现在会固定给前端更完整的用户视图，建议按顺序渲染：

```text
summary -> llm_analysis -> issues -> recommendations -> references -> next_steps
```

即使项目知识库没有命中足够证据，后端也会基于当前文件内容和通用 Unreal/C++/C# 规则返回可参考结果，并在 `references` 块中说明 fallback 来源。

前端可优先读取：
- `user_view.blocks`
- `data.llm_analysis`
- `data.localized_review.issues`
- `data.localized_review.recommendations`
- `data.localized_review.references`
- `data.localized_review.next_steps`
- `data.llm_review`

`data.llm_review.ok = true` 表示后端已用配置的 LLM 做过综合审查；`false` 时仍有确定性规则扫描结果可展示。常见跳过原因包括 `missing_openai_api_key`、`json_parse_failed`、`file_read_failed_or_empty_source`。

`llm_analysis` 是给普通用户看的自然语言分析卡片。`status=completed` 表示已由 LLM 综合解释；`status=skipped` 表示 LLM 未执行，前端应显示为轻提示，不要当成任务失败。

### Code Review 读取失败

如果 `data.review_scope.read_status = "error"` 或存在 `data.review_scope.load_error`，前端应把结果作为文件读取失败处理。此时 `user_view.status_hint = "read_error"`，`issues` 块会显示具体错误，不应把它当成正常审查结论。

### Assets Inspect 中文 Highlight

Assets Inspect 的 Highlight / `issues` block 中，`reason` 和 `suggestion` 已按最终输出语言本地化。中文工作流下选择 `NewMap` / `World` 时，前端应能直接显示中文原因与中文改名建议，例如说明默认占位命名风险，并保留 `L_` / `Map_` 前缀原文。

Assets Inspect 现在同样会返回 `llm_analysis` 块，建议放在检查摘要后、规则问题前。该块用于解释资产命名、类型、依赖关系的综合影响；LLM 未配置时会返回 `status=skipped`，原有规则问题、重命名建议、资产类型和关系摘要仍然可用。

## 13. 2026-04-23 Project Inventory / LLM Analysis 契约补齐

本轮已按 UE 前端回传的联调文档补齐几个稳定字段，前端可以直接按下面规则消费。

### Project Inventory Snapshot

`POST /api/v1/project-inventory/snapshot` 请求体现在明确支持：

- `snapshot_time`：UE 侧扫描时间；如果不传，后端使用当前 UTC 时间。
- `scan_diagnostics`：UE 侧扫描诊断，例如资产扫描数量、代码扫描数量、失败原因。
- `code_files[].last_modified`：前端可继续传这个字段；后端会同时保存为 `last_modified` 和 `modified_at`。

成功响应中的 `snapshot` 会稳定包含：

- `status: "saved"`
- `snapshot_id`
- `asset_count`
- `code_file_count`
- `summary.asset_count`
- `summary.code_file_count`
- `summary.asset_type_counts`
- `summary.code_file_type_counts`
- `scan_diagnostics`

`GET /api/v1/project-inventory/summary` 也会返回 `scan_diagnostics`，方便 Debug View 展示“本次扫描从 UE 侧采集到了什么”。

### Agent Chat / Project QA Inventory

当用户在 Agent Chat 里问“工程里有哪些资产”“有哪些 C++ 文件”“某个 StaticMesh 的 Nanite / LOD / 碰撞 / 材质设置是什么”等项目事实问题时，后端会优先查询 Project Inventory。命中结果继续放在：

- `data.inventory`
- `debug_view.inventory`

如果没有 snapshot，后端会正常降级到知识库 RAG 或普通回答，不要求前端阻断聊天。

### LLM Analysis Skipped 展示

Code Review 和 Assets Inspect 的 `llm_analysis` 现在同时返回：

- `status`：`completed` 或 `skipped`
- `reason`：给用户看的本地化自然语言原因
- `reason_code`：给前端和 Debug View 判断用的稳定枚举

常见 `reason_code`：

- `missing_openai_api_key`
- `missing_chat_model`
- `json_parse_failed`
- `request_failed`
- `file_read_failed_or_empty_source`
- `empty_asset_selection`
- `not_attempted`

前端推荐展示 `reason`，调试面板再展示 `reason_code`。`status=skipped` 不是任务失败，只表示本次没有执行在线 LLM 综合解释，原有规则扫描、引用、建议仍然有效。

## 14. 2026-04-24 会话恢复 / Agent Chat 项目级 Inventory 工具

本轮没有新增主菜单，但有两处会影响前端联调和测试验收。

### Session History 恢复

后端现在会把 `assistant_message` 也持久化到 session history，并按 `created_at + message_id` 稳定排序返回。

前端恢复建议：

1. `GET /api/v1/sessions/{session_id}/history`
2. 直接按返回顺序渲染，不要再按本地发送时间重排
3. 用户发下一条消息时，把后端返回的完整 history 作为基线，再在尾部追加新的 user message

预期效果：

- 恢复后不应再出现两个 user 连在一起、assistant 丢失、或顺序错乱
- 正常顺序应是 `user -> assistant -> user -> assistant`

### Agent Chat / Project QA Inventory 工具选择

项目级资产盘点问题只属于 `Agent Chat / Project QA`。例如“当前项目有哪些蓝图资产”“项目里哪些 StaticMesh 开启了 Nanite”“某模块有哪些 C++ 文件”，前端仍只调用：

```http
POST /api/v1/chat/runs
```

后端路由层会把这类自由聊天问题提升为 `project_qa`，并选择只读工具 `query_project_inventory`。

新增可消费字段：

- `data.inventory`
- `data.tool_plan`
- `debug_view.inventory`
- `debug_view.tool_plan`
- `debug_view.route.selected_tool_id = "query_project_inventory"`
- `debug_view.tools[]` 中的 `query_project_inventory`
- `step_results[]` 中的 `query_project_inventory`

前端建议：

- 聊天时间线显示 `assistant_message`
- 结果区继续按 `user_view.blocks` 渲染
- 如果 `data.inventory.items` 非空但用户视图里没有单独块，前端可以补一个“项目资产匹配”卡片作为兜底
- 不要把这类自由聊天问题转发到 `POST /api/v1/tasks/assets-inspect`

### Assets Inspect 边界

Assets Inspect 面板只处理 Content Browser 当前选中资产和用户在该面板提交的 inspection 要求。它不负责回答“当前项目有哪些资产”这类项目级盘点问题。

### Code Review / Assets Inspect 的 LLM 状态

后端已经对这两类任务做了更紧凑的 prompt 和更宽松的 timeout，但前端展示逻辑不变：

- `llm_analysis.status=completed`：按正常 LLM 综合分析展示
- `llm_analysis.status=skipped`：显示轻提示，不作为失败
- `reason` 给用户看，`reason_code` 给 Debug View 看

## 15. 2026-04-24 二次排查：Inventory 空结果与 Code Review LLM 兜底

本轮后端没有要求前端新增 UI，但补强了两个测试时容易误判的返回契约。

### Agent Chat / Project Inventory

用户在 Agent Chat 输入以下问法都应由后端自动选择 `query_project_inventory`：

- `我当前项目的蓝图资产有哪些，你列一下`
- `当前项目蓝图资产有哪些`
- `当前项目有哪些 cpp 文件`
- `某个 StaticMesh 的 Nanite / LOD / collision / material 设置是什么`

前端继续只调用：

```http
POST /api/v1/chat/runs
```

后端现在会在 `data.inventory.summary.empty_reason` 返回空结果原因：

- `no_project_inventory_snapshot`：当前 `project_id/project_name` 没有提交过 Project Inventory 快照。
- `no_matching_inventory_items`：有快照，但本次 query 没匹配到资产或代码文件。

当 `empty_reason = "no_project_inventory_snapshot"` 时，Agent Chat 不再空回复，也不会只说“知识库没找到”，而是明确提示用户先在 UE 插件 Debug View 点击 `Submit Inventory`。前端已有 `data.inventory` fallback 的话无需改 UI，只建议测试时优先看：

- `debug_view.route.selected_tool_id`
- `data.tool_plan`
- `data.inventory.summary.has_snapshot`
- `data.inventory.summary.empty_reason`
- `data.inventory.items`

注意：后端现在不会在传入了明确 `project_id/project_name` 但找不到快照时偷用其他项目的 latest snapshot，避免多项目测试时串数据。

### Code Review LLM 状态

后端现在把 Code Review 的 LLM 状态拆成三类，前端按已有 `llm_analysis` 卡片展示即可：

- `data.review_scope.read_status = "ok"` 且 `content_length > 0`：后端确实读到了选中的代码文件。
- `data.llm_analysis.reason_code = "missing_selected_code_content"`：没有收到可解析的选中文件内容，通常是前端没有提交 `payload.project_root + payload.file_path`，或文件不在 `source_roots` 允许范围内。
- `data.llm_review.reason = "completed_text_fallback"`：LLM 已经返回内容，但没有严格按 JSON schema 返回；后端会尽量修复常见 JSON-like 格式，修复失败时也会从原文提取 summary / issue / suggestion，`llm_analysis.status = "completed"`，不再显示 skipped。

前端暂不需要新增字段渲染。测试 Code Review 时，如果仍看到 skipped，优先检查：

- `data.review_scope.source_kind`
- `data.review_scope.read_status`
- `data.review_scope.load_error`
- `data.review_scope.resolved_absolute_path`
- `data.llm_review.reason`
- `data.llm_review.error`

## 16. 2026-04-24 Code Review 高亮按钮展示字段

Code Review 面板没有聊天输入框，所以高亮按钮 / Highlights 弹窗应只消费后端的用户展示字段，不要消费 Debug 或 raw LLM 字段。

推荐读取顺序：

- 概要：`user_view.blocks[block_type="summary"].text`
- LLM 分析结果：`user_view.blocks[block_type="llm_analysis"].text`
- LLM 要点：`user_view.blocks[block_type="llm_analysis"].data.key_points`
- 问题列表：`user_view.blocks[block_type="issues"].data.items`
- 建议列表：`user_view.blocks[block_type="recommendations"].data.items`
- 证据依据：`user_view.blocks[block_type="references"].data.items`
- 下一步：`user_view.blocks[block_type="next_steps"].data.items`

不要用于普通用户高亮弹窗的字段：

- `data.llm_review`
- `debug_view.raw_result`
- `debug_view.normalized_request`
- `artifacts[].content`
- `data.analysis_input.source_excerpt`

这些字段可以继续放在 Debug View / Raw JSON 里。它们可能包含完整 JSON、源码片段、LLM 原始响应或诊断信息，不适合直接展示给普通用户。

后端本轮已保证：

- `user_view.blocks[].text` 是自然语言展示文本。
- `data.llm_analysis.text` 是自然语言展示文本。
- 如果 LLM 返回 JSON-like 文本但解析失败，后端会先尝试修复 JSON-like 格式；仍不合法时会提取可展示的 summary / title / reason / suggestion。原始文本只留在 `data.llm_review.text` 给 Debug View。

### Code Review 编辑器侧必传信息

前端暂不需要新增编辑器采集项，但每次审查选中文件时必须稳定提交：

```json
{
  "payload": {
    "project_root": "F:/Epic Games/project/RushBa",
    "source_roots": ["Source", "Plugins"],
    "file_path": "Source/RushBa/Player/RBPlayerCharacter.cpp",
    "focus": "General"
  },
  "context": {
    "active_panel": "CodeReview",
    "current_file": "Source/RushBa/Player/RBPlayerCharacter.cpp",
    "current_module": "RushBa"
  }
}
```

`file_path` 应优先使用 `POST /api/v1/tasks/code-review/files` 返回的 `file_path` 或 `relative_path`。如果后端和 UE 编辑器不在同一台机器、后端无法读取这个路径，再考虑额外发送 `payload.file_content`；当前本地个人作品场景下，`project_root + file_path` 就够。

## 17. 2026-04-24 语言切换按钮接入

本轮后端已经把输出语言策略收口为“前端按钮优先，默认中文”。UE 前端需要新增一个轻量语言切换控件，建议放在 Agent Chat 顶部工具条或插件全局设置区，只有两个选项：

- `中文`：默认值，发送 `zh-CN`
- `English`：发送 `en-US`

每次调用后端任务接口时，都在 `runtime_options` 里带上：

```json
{
  "runtime_options": {
    "preferred_output_language": "zh-CN"
  }
}
```

用户切换英文后改为：

```json
{
  "runtime_options": {
    "preferred_output_language": "en-US"
  }
}
```

后端兼容 `auto`，但新策略下 `auto` 不再跟随用户输入语言，而是按以下顺序决策：

- 用户消息里明确要求“用英文回答 / 用中文回答”或 `reply in English / reply in Chinese`
- `runtime_options.preferred_output_language`
- session 已保存的语言偏好
- `context.editor_state.locale` / `context.editor_state.culture` 等编辑器语言字段
- 默认 `zh-CN`

注意：消息内临时指定语言是单轮覆盖，不会改写 session 偏好；前端按钮传入的 `zh-CN/en-US` 会写入 session，后续 `auto` 请求也会沿用。

如果前端在启动或恢复会话时希望提前同步语言，可以调用：

```http
POST /api/v1/sessions
```

```json
{
  "session_id": "rushba_agent_chat",
  "project_name": "RushBa",
  "preferred_output_language": "zh-CN",
  "profile_id": "default"
}
```

后端会在所有响应的 `locale` 中返回：

- `detected_input_language`：后端检测到的用户输入语言，只用于诊断
- `preferred_output_language`：本轮采用的偏好语言
- `final_output_language`：最终用户可见输出语言
- `language_source`：来源，可能是 `explicit_override`、`message_override`、`session_preference`、`editor_locale` 或 `default`

前端渲染时不需要自己翻译后端文本，直接展示 `assistant_message`、`user_view.text`、`user_view.blocks[].title/text`、`data.llm_analysis.text` 等用户可见字段即可。Debug View、raw JSON、枚举值、路径、代码符号仍然保持英文或原文。

### 前端本轮需要读取的文件

- `docs/frontend-unified-handoff.md`：主交接文档，重点看本节和 Code Review 高亮字段章节
- `docs/backend-user-guide.md`：需要理解后端语言策略、知识库和模型配置时查看
- `docs/improveplan.md`：只作为阶段计划和边界确认，不需要按它逐条实现 UI

## 18. 2026-04-25 Context Bundle v1 接入说明

本轮后端完成了 Context Manager v1。主 UI 暂不强制修改；Agent Chat、Project QA、Code Review、Code Generate 的现有请求方式保持不变。若 UE 前端想增强 Debug View，建议新增一个可折叠的 `Context Bundle` 区块。

建议读取字段：

- `debug_view.context_bundle.version`
- `debug_view.context_bundle.input_summary`
- `debug_view.context_bundle.recent_messages`
- `debug_view.context_bundle.editor_context`
- `debug_view.context_bundle.tool_context`
- `debug_view.context_bundle.session_summary`
- `debug_view.context_bundle.budget`
- `debug_view.memory_summary.context_budget`

展示建议：

- 普通用户界面不要展示完整 Context Bundle。
- Debug View 可以用卡片展示 `route_type`、`latest_user_message`、最近消息数量、最近工具摘要数量、`estimated_chars / char_budget`。
- `tool_context` 只代表最近工具任务摘要，不代表它们已经写入聊天历史。
- 如果 `budget.warnings` 非空，Debug View 可以显示轻提示，说明上下文已按摘要/截断策略处理。

前端是否必须修改：

- 主 UI：不需要。
- Debug View：可选增强。如果本轮不改，也不会影响功能测试。

如果 UE 前端后续接入这个 Debug 区块，回传交接文档时请说明：

- 是否展示了 `Context Bundle` 分区。
- 是否展示了 `tool_context` 与 `recent_messages` 的区别。
- 是否展示了 `budget.warnings`。
- 测试时 Agent Chat、Project QA、Code Review 是否还能正常渲染原有 `user_view`。

## 19. 2026-04-25 Memory Summary v1 接入说明

本轮后端完成轻量会话记忆摘要。主 UI 不需要修改，聊天时间线仍然以 `/api/v1/sessions/{session_id}/history` 返回的真实消息为准。

可选 Debug View 字段：

- `GET /api/v1/sessions/{session_id}` -> `item.memory_summary`
- `debug_view.memory_summary.updated_session_memory`
- `debug_view.context_bundle.session_summary`

推荐展示方式：

- 在 Debug View 的 Context / Memory 区显示 `memory_summary.version`、`strategy`、`message_count`、`summarized_message_count`。
- 普通用户界面不要展示完整 `summary_text`，避免把调试摘要误认为正式聊天回复。
- 如果 `updated_session_memory.status = "not_triggered"`，说明消息数量还没到摘要阈值，不是错误。

前端是否必须修改：

- 主 UI：不需要。
- Debug View：可选增强。如果本轮不改，也不会影响测试。

如果 UE 前端后续接入本区块，请在回传交接文档里说明：

- 是否展示了 session 顶层 `memory_summary`。
- 是否展示了 `updated_session_memory.status`。
- 是否仍然只用 `/history` 渲染聊天时间线，没有把 `summary_text` 混入普通聊天气泡。

## 20. 2026-04-25 Agent Decision Trace v1 接入说明

本轮后端新增 `debug_view.agent_decision_trace`。主 UI 不需要修改；这是 Debug View / 面试演示用字段，用来解释一次请求为什么走某条 route、用了哪些上下文、是否检索、调用了哪个 Skill、是否发生 fallback。

建议读取字段：

- `debug_view.agent_decision_trace.version`
- `debug_view.agent_decision_trace.summary.route_type`
- `debug_view.agent_decision_trace.summary.skill_id`
- `debug_view.agent_decision_trace.summary.retrieval_mode`
- `debug_view.agent_decision_trace.summary.memory_status`
- `debug_view.agent_decision_trace.summary.finish_reason`
- `debug_view.agent_decision_trace.decisions`

`decisions` 当前固定包含：

- `input_summary`
- `language_decision`
- `intent_decision`
- `context_decision`
- `retrieval_decision`
- `tool_decision`
- `memory_decision`
- `fallback_decision`
- `final_response_plan`

展示建议：

- Debug View 可以做成一组折叠卡片或时间线。
- 每个 decision 读取 `decision`、`reason`、`source`、`confidence`、`details`、`warnings`。
- 普通用户界面不要展示完整 Decision Trace。

前端是否必须修改：

- 主 UI：不需要。
- Debug View：可选增强。如果本轮不改，不影响功能测试。

如果 UE 前端后续接入本区块，请在回传交接文档里说明：

- 是否展示了 `Agent Decision Trace` 分区。
- 是否展示了 `summary` 五个核心字段。
- 是否能展开查看每个 decision 的 `reason/source/details/warnings`。
- Agent Chat、Project QA、Code Review 三类任务是否仍能正常渲染原有 `user_view`。

## 21. 2026-04-25 RAG Readiness 接入说明

本轮后端增强了 `GET /api/v1/knowledge-base/status` 的返回，用于 Debug View / Monitor 展示知识库和检索链路是否可用。主 UI 不需要修改。

建议读取字段：

- `summary.effective_mode`
- `summary.rag_readiness.status`
- `summary.rag_readiness.lexical_ready`
- `summary.rag_readiness.embedding_ready`
- `summary.rag_readiness.vector_store_ready`
- `summary.rag_readiness.usable_for_project_qa`
- `summary.rag_readiness.degraded_reasons`
- `summary.rag_readiness.indexed_documents`
- `summary.rag_readiness.indexed_chunks`
- `summary.rag_readiness.domain_counts`
- `summary.rag_readiness.eval_command`

展示建议：

- Monitor / Debug View 可以显示一个 KB readiness 小卡片。
- `status=degraded` 不一定是错误；如果 `lexical_ready=true` 且 `usable_for_project_qa=true`，Project QA 仍可用，只是没有走向量检索。
- 普通用户界面只需要在 RAG 无结果时展示现有 `user_view` 提示，不要直接暴露复杂指标。

前端是否必须修改：

- 主 UI：不需要。
- Debug View / Monitor：可选增强。

如果 UE 前端后续接入本区块，请在回传交接文档里说明：

- 是否展示 KB readiness 小卡片。
- 是否能区分 `degraded but usable` 与 `empty/unusable`。
- 是否仍然保持 Agent Chat / Project QA 主界面只展示 citations 与用户可读回答。

## 22. 2026-04-25 Skill Protocol v1 接入说明

本轮后端把 5 个核心能力统一成 `skill_protocol_v1`。主 UI 不需要修改；现有 Agent Chat、Code Review、Code Generate、Logs Analyze、Assets Inspect 的请求方式保持不变。

可选 Debug View 字段：

- `debug_view.skill.protocol_version`
- `debug_view.skill.skill_id`
- `debug_view.skill.title`
- `debug_view.skill.panel_id`
- `debug_view.skill.frontend_ui`
- `debug_view.skill.selected_tool_id`
- `debug_view.skill.lifecycle.collector.status`
- `debug_view.skill.lifecycle.rules.status`
- `debug_view.skill.lifecycle.retrieval.status`
- `debug_view.skill.lifecycle.llm.status`
- `debug_view.skill.lifecycle.llm.reason`
- `debug_view.skill.lifecycle.projector.status`

系统能力接口也会返回静态 manifest：

- `GET /api/v1/system/capabilities`
- `capabilities.skill_architecture.protocol_version = "skill_protocol_v1"`
- `capabilities.skill_architecture.runtime_lifecycle_field = "debug_view.skill.lifecycle"`
- `capabilities.skill_catalog[]`

展示建议：

- Debug View 可以把 Skill 显示成一条轻量流水线：`collector -> rules -> retrieval -> llm -> projector`。
- `llm.status = skipped` 不一定是错误；请结合 `llm.reason` 展示，例如 `missing_openai_api_key` 表示未配置 LLM，`degraded_fallback` 表示走了降级回答。
- 普通用户主界面仍然优先渲染 `user_view`，不要把 `debug_view.skill` 当作聊天内容展示。

前端是否必须修改：

- 主 UI：不需要。
- Debug View：可选增强。

如果 UE 前端后续接入本区块，请在回传交接文档里说明：

- 是否展示 Skill lifecycle 流水线。
- 是否把 `llm.reason` 作为机器码处理，而不是当作完整自然语言回答。
- Code Review 高亮按钮是否仍只消费 `user_view.blocks` / `data.llm_analysis`，没有误用 `debug_view.skill` 或 raw JSON。

## 23. 2026-04-25 Local Grep Retrieval v1 接入说明

后端新增本地 markdown/code grep 检索，用于在未接入 embedding / Qdrant 时提升 Code Generate、Project QA、Code Review 的可用性。主 UI 不需要修改。

当前后端行为：

- `Code Generate` 会优先检索本地 `knowledge/code-reference`、`knowledge/examples`、`knowledge/engine-notes` 等文件。
- `Project QA` 在 RAG 无命中时会 fallback 到 local grep。
- `Code Review` 仍以选中文件和规则扫描为主，知识检索可补充 team rules / engine notes。

可选 Debug View 字段：

- `debug_view.local_search.status`
- `debug_view.local_search.reason`
- `debug_view.local_search.summary.result_count`
- `debug_view.local_search.summary.domain_filters`
- `debug_view.local_search.summary.terms`
- `debug_view.local_search.items[].title`
- `debug_view.local_search.items[].source_path`
- `debug_view.local_search.items[].domain`
- `debug_view.local_search.items[].snippet`
- `debug_view.local_search.items[].matched_terms`
- `debug_view.local_search.items[].score`

Knowledge Base 状态接口新增：

- `GET /api/v1/knowledge-base/status`
- `summary.local_search_readiness.status`
- `summary.local_search_readiness.searchable_files`
- `summary.local_search_readiness.domain_counts`
- `summary.local_search_readiness.source_paths`

前端是否必须修改：

- 主 UI：不需要。
- Debug View / Monitor：可选新增 `Local Search` 折叠区块。

如果 UE 前端后续接入本区块，请在回传交接文档里说明：

- 是否展示 local search 命中文件、domain 和 snippet。
- 是否在 Code Generate Debug View 中展示 `data.reference_lookup.local_reference_count`。
- 是否仍然保持普通用户界面只渲染 `user_view`，不直接展示 raw local search JSON。

## 24. 2026-04-26 知识库范围与 Code Generate 展示修正

本轮后端把默认知识库范围收口为 `KB_SOURCE_PATHS=./knowledge`。这可以避免 Agent Chat / Project QA 在用户询问 UE 项目问题时引用后端开发文档，例如 `backend.md`、`forward.md`、`docs/improveplan.md` 或交接文档。

前端影响：

- 主 UI 不需要改接口。
- 如果 Debug View / Monitor 展示知识库来源路径，正常情况下应看到 `knowledge/...` 或用户手动导入的 UE 项目资料。
- 如果仍看到 `backend.md` / `forward.md` / `docs/...`，说明后端旧索引还没清理，需要调用 `POST /api/v1/knowledge-base/reindex`。

Code Generate 展示规则也需要统一理解：

- 后端不会创建真实文件，不会写入 UE 工程。
- `data.write_policy.written_to_disk=false` 是稳定字段。
- `data.generated_items[].write_status=not_written` 和 `data.generated_items[].is_virtual=true` 表示这是 API 返回的虚拟草稿。
- `data.generated_items[].file_path` 是建议放置路径或虚拟草稿名，不是磁盘上已经存在的文件。
- 前端 Code Generate 面板应把 `generated_items` 渲染为“代码结果按钮 / Tab / 列表”，点击后展示 `generated_items[].code`。
- 不建议在普通用户 UI 文案里写“已生成文件 draft.txt”；应写“生成了一个草稿结果，尚未写入工程”。

本轮后端也增强了兜底模板：如果前端传入 `target_type=general/code/cpp/ue_cpp` 这类泛化值，后端会按 UE C++ 草案处理，尽量返回 `Source/<Class>.h` 和 `Source/<Class>.cpp`，不再轻易返回 `draft.txt`。

如果 UE 前端需要回传测试结果，请说明：

- Code Generate 请求里当前传的 `payload.target_type` 是什么。
- 是否只使用 `user_view.blocks[block_type="generated_items"].data.generated_items` 渲染代码结果。
- 是否把 `write_status=not_written` 作为“未写入工程”的提示，而不是错误状态。

## 25. 2026-04-26 常用 UE 代码知识库补强

后端本轮补充了常用 UE 代码知识和兜底模板。这个改动主要解决 Code Generate 在用户问“角色增强输入代码怎么写”“交互组件怎么写”“射线交互怎么写”“子系统怎么写”时只返回普通 Actor BeginPlay/Tick 空骨架的问题。

后端新增行为：

- local grep 可命中 `knowledge/engine-notes/ue-enhanced-input-character.md`。
- local grep 可命中 `knowledge/code-reference/enhanced-input-character-example.h/.cpp`。
- local grep 可命中 `knowledge/examples/enhanced-input-buildcs-note.md`。
- local grep 可命中 `interaction-component`、`line-trace-interaction`、`game-instance-subsystem`、`dataasset-gameplaytag` 相关知识文件。
- Code Generate 兜底模板能识别中文“角色增强输入”请求。
- 即使 LLM 未配置，也会返回 `ACharacter`、`UInputMappingContext`、`UInputAction`、`UEnhancedInputComponent` 相关草稿。
- 建议路径会采用 `Source/<Module>/Public/<Class>.h` 和 `Source/<Module>/Private/<Class>.cpp`。
- `patch_plan` 会提示添加 `EnhancedInput` Build.cs 依赖，并在编辑器中分配 Input Action / Mapping Context 资产。
- 交互组件请求会返回 `UActorComponent` + overlap 绑定草稿。
- 射线交互请求会返回 `UActorComponent` + `LineTraceSingleByChannel` 草稿。
- 子系统/全局管理器请求会返回 `UGameInstanceSubsystem` 草稿。

前端是否必须修改：

- 主 UI 不需要新增控件。
- 继续按第 24 节把 `generated_items` 渲染成代码草稿按钮 / Tab。
- 如果测试上述常用场景，请确认用户能看到完整 `.h` 和 `.cpp` 内容，而不只是文件名。
- 如果 Debug View 展示引用来源，可显示 `data.reference_lookup.sources` 和 `debug_view.local_search.items`，帮助确认命中了 Enhanced Input 资料。

如果 UE 前端回传测试结果，请说明：

- 本次 Code Generate 的 `payload.target_type` 和 `context.current_module`。
- 是否展示了 `Source/<Module>/Public` / `Private` 建议路径。
- 是否能展开查看包含 `AddMappingContext` / `BindAction` / `LineTraceSingleByChannel` / `UGameInstanceSubsystem` 等关键代码正文。

## 26. 2026-04-26 UE 前端回传状态记录

UE 前端回传的 `frontend-unified-handoff.md` 已确认第 24 节 Code Generate 虚拟草稿展示契约已经落地：

- `generated_items` 已渲染为“代码草稿”按钮 / Tab。
- 点击草稿按钮会预览 `generated_items[].code`。
- `file_path` 已标注为“建议路径”，不再暗示磁盘文件已存在。
- `write_status=not_written` 和 `is_virtual=true` 已作为正常草稿状态处理。
- 用户实测 Code Generate 当前展示链路可用，后端已记录为阶段通过。

当前判断：

- 后端不需要为 Code Generate 虚拟草稿展示再改接口。
- 前端主 UI 暂不需要新增控件。
- 下一次给 UE 前端交接时，重点让前端继续阅读第 25 节，验证常用 UE 场景代码生成是否能完整展示 `.h/.cpp` 正文。

下一次 UE 前端回传建议说明：

- “角色增强输入代码怎么写”是否能看到 `AddMappingContext`、`BindAction`、`Move`、`Look`。
- “交互组件 overlap 怎么写”是否能看到 `UActorComponent` 和 overlap 绑定。
- “射线交互组件怎么写”是否能看到 `LineTraceSingleByChannel`。
- “全局管理器子系统怎么写”是否能看到 `UGameInstanceSubsystem`。

## 27. 2026-04-26 Agent Chat 知识库问答收口

本轮后端修正了 Agent Chat / Project QA 中两个容易误解的知识库行为。

### 知识库目录问题

用户问“知识库有哪些内容”“知识库里有什么”“list knowledge base contents”这类问题时，后端现在不再把它当作普通 RAG 片段检索，也不会把 `.h/.cpp` 源码正文直接塞进回答。

新的返回方式：

- `data.answer_mode = "knowledge_catalog"`
- `data.catalog.document_count`
- `data.catalog.domain_counts`
- `data.catalog.items[]`
- `data.answer_generation.mode = "knowledge_catalog"`
- `debug_view.retrieval.mode = "knowledge_catalog"`

普通用户界面仍然只展示 `assistant_message` / `user_view.text` 即可；Debug View 可选展示 `data.catalog`，用于确认当前索引了哪些 knowledge 文件。

### 中文问题检索英文知识文档

后端现在给本地 lexical RAG / local grep 增加了轻量中英查询扩展。例如：

- “actor的生命周期是什么” 会补充 `lifecycle / constructor / BeginPlay / Tick / EndPlay` 等检索词。
- “增强输入” 会补充 `Enhanced Input / InputMappingContext / InputAction / EnhancedInputComponent` 等检索词。
- “静态网格体 / 碰撞 / 子系统 / 交互组件”等常见 UE 术语也会做轻量扩展。

这不是翻译整篇知识库，也不是替代 embedding；它只是让未接入向量模型时的本地词法检索更稳。前端不需要新增控件。测试时可在 Debug View 观察：

- `data.retrieved_docs[].source_path`
- `data.citations`
- `debug_view.retrieval.retrieved_docs`
- `debug_view.local_search.items[].matched_terms`

## 28. 2026-04-26 Code Review Agent Workflow v1

后端本轮开始执行面试级 Agent 项目增强计划。没有新增主菜单，也没有改变 Code Review 请求方式；只是让现有 Code Review 在原有展示块之后追加“轻量 Agent 工作流”结果。

### 后端新增字段

Code Review 响应现在会继续保持前 6 个稳定块顺序：

```text
summary -> llm_analysis -> issues -> recommendations -> references -> next_steps
```

同时在后面追加：

- `user_view.blocks[block_type="agent_workflow"]`
- `user_view.blocks[block_type="fix_draft"]`
- `user_view.blocks[block_type="validation_plan"]`

对应 `data` 字段：

- `data.agent_workflow`
- `data.fix_draft`
- `data.validation_plan`
- `data.localized_review.agent_workflow`
- `data.localized_review.fix_draft`
- `data.localized_review.validation_plan`

Debug View 中也会增加两个 step/tool：

- `draft_fix_plan`
- `build_validation_plan`

### 字段含义

`agent_workflow` 说明本轮按轻量 Agent 流程执行：

```text
collect code -> rule scan -> knowledge guidance -> LLM explanation -> fix draft -> validation plan
```

`fix_draft` 是非破坏性修复草稿：

- `write_policy.written_to_disk=false`
- `items[].is_virtual=true`
- `items[].write_policy=not_written`
- 只作为建议展示，不代表后端已经改工程文件

`validation_plan` 是验证清单：

- 编译相关模块
- 打开编辑器并运行 PIE 烟测
- 根据规则命中补充 UObject 生命周期、Tick 性能、线程上下文、资产引用、蓝图编译等检查项
- 复查 Output Log，并可把日志继续送到 Logs Analyze

### 前端是否必须修改

当前不强制修改主 UI。因为后端把新增内容放在原有 6 个 Code Review 块之后，旧 UI 如果有通用 block fallback，应该可以直接看到文本。

建议后续前端优化：

- Code Review Highlights 弹窗新增三个可折叠区：`Agent Workflow`、`Fix Draft`、`Validation Plan`。
- `fix_draft` 文案必须表达“建议 / 草稿 / 未写入工程”，不要写成“已修复”。
- `validation_plan` 可以渲染成 checklist，但不要让用户误以为后端已经执行测试。

### 下一次 UE 前端回传建议说明

- 是否能看到新增的三个 block。
- 是否把 `fix_draft.write_policy.written_to_disk=false` 当成正常状态。
- 是否能显示 `validation_plan.items[].title/text/category`。
- Code Review 原有 summary / llm_analysis / issues / recommendations 高亮按钮是否仍正常。

## 29. 2026-04-26 Validation Advisor v1

后端本轮把“验证清单”扩展到更多核心 Skill。它不是新主功能，而是各工具结果里的附加建议层，用来说明用户采纳生成内容或修复建议后，应该怎样在 UE 编辑器里验证。

### 新增响应字段

这些任务现在都会返回：

- `data.validation_plan`
- `user_view.blocks[block_type="validation_plan"]`
- `debug_view.tools[].tool_id == "build_validation_plan"`
- `step_results[].step_id == "build_validation_plan"`

覆盖范围：

- `Code Review`：和第 28 节一致，验证编译、PIE、UObject 生命周期、Tick、线程、资产引用、蓝图编译、日志复查。
- `Code Generate`：验证手动放置草稿、编译模块、Build.cs、Enhanced Input 资产、Trace/Overlap/SubSystem 场景、PIE 烟测。
- `Logs Analyze`：验证完整日志窗口、复现步骤、首个 Error/Fatal、资产路径、相关模块、首个编译错误。
- `Assets Inspect`：验证重命名建议、Fix Up Redirectors、蓝图编译、StaticMesh 设置、Reference Viewer。

### 前端是否必须修改

不强制。后端仍把 `validation_plan` 作为普通 `user_view.blocks` 追加输出；如果旧 UI 有通用 block fallback，可以直接显示。

建议统一优化：

- 在 Code Review / Code Generate / Logs Analyze / Assets Inspect 结果区都把 `validation_plan` 渲染成 checklist。
- 每一项读取 `items[].title`、`items[].text`、`items[].category`、`items[].automation_level`。
- 文案要表达“建议 / 待验证”，不要写成“已执行测试”。

### 下一次 UE 前端回传建议说明

- 哪些面板已经展示了 `validation_plan`。
- 是否把 `automation_level=manual_or_editor` 作为人工/编辑器验证提示。
- 是否仍保持原有核心结果显示不变。

## 30. 2026-04-26 UE 前端回传状态：Workflow / Validation 已对齐

UE 前端回传的 `frontend-unified-handoff.md` 和 `backend-action-items.md` 已同步后端第 25-29 节，并确认当前处理策略：

- 不新增主菜单，不改变 5 个核心入口。
- Code Generate 常用 UE 代码生成仍按 `generated_items` 草稿按钮 / Tab 展示。
- Agent Chat 的 `knowledge_catalog` 暂时通过普通回答和 Debug View Raw Response 查看。
- Code Review 新增 `agent_workflow`、`fix_draft`、`validation_plan` 先走通用 User View block fallback。
- Code Generate / Logs Analyze / Assets Inspect 的 `validation_plan` 也先走通用 block fallback。
- Debug View 可查看 `data.agent_workflow`、`data.fix_draft`、`data.validation_plan`、`step_results`、`debug_view.tools`。

当前后端判断：

- 不需要新增接口字段。
- 不需要后端为前端再改主流程。
- 可以进入联调测试阶段。

建议测试时重点观察：

- Code Review 原有 `summary / llm_analysis / issues / recommendations` 是否仍正常。
- Code Review 是否能看到 `agent_workflow / fix_draft / validation_plan`。
- Code Generate / Logs Analyze / Assets Inspect 是否都能看到 `validation_plan`。
- 前端文案是否保持“建议 / 草稿 / 未写入 / 待验证”，没有误写成“已修复 / 已执行测试”。

## 31. 2026-04-26 Logs Analyze 输入优化契约

本轮后端优化了 Logs Analyze 的输入边界，解决“必须粘贴完整日志文本才能分析”的体验问题。接口仍然是：

```http
POST /api/v1/tasks/logs-analyze
```

前端需要调整：

- 日志分析面板不要再把“粘贴文本”设为唯一必填项。
- 用户可以选择日志文件路径、粘贴几行 Error/Fatal、或两者都提供。
- 推荐 UI 改成三块：`Log Source / File`、`Error Snippet / Pasted Text`、`Notes / Attachments`。
- `Analyze Log` 启用条件改为：至少存在 `log_text/selected_log_text/log_excerpt/error_excerpt/error_lines` 之一，或存在 `log_file_path/log_path/file_path/log_source` 之一。

后端新增兼容字段：

- `payload.log_file_path`：推荐的日志文件绝对路径或项目相对路径。
- `payload.log_path` / `payload.file_path`：兼容字段。
- `payload.selected_log_text` / `payload.log_excerpt` / `payload.error_excerpt` / `payload.error_lines`：短片段输入。
- `payload.notes` / `payload.user_notes`：用户备注。
- `payload.attachment_paths` / `payload.attachments[]`：可选辅助文本附件路径。
- `payload.include_file_context=true`：当已经有粘贴片段但仍希望后端读取文件上下文时使用。

后端读取规则：

- 只分析前端显式传入的文本或路径，不主动扫描 UE 工程日志目录。
- 文件读取保持只读，支持 `.log/.txt/.crashcontext/.xml/.json/.ini`。
- 没有 `line_window` 时默认读取文件尾部窗口，避免一次性塞入超长日志。
- 有 `line_window` 时读取指定行号范围。
- 文本片段优先级高于文件读取，适合用户只想分析几条 Error。

前端可在 Debug View 展示：

- `data.input_context.input_mode`：`pasted_text`、`file_tail`、`file_line_window`、`attachment_text` 或 `empty`。
- `data.input_context.read_diagnostics[]`：文件读取状态、截断状态、读取字节数。
- `data.input_context.attachment_diagnostics[]`：附件读取状态。
- `data.parser_diagnostics.input_collection`：完整输入采集诊断。

回传建议说明：

- 是否支持“只选文件不粘贴文本”后点击 Analyze。
- 是否支持“只粘贴几行 Error/Fatal”后点击 Analyze。
- 是否把 `input_mode/read_diagnostics` 放入 Debug View，而不是普通用户主结果。

## 32. 2026-04-27 Logs Analyze LLM 分析与知识库质量门槛

本轮后端继续优化 Logs Analyze 的解释层，解决“日志分析结果看起来像 LLM、又不像 LLM”的不清晰问题。

### 后端新增行为

- Logs Analyze 现在固定返回 `data.llm_analysis` 和 `user_view.blocks[block_type="llm_analysis"]`。
- LLM 可用时，`llm_analysis.status = "completed"`，`text` 是面向普通用户的综合解释。
- LLM 未配置或请求失败时，`llm_analysis.status = "skipped"`，`reason_code` 会说明原因，例如 `missing_openai_api_key`。
- 规则解析、问题类型和验证清单不会因为 LLM skipped 失败，仍然正常返回。
- Debug View 新增 tool/step：`llm_log_analysis_synthesis`。

### 知识库使用策略

Logs Analyze 仍会尝试检索 `incident_history / engine_notes / project_docs`，但新增质量门槛：

- `data.retrieval_quality_gate.status = "passed"`：知识库命中质量足够，可作为引用和 LLM 辅助上下文。
- `data.retrieval_quality_gate.status = "skipped"`：命中质量低于阈值，后端不会把这些弱命中放进普通用户引用，也不会强行交给 LLM 作为事实。
- 阈值诊断字段：`confidence`、`top_score`、`min_confidence`、`min_top_score`、`candidate_count`。

前端展示建议：

- Logs Analyze 主结果区把 `llm_analysis` 放在 `Log Summary` 后、`Issue Families` 前。
- `llm_analysis.status=skipped` 时显示轻提示，不当作任务失败。
- 普通用户主 UI 只显示通过质量门槛的 citations / references。
- `retrieval_quality_gate` 放 Debug View，不建议作为普通用户强提示。

回传建议说明：

- Logs Analyze 结果里是否能看到“LLM 分析结果”卡片。
- 未配置 LLM 时是否显示 skipped 轻提示，而不是让用户误以为 LLM 已经分析。
- 弱知识库命中是否只在 Debug View 可见，不进入普通用户引用。

## 33. 2026-04-27 面试增强第一阶段：Tool Registry / ReAct Lite / Startup Checks

状态：后端已实现，前端暂不需要强制修改。

### 新增但兼容的字段

- `GET /api/v1/system/capabilities`
  - 新增 `capabilities.tool_registry.mode`
  - 新增 `capabilities.tool_registry.tools[]`
  - 每个 tool card 包含 `tool_id`、`task_type`、`title`、`description`、`side_effect_level`、`route_preference`、`requires_retrieval`、`trigger_keywords`、`required_payload_fields`、`optional_payload_fields`、`timeout_ms`、`input_schema`
- `GET /api/v1/system/health`
  - 新增 `startup_checks`
  - 包含 `status`、`blocking`、`counts`、`checks[]`
- `POST /api/v1/chat/runs` 或 `POST /api/v1/tasks/project-qa`
  - Project QA 响应新增 `data.react_loop`
  - Debug View 新增 `debug_view.react_loop`

### 前端建议

- 现阶段无需新增主 UI。
- Debug View 可以直接展示 `react_loop` 原始 JSON，作为面试演示“Agent 如何选择工具”的证据。
- Health / Settings 面板如已有状态区，可选展示 `startup_checks` warning；没有状态区也可以先不做。
- `tool_registry.tools` 可作为后续动态说明/帮助面板的数据源，但不要用它替代现有按钮逻辑。

### 需要前端回传的信息

- 如果 Debug View 无法展示新增字段，请回传渲染截图或字段丢失位置。
- 如果 Health 面板已有状态展示，请说明是否需要后端进一步压缩 `startup_checks` 文案。
- 如果后续想把工具能力卡做成 UI 帮助面板，请回传期望字段和布局。

### 边界

- ReAct Lite 当前只用于 Agent Chat / Project QA 的可解释轨迹。
- Code Review / Code Generate / Logs Analyze / Assets Inspect 的接口和主 UI 暂不变。
- 后端没有新增写工程文件的自动动作。

## 34. 2026-04-27 Project QA 受控 ReAct 与当前文件读取

状态：后端已实现，前端暂不强制改 UI。

### 后端新增能力

`Agent Chat / Project QA` 现在支持受控 ReAct 工具选择：

- LLM 可用时，后端会让 LLM 在白名单里建议只读工具。
- LLM 不可用、规划失败或返回非法工具时，后端继续走 deterministic fallback。
- 当前允许工具：
  - `retrieve_project_knowledge`
  - `query_project_inventory`
  - `read_project_file`

### 当前文件读取

如果用户在自由聊天中问：

- “当前文件里做了什么”
- “解释这个文件”
- “这个 cpp 里有没有问题”

前端建议继续传：

```json
{
  "context": {
    "project_root": "F:/Epic Games/project/RushBa",
    "current_file": "Source/RushBa/Private/PlayerCharacter.cpp"
  }
}
```

后端会：

- 校验 `current_file` 解析后必须位于 `project_root` 内。
- 只读取文本/code/config 文件。
- 限制读取大小，默认约 40KB，最大 120KB。
- 只读，不写入、不删除、不移动、不执行。

### 新增响应字段

- `data.project_file`
  - `status`: `completed / skipped / blocked / error`
  - `reason`
  - `file_path`
  - `resolved_path`
  - `bytes_read`
  - `truncated`
  - `text_excerpt`
- `data.tool_plan.planner_decision`
- `data.tool_plan.tool_calls[]`
- `data.tool_contracts.input_contracts[]`
- `data.tool_contracts.result_contracts[]`
- `debug_view.project_file`
- `debug_view.tool_contracts`
- `debug_view.react_loop.steps[]`

### 前端展示建议

- 普通聊天 UI 不需要新增卡片，直接显示 `assistant_message` 即可。
- Debug View 建议展示 `react_loop`、`tool_plan`、`project_file`、`tool_contracts`。
- 如果 `project_file.status=blocked`，Debug View 显示 reason，普通用户不需要强提示。

### 需要前端回传的信息

- 当前 Agent Chat 请求是否稳定传 `context.project_root`。
- 用户当前打开文件是否能稳定传 `context.current_file`，且最好是项目相对路径。
- 如果传的是绝对路径，也可以，但后端仍会检查它是否在 `project_root` 内。

### 边界

- 这不是 Code Review 文件扫描功能，只是 Project QA 的只读上下文补充。
- 不会自动分析整个工程文件树。
- 不会替代 Code Review 面板的文件选择和审查流程。

## 35. 2026-04-27 Tool Contract Debug 字段

状态：后端已实现，前端暂不强制修改。

### 新增字段

- `GET /api/v1/system/health`
  - `startup_checks.checks[]` 中新增 `check_id="tool_registry_contracts"`。
- `GET /api/v1/system/capabilities`
  - `capabilities.tool_registry.tools[].output_schema`
- Project QA 响应：
  - `data.tool_contracts.input_contracts[]`
  - `data.tool_contracts.result_contracts[]`
  - `debug_view.tool_contracts`

### 前端建议

- 普通用户 UI 不展示 Tool Contract。
- Debug View 原样展示即可。
- 如果 contract `ok=false`，这代表后端工具契约或工具结果异常，适合放 Debug View，不建议当成普通用户错误弹窗。

### 边界

- 这是后端内部工具契约透明化，不改变现有请求格式。
- 不要求前端根据 schema 动态生成表单。

## 36. 2026-04-27 Self-Reflection Debug 字段

状态：后端已实现，前端暂不强制修改。

### 新增字段

- `data.self_reflection`
- `debug_view.self_reflection`
- `trace_summary.agent_decision_trace.decisions.self_reflection_decision`

### 字段含义

- `status`: `passed / needs_context / degraded`
- `grounding_level`: `project_grounded / general_llm / fallback / insufficient_evidence / low_confidence`
- `evidence_counts`: 知识库、项目快照、当前文件证据数量。
- `checks[]`: 回答是否为空、证据是否足够、置信度是否达标、是否有降级 warning。
- `recommendations[]`: 给 Debug View 的补上下文建议。

### 前端建议

- 普通用户 UI 暂不展示。
- Debug View 原样展示即可。
- 如果后续想做“回答质量徽标”，可以只展示 `status`，但现在不是必须项。

### 边界

- Self-Reflection 不额外调用 LLM。
- 不代表任务失败，只是回答质量诊断。

## 37. 2026-04-27 轻量长期记忆 Debug 字段

状态：后端已实现，前端暂不强制修改。

### 新增行为

当用户在 Agent Chat 中表达项目约定，例如：

```text
请记住：我们的项目 UE 版本是 5.4，所有蓝图命名要加 BP_ 前缀。
```

后端会把这类信息作为项目级长期记忆保存。之后同一 `project_name` 的新 session 可以召回。

### 前端建议继续传

```json
{
  "context": {
    "project_name": "RushBa"
  }
}
```

`project_name` 是跨 session 召回的主要过滤条件。

### 新增 Debug 字段

- `data.context_bundle.long_term_memory`
- `debug_view.memory_summary.long_term_memory`
- `agent_decision_trace.decisions.memory_decision.details.long_term_memory_items`

### 前端展示建议

- 普通用户 UI 暂不需要新增记忆管理面板。
- Debug View 原样展示即可。
- 如果后续做“记忆面板”，建议只展示 `category/text/source_session_id/created_at`。

### 边界

- 后端不做用户画像。
- 后端不做向量记忆或图记忆。
- 清理 session 只清理该 session 自己保存的长期记忆，不影响其他 session。

## 38. 2026-04-27 RAG Eval Markdown Report

状态：后端已实现，前端不需要修改。

### 后端新增内容

- `scripts/run_rag_eval.py` 新增 `--markdown-output`。
- 新增 `docs/rag-eval-report.md`，用于展示当前 RAG smoke eval 结果。
- 报告包含：
  - `hit_at_k`
  - `mrr`
  - `route_accuracy`
  - `citation_coverage`
  - 每条 case 的 matched sources

### 前端影响

- UE 插件 UI 不需要新增接口或字段。
- 这份报告仅用于后端自测、面试展示和复盘。
- 如果后续前端也想在 Debug 面板展示 eval 结果，需要另开“本地评测结果查看”需求；当前阶段不做。

### 当前需要前端回传的信息

- 无。

## 39. 后续可选项：Token 级 SSE 流式输出

状态：后端暂不继续单方面实现，需要 UE 前端先确认消费方式。

### 为什么需要前端配合

当前 `/api/v1/chat/runs/{run_id}/events/stream` 是事件回放，不是 token 实时流。若升级为真正 token 级 SSE，UE 前端需要支持：

- 以 `text/event-stream` 方式读取持续响应。
- 增量拼接 `assistant_delta` / `token` 事件。
- 在工具调用事件出现时显示“正在检索 / 正在读取项目文件 / 正在查询 Inventory”等中间状态。
- 在 `final` 事件到达后，把完整回答落到现有聊天历史。
- 在连接中断、后端报错或用户取消时做兜底显示。

### 建议的前端回传信息

如果后续决定做流式，请 UE 前端先回传：

- 当前 HTTP 客户端是否支持 SSE 持续读取。
- 聊天 UI 是否支持逐 token 更新同一条 assistant 气泡。
- 是否需要保留现在的非流式接口作为 fallback。
- UE 插件侧期望的事件名，例如 `token`、`tool_call`、`tool_result`、`final`、`error`。

### 后端边界

- 只考虑 `Agent Chat / Project QA` 流式。
- Code Review / Code Generate / Logs Analyze / Assets Inspect 继续同步返回。
- 不在本阶段改为全项目 async，也不引入复杂消息队列。

## 40. 2026-04-27 后端已新增可选 SSE 流式入口

状态：后端已实现可选入口，UE 前端暂不强制接入。

### 新增接口

- `POST /api/v1/chat/runs/stream`

请求体沿用 `UnifiedTaskRequest`，建议继续传：

- `task_type="agent_chat"`
- `runtime_options.stream=true`
- `context.project_root`
- `context.project_name`
- `context.current_file`

### SSE 事件名

当前后端会返回以下事件：

- `stream_opened`：SSE 连接已打开，包含 fallback endpoint。
- `run_started`：后端已创建 `task_id/run_id/trace_id` 并开始执行。
- `tool_call`：Project QA 调用只读工具前触发，例如 `retrieve_project_knowledge`、`query_project_inventory`、`read_project_file`。
- `tool_result`：只读工具执行完成后的摘要。
- `assistant_delta`：最终 LLM 回答的文本增量。
- `final`：完整 `UnifiedTaskResponse`，可用于落库聊天气泡、恢复历史和 Debug View。
- `error`：流式执行失败。
- `heartbeat`：长时间无事件时的保活事件。

### 前端接入建议

- 当前 UE 插件可以继续使用非流式 `POST /api/v1/chat/runs`，不影响已有功能。
- 如果开始接入流式，请只在 Agent Chat / Project QA 做，不要改 Code Review / Code Generate / Logs Analyze / Assets Inspect。
- 前端应把 `assistant_delta.payload.text` 追加到同一个 assistant 气泡。
- 前端收到 `final.payload.response` 后，用完整响应替换或校准临时气泡，并继续按现有 User View / Debug View 渲染。
- 如果 SSE 失败，前端应回退到 `POST /api/v1/chat/runs`。

### 后端边界

- `GET /api/v1/chat/runs/{run_id}/events/stream` 仍然是历史事件回放，不改语义。
- `POST /api/v1/chat/runs/stream` 是新入口，不破坏旧接口。
- LLM 未配置时不会伪造 token，但仍会发送 `final`。
- 当前只对最终 LLM 回答阶段推送 token；检索和工具阶段以结构化事件说明进度。

### 需要 UE 前端后续回传

- 是否能稳定消费 `text/event-stream`。
- 是否能逐 token 更新同一条 assistant 气泡。
- 断线后是否能自动回退非流式。
- `tool_call/tool_result` 是否需要专门的“正在检索 / 正在读取文件”状态条。

## 41. 2026-04-30 UE C++ 蒸馏知识包与 Code Generate 增强

状态：后端已完成，UE 前端暂不需要强制修改。

### 后端新增内容

- 新增 UE C++ 蒸馏知识包，位置在 `knowledge/engine-notes`、`knowledge/examples`、`knowledge/code-reference`、`knowledge/team-rules`、`knowledge/prompt-packs`。
- 新增 `prompt_packs` 知识 domain，用于标记 LLM 行为指导类文档。
- 新增中文查询扩展词，让中文问题也能命中英文 UE 术语，例如 HTTP、WebSocket、GAS、反射、容器、委托、网络同步。
- `Code Generate` 新增 HTTP AsyncAction、WebSocket Subsystem、DeveloperSettings、GAS AttributeSet 兜底模板。

### 前端影响

- 现有接口不变。
- 现有 `Code Generate` 面板继续读取 `data.generated_items`、`data.reference_lookup`、`data.retrieved_references` 即可。
- 如果用户问“HTTP 请求怎么写 / WebSocket 长连接怎么写 / 项目设置配置怎么写 / GAS 技能系统属性集怎么写”，后端现在会返回更具体的 UE C++ 草稿，而不是普通 Actor 骨架。
- 新增 `prompt_packs` domain 只可能出现在知识库状态、citations、Debug View 或 reference lookup 中；前端不需要新增菜单或面板。

### 建议前端显示

- Code Generate 结果仍然以按钮 / Tab / 文件列表展示 `generated_items[]`。
- 对 `write_policy.written_to_disk=false` 继续显示“草稿 / 未写入工程”语义。
- 如果引用来源包含 `prompt_packs`，可以在 Debug View 中按普通 source 显示；普通用户 UI 可以不用突出展示。

### 需要前端回传的信息

- 暂无强制回传。
- 如果测试中发现某类新增生成结果没有展示出来，请回传该次响应里的 `data.generated_items`、`data.generation_mode`、`data.reference_lookup` 和 Debug View。

## 42. 2026-04-30 Agent Chat UE 技术知识路由修正

状态：后端已完成，UE 前端不需要改 UI 或接口。

### 背景

用户在 Agent Chat 中问 “GAS / 多线程 / HTTP / 反射”等 UE 技术问题时，之前容易走 `direct_answer`，表现得像 LLM 自己回答，没有使用本地知识库。

### 后端调整

- 新增 UE 技术知识路由信号。
- Agent Chat 命中 UE 技术问题时会进入 `project_qa`。
- `debug_view.route.selected_tool_id` 会显示 `retrieve_project_knowledge`。
- `debug_view.route.decision_source` 会显示 `heuristic_ue_knowledge_signal`。
- 项目事实问题不受影响，例如“当前项目有哪些蓝图资产”仍走 `query_project_inventory`。

### 前端影响

- 继续使用现有 `POST /api/v1/chat/runs`。
- 聊天气泡和 citations 渲染逻辑不变。
- Debug View 如果展示 route/source/tool，可能会看到新的 `decision_source=heuristic_ue_knowledge_signal`。

### 建议测试问题

- “GAS技能系统是什么”
- “UE多线程怎么做”
- “HTTP请求怎么写”
- “反射宏怎么选”
- “当前项目有哪些蓝图资产，你列一下”

### 需要前端回传的信息

- 如果上述 UE 技术问题仍显示成纯 `direct_answer`，请回传完整响应的 `debug_view.route`、`data.retrieved_docs`、`data.citations`。
- 如果 citations 有内容但用户界面没有显示参考来源，请回传前端渲染截图和对应 JSON。

## 43. 2026-04-30 本地私有全量知识源接入

状态：后端已完成，UE 前端不需要改 UI 或接口。

### 后端能力

后端现在明确支持双轨知识库：

- 公开仓库内置：`./knowledge`，只放本项目原创蒸馏知识。
- 本地私有扩展：用户可在 `.env` 的 `KB_SOURCE_PATHS` 中追加合法拥有的外部资料路径。

示例：

```env
KB_SOURCE_PATHS=./knowledge,../XG-UE-Cpp-Course-Skill-main/knowledge,../XG-UE-Cpp-Course-Skill-main/.trae/skills/xg-uecpp-course/references
```

新增扫描脚本：

```powershell
.\.venv\Scripts\python.exe scripts\scan_knowledge_sources.py --markdown-output storage\artifacts\private-kb-scan.md
```

该脚本只统计文件数、domain、后缀、缺失路径，不复制私有知识正文。

### 前端影响

- 无需新增字段。
- 继续使用现有知识库刷新、Agent Chat、Code Generate、Code Review 响应。
- 如果用户本地接入了私有全量库，前端只会看到更多 citations / references / retrieved docs。

### 建议前端测试

- 接入私有路径后，调用知识库刷新。
- 在 Agent Chat 问 “GAS 体系怎么组织”“FRunnable 多线程怎么写”“Slate 独立程序是什么”。
- 在 Code Generate 问 “HTTP POST JSON 请求怎么写”“WebSocket 长连接怎么写”。
- 查看 citations 是否出现私有路径来源。

### 需要前端回传的信息

- 如果刷新后仍看不到私有资料，请回传 `GET /api/v1/knowledge-base/status` 的 `source_paths`、`rag_readiness`、`local_search_readiness`。
- 如果前端不希望显示私有绝对路径，需要另开“citation 路径脱敏/相对化”需求；当前后端仍按现有 source path 返回。
