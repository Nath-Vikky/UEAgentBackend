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

- 日志预览区
- `Analyze Log` 按钮
- 结构化结果区
- 可选“发送到聊天”继续追问

建议 payload：

```json
{
  "log_text": "...",
  "log_source": "Saved/Logs/MyProject.log",
  "time_range": {"start": "...", "end": "..."},
  "line_window": {"start": 120, "end": 220}
}
```

前端应重点消费 `user_view.blocks` 中的这些结构：

- `Log Summary`
- `Issue Families`
- `Suggested Actions`
- `Captured Log Window`
- `Affected Modules / Resources`

日志采集仍属于插件职责，后端只分析文本。

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
summary -> issues -> recommendations -> references -> next_steps
```

即使项目知识库没有命中足够证据，后端也会基于当前文件内容和通用 Unreal/C++/C# 规则返回可参考结果，并在 `references` 块中说明 fallback 来源。

前端可优先读取：
- `user_view.blocks`
- `data.localized_review.issues`
- `data.localized_review.recommendations`
- `data.localized_review.references`
- `data.localized_review.next_steps`
- `data.llm_review`

`data.llm_review.ok = true` 表示后端已用配置的 LLM 做过综合审查；`false` 时仍有确定性规则扫描结果可展示。常见跳过原因包括 `missing_openai_api_key`、`json_parse_failed`、`file_read_failed_or_empty_source`。

### Code Review 读取失败

如果 `data.review_scope.read_status = "error"` 或存在 `data.review_scope.load_error`，前端应把结果作为文件读取失败处理。此时 `user_view.status_hint = "read_error"`，`issues` 块会显示具体错误，不应把它当成正常审查结论。

### Assets Inspect 中文 Highlight

Assets Inspect 的 Highlight / `issues` block 中，`reason` 和 `suggestion` 已按最终输出语言本地化。中文工作流下选择 `NewMap` / `World` 时，前端应能直接显示中文原因与中文改名建议，例如说明默认占位命名风险，并保留 `L_` / `Map_` 前缀原文。
