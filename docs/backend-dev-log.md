# Backend Dev Log

## 2026-04-20 Contraction Pass

这一轮不再继续横向扩功能，开始把项目收回到 5 个核心功能：

- `Agent Chat / Project QA`
- `Code Review`
- `Code Generate`
- `Logs Analyze`
- `Assets Inspect`

### 主要代码改动

- 收缩 `system/capabilities`
- 新增 `deferred_task_types`
- 新增 `feature_catalog`
- 新增更明确的 `ui_recommendations`
- 为代码审查补了 `POST /api/v1/tasks/code-review/files`
- 支持按 `project_root + file_path` 读取选中文件
- 知识库支持导入代码文件并归类为 `code_reference`
- `code_generate` 先检索代码参考，再返回 `generated_items`
- 资产检查支持 `asset_items`、`asset_type`、`dependencies`、`referencers`
- 日志分析支持 `log_source`、`time_range`、`line_window`
- 延后功能仍保留兼容路由，但不再作为主线暴露给前端

## 2026-04-20 Finalization Pass

这一轮继续做的是“产品化收边”而不是继续加功能。

### 主要代码改动

- 清理掉旧的 `code_generate` 重复执行路径，只保留新的参考增强版实现
- `logs_analyze` 的 `user_view` 收成更适合专用面板的数据结构
- `assets_inspect` 的 `user_view` 收成更适合专用面板的数据结构
- 统一重写文档入口：`README.md`、`docs/backend-user-guide.md`、`docs/frontend-unified-handoff.md`

## 2026-04-21 Encoding And Handoff Cleanup

这一轮修复了上一轮收口时由 PowerShell 写入造成的中文问号占位符编码问题。

### 主要代码改动

- 恢复 `logs_analyze` 的中文 `user_view` 文案
- 恢复 `assets_inspect` 的中文 `user_view` 文案
- 保留英文标题不变，确保前端测试和 UI 映射稳定

### 主要文档改动

- 恢复 `README.md` 中文内容
- 恢复 `backend-user-guide.md` 中文内容
- 恢复 `frontend-unified-handoff.md` 中文内容
- 更新 `backend-dev-log.md` 记录编码修复

### 当前真实判断

- 平台层：已完成
- 5 个核心功能主链路：已完成当前收口版验证
- 前端现在可以按统一交接文档集中改 UI

### 保留的非阻塞边界

- `events/stream` 仍然是事件回放，不是 token 实时流
- `code_generate` 不直接写用户工程，也不做编译验证
- `LangSmith / OTel` 仍是本地契约与元数据层，不是远端生产链路

## 2026-04-21 UE 联调反馈修复

这一轮根据 UEAgentTool 返回的 `backend-action-items.md` 和 `frontend-unified-handoff.md` 做了对齐修复，目标是把前端当前遇到的阻塞点补齐，而不是继续扩功能。

### 主要代码改动

- 修复 `LLMService.classify_agent_chat()`：LLM 路由复核成功时现在会解析 JSON 并稳定返回 `{ok, route_type, confidence, reason, error, provider, model, profile_id, usage}`。
- 清理 `complete_json_object()` 中不可达的路由解析逻辑，避免同一段职责散落在两个方法里。
- 加固 `TaskService._apply_llm_route_decision()`：当 LLM 返回非法 JSON、空文本、失败结果或 `None` 时，统一记录 `llm_route_decision.status = "skipped"`，沿用原始路由，不再触发 500。
- 补齐 `POST /api/v1/tasks/code-review/files`：返回 `file_path`、`label`、`module_name`、`file_type`，支持 Windows 路径、空格路径、`Source/Plugins` 扫描和按模块名搜索。
- 新增 `scan_diagnostics`：当文件列表为空时返回 `source_roots_not_found`、`query_filtered_empty`、`no_matching_code_extensions` 等原因，方便前端 Debug View 展示。
- 代码审查读取文件时补充 `resolved_absolute_path`、`read_status`、`content_length`、`applied_focus`、`source_roots`，读文件失败会返回明确错误，不让空内容审查伪装成功。
- 资产检查支持 `asset_items[].asset_name`，并稳定识别 `NewMap`、`Untitled`、`NewBlueprint`、`NewMaterial`、`NewTexture`、`NewDataAsset` 等默认/占位命名。
- `Assets Inspect` 对 `World` 类型资产增加 `L_` / `Map_` 命名前缀建议，`user_view.blocks` 中的问题项包含 `severity`、`reason`、`suggestion`。
- 收敛常用 `user_view.blocks[].block_type` 到 `summary`、`issues`、`recommendations`、`references` 等前端更容易稳定渲染的类型。

### 测试补充

- 补充 LLM 路由成功 JSON、非法 JSON、LLM 失败的单元测试。
- 补充 `/api/v1/chat/runs` 在路由复核失败和返回 `None` 时不 500 的集成测试。
- 补充 Code Review 文件扫描对插件路径、空格路径、模块名搜索和读文件调试字段的集成测试。
- 补充 Assets Inspect 对 `NewMap` / `World` 默认命名的集成测试。

## 2026-04-21 UE 二次反馈优化

UE 端二次反馈集中在两个体验问题：中文工作流下 `user_view` 仍会混入英文自然语言，以及 Code Review 在 KB 不足时输出偏薄。

### 主要代码改动

- Code Review 的用户可见结果固定输出五类块：`summary`、`issues`、`recommendations`、`references`、`next_steps`。
- 当知识库没有命中足够证据时，Code Review 会明确提示“基于当前文件内容和通用 Unreal/C++/C# 规则，仅供参考”，不再只给一两句泛化总结。
- Code Review 增加 `localized_review` 数据，供前端直接读取本地化后的 issue / recommendation / reference / next_step。
- Code Review 在 LLM 可用时会尝试 `llm_code_review_synthesis`，把文件片段、规则扫描结果和检索证据交给 LLM 做综合审查；LLM 不可用时稳定降级到确定性规则扫描。
- Assets Inspect 的 `user_view.blocks[].data.items[].reason/suggestion` 现在会按最终输出语言本地化；原始 `data.violations` 保留稳定英文规则字段，方便 Debug View 和测试。
- `NewMap` / `World` 这类默认地图名在中文工作流下会返回中文原因和中文改名建议，同时保留 `L_` / `Map_` 这类代码/资产前缀原文。

### 验证

- 受影响集成测试通过：Code Review 文件选择审查、Assets Inspect `NewMap`。
- `ruff check app tests --no-cache` 通过。

## 2026-04-22 Skill Registry 与 Knowledge Ingestion 优化

这一轮把前面确定的架构方向落到代码里：后端采用固定内置 Skill，不做运行时动态 Skill 插件；知识库导入链路统一暴露能力状态，方便后续前端做知识库管理面板。

### 主要代码改动

- 新增 `app/skills/registry.py`，集中描述 5 个固定内置 Skill：`ProjectQASkill`、`CodeReviewSkill`、`CodeGenerateSkill`、`LogsAnalyzeSkill`、`AssetsInspectSkill`。
- `system/capabilities` 新增 `skill_catalog`、`core_skill_ids`、`skill_architecture`，前端可以从这里读取菜单、UI 模式和 Skill 内部边界说明。
- `feature_catalog` 和 `ui_recommendations` 改为从 Skill registry 派生，避免能力清单分散在多个文件里。
- 修复 `TASK_TYPE_TO_TOOL_ID` 由字典推导覆盖主工具的问题，`logs_analyze` 现在稳定指向 `analyze_ue_log`，`config_generate` 稳定指向 `generate_design_config`。
- `code_generate` 的工具描述改为 `requires_retrieval=True`，与“先查代码知识库，再生成”的当前功能边界一致。
- 新增 `app/rag/ingestion/capabilities.py`，统一声明文本、代码、HTML、PDF、DOCX 的支持范围，以及 `docling` / `unstructured` 解析依赖状态。
- `GET /api/v1/knowledge-base/status` 新增 `ingestion_pipeline`、`format_groups`、`first_class_formats`、`enhanced_formats`、`parser_dependencies`、`knowledge_domains`。
- `POST /api/v1/knowledge-base/import` 的 `source_type=text` 现在同时支持 `text` 和 `content` 字段，并会保存 `doc_type`、`tags`、`metadata`。
- 新增知识库任务别名接口：`GET /api/v1/knowledge-base/jobs/{job_id}` 和 `POST /api/v1/knowledge-base/jobs/{job_id}/retry`，保留旧的 `import-jobs` 路径兼容。
- 新增 Skill runtime descriptor，每次任务响应都会在 `debug_view.skill`、`data.skill`、`trace_summary.skill_id` 标记当前固定 Skill、collector、rules、retrieval domains 和本次检索状态。

### 文档更新

- `frontend-unified-handoff.md` 补充 `skill_catalog`、`skill_architecture`、知识库管理接口和 inline text 导入字段说明。
- `backend-user-guide.md` 已记录知识库、向量模型、Qdrant、LangSmith stub、RAG fallback 的使用方式。
- `frontend-unified-handoff.md` 和 `backend-user-guide.md` 已补充 `debug_view.skill` 的消费方式。

### 验证

- `ruff check` 针对本轮受影响文件通过。
- 关键集成测试通过：capabilities、KB refresh/status、inline content/metadata 导入、KB job alias/retry、direct chat skill runtime、project QA skill runtime、Code Review skill runtime。

## 2026-04-22 CodeReviewSkill Executor 抽离

这一轮开始把固定 Skill 从“描述层”推进到“执行层”。先选择 Code Review，因为它的边界最清晰：UE 文件 collector、规则扫描、知识库参考、LLM 综合审查、结构化投影。

### 主要代码改动

- 新增 `app/skills/executors/code_review.py`，提供 `CodeReviewSkillExecutor`。
- `TaskService._execute_code_review()` 现在只负责创建 executor 并传入依赖，不再直接编排 Code Review workflow。
- Code Review 的输出契约保持不变：`user_view.blocks` 仍固定为 `summary/issues/recommendations/references/next_steps`，`data.review_scope`、`data.localized_review`、`debug_view.skill` 继续保留。
- Code Review 的本地化 helper、推荐项生成、证据说明、下一步建议和 LLM 综合审查 prompt 已搬入 executor。
- `TaskService` 对 Code Review 基本只保留 executor 创建和任务生命周期调度。

### 验证

- `ruff check app/skills app/services/task_service.py --no-cache` 通过。
- Code Review 文件列表与选中文件审查集成测试通过。

## 2026-04-22 CodeGenerateSkill Executor 抽离

这一轮按 Code Review 的模式继续抽离 Code Generate。由于代码生成主逻辑已经在 `CodeGenerationService` 中，executor 主要负责把 service 输出投影成统一响应结构。

### 主要代码改动

- 新增 `app/skills/executors/code_generate.py`，提供 `CodeGenerateSkillExecutor`。
- `TaskService._execute_code_generate_v2()` 现在只创建 executor 并调用，不再直接组装 Code Generate 的 `user_view` 和 `debug_view`。
- Code Generate 原有响应契约保持不变：`data.generated_items`、`data.reference_lookup`、`data.generation_mode`、`data.retrieved_references` 继续保留。
- `debug_view.skill.skill_id` 和 `trace_summary.skill_id` 会稳定显示 `CodeGenerateSkill`。

### 验证

- `ruff check app/skills app/services/task_service.py tests/integration/test_system_and_tasks.py --no-cache` 通过。
- Code Generate 直接生成和代码知识库参考增强生成集成测试通过。

## 2026-04-22 LogsAnalyzeSkill 与 AssetsInspectSkill Executor 抽离

这一轮继续把剩余两个工具型核心 Skill 从 `TaskService` 中抽离出来，让 `TaskService` 更接近任务生命周期调度器。

### 主要代码改动

- 新增 `app/skills/executors/logs_analyze.py`，提供 `LogsAnalyzeSkillExecutor`。
- 新增 `app/skills/executors/assets_inspect.py`，提供 `AssetsInspectSkillExecutor`。
- `TaskService._execute_logs_analyze()` 和 `TaskService._execute_assets_inspect()` 现在只创建 executor 并传入依赖。
- Logs Analyze 原有响应契约保持不变：`data.findings`、`data.structured_events`、`data.parser_diagnostics`、`user_view.blocks` 继续保留。
- Assets Inspect 原有响应契约保持不变：`data.violations`、`data.rename_suggestions`、`data.type_insights`、`data.relationship_summary`、`data.localized_asset_view` 继续保留。
- 集成测试补充 `debug_view.skill.skill_id` 和 `trace_summary.skill_id` 断言，确认前端 Debug View 可以稳定识别当前 Skill。

### 验证

- `ruff check app/skills/executors app/services/task_service.py tests/integration/test_system_and_tasks.py --no-cache` 通过。
- Logs Analyze 和 Assets Inspect 相关集成测试通过。

## 2026-04-23 前端交接契约复核

UE 前端回传的 `backend-action-items.md` 和 `frontend-unified-handoff.md` 与后端主体契约基本一致。本轮只发现一个小偏差：Code Generate 的用户视图第二个块仍使用通用 `list` 类型，而交接文档已把 `generated_items` 列为稳定块类型。

### 主要代码改动

- `CodeGenerateSkillExecutor` 的生成结果块从 `block_type="list"` 调整为 `block_type="generated_items"`。
- 集成测试补充 Code Generate 的 `user_view.blocks` 顺序断言：`summary -> generated_items`。

### 验证目标

- 前端可以按 `generated_items` 专门渲染代码结果按钮、Tab 或列表。
- `data.generated_items`、`data.reference_lookup`、`data.generation_mode`、`data.retrieved_references` 不变。

## 2026-04-23 LLM Analysis 用户可见块

这一轮开始改善工具型 Skill 的“人味”：保留确定性规则结果，同时把 LLM 综合解释显式投影到用户界面。

### 主要代码改动

- Code Review 新增 `llm_analysis` 用户视图块，顺序为 `summary -> llm_analysis -> issues -> recommendations -> references -> next_steps`。
- Code Review 复用已有 `data.llm_review`，将 LLM 摘要、关键点、优先级和 skipped 原因投影为 `data.llm_analysis`。
- Assets Inspect 新增 LLM 综合解释调用，基于资产规则结果、类型摘要、依赖关系和知识库参考生成自然语言分析。
- Assets Inspect 新增 `data.llm_analysis` 和 `data.llm_analysis_raw`，LLM 未配置时返回 `status=skipped`，不影响原有规则结果。
- `TaskService` 向 `AssetsInspectSkillExecutor` 传入 `llm_service` 和 `chat_config`。

### 前端影响

- Code Review 和 Assets Inspect 建议新增“LLM 分析结果”卡片。
- `status=skipped` 不是失败，只表示当前未配置 LLM 或本次未尝试 LLM。
- 原有 `issues`、`recommendations`、`references`、`next_steps` 读取方式保持不变。

## 2026-04-23 Project Inventory 最小闭环

这一轮补了项目快照后端能力，为后续 Agent Chat / Project QA 回答项目事实问题做准备。

### 主要代码改动

- 新增 `ProjectInventoryService`，使用 `storage/project_inventory.json` 保存最新项目快照。
- 新增 `POST /api/v1/project-inventory/snapshot`，接收 UE 插件提交的资产和代码文件摘要。
- 新增 `GET /api/v1/project-inventory/summary`、`/assets`、`/assets/{asset_id}`、`/code-files`、`POST /query`。
- 支持按资产类型、名称、路径、设置、属性、模块名查询。
- Query 能识别 StaticMesh / Nanite / Blueprint / Material / Texture / World / Niagara / Sound / DataTable 等常见 UE 关键词。
- 集成测试覆盖 StaticMesh Nanite 设置、Blueprint 属性、C++ 文件索引和自然语言 query。

### 边界

- 后端不直接解析 `.uasset`，只消费 UE 插件提交的 Asset Registry / Editor API 元数据。
- Project Inventory 已经最小接入 Agent Chat / Project QA，命中结果会进入 `data.inventory` 和 `debug_view.inventory`。
- LLM 不可用时，Project QA 可以基于 Inventory 命中项返回基础项目事实回答。

## 2026-04-23 UE 前端二次回传契约补齐

UE 前端已经接入 Debug View 的 Project Inventory 提交按钮，并回传了需要稳定化的字段。后端本轮保持主流程不变，只补齐快照响应结构、时间字段别名和 LLM 跳过原因展示。

### 主要代码改动

- `ProjectInventorySnapshotRequest` 明确支持 `snapshot_time` 和 `scan_diagnostics`。
- `ProjectInventoryService.save_snapshot()` 返回 `status="saved"`、`summary.asset_count`、`summary.code_file_count`、类型统计和扫描诊断。
- `ProjectInventoryService.summary()` 返回 `scan_diagnostics`，方便 Debug View 展示 UE 侧采集状态。
- `code_files[].last_modified` 与 `modified_at` 双向兼容，后端返回时两个字段都会保留。
- Code Review 与 Assets Inspect 的 `data.llm_analysis` 新增 `reason_code`，`reason` 改为本地化用户可读说明。

### 前端影响

- Project Inventory 提交成功后可优先读 `snapshot.status` 和 `snapshot.summary`，不用从顶层 count 自己拼状态。
- `llm_analysis.status=skipped` 时前端展示 `reason` 作为轻提示，Debug View 展示 `reason_code`。
- 原有 `data.inventory`、`debug_view.inventory`、`data.llm_review.reason` 继续保留兼容。

## 2026-04-24 会话恢复 / Agent Chat Inventory 工具选择 / LLM 稳定性

这一轮集中处理三个真实使用问题：聊天历史恢复后顺序错乱、自由聊天里的项目资产问题被误路由到 Assets Inspect、Code Review 的 LLM 综合分析容易因为超时而跳过。

### 主要代码改动

- `append_messages()` 改为按历史增量写入，不再把前端传来的整段 `session.messages` 每次都重复入库。
- 会话消息恢复现在稳定按 `created_at + message_id` 排序；`TaskService.create_task()` 会把每次 `assistant_message` 也持久化进 session history。
- 新增会话恢复回归测试，验证“第一次聊天 -> 从后端恢复历史 -> 第二次继续聊天”后历史顺序为 `user -> assistant -> user -> assistant`。
- 新增 `query_project_inventory` 只读工具注册，任务类型归属 `project_qa`。
- Agent Chat 路由器会识别“当前项目有哪些蓝图资产”“项目里哪些资产开了 Nanite”等项目事实问题，选择 `query_project_inventory`，不再误选 `inspect_asset_metadata`。
- Project QA 执行层新增 `tool_plan`，纯项目事实查询可以跳过知识库检索，直接查询 Project Inventory；带解释/规范/风险的问题再组合 KB/RAG。
- Code Review 与 Assets Inspect 的在线 LLM 综合分析改为使用更紧凑的 prompt，缩短输入摘要，并为这两类请求单独放宽 timeout、收紧 `max_tokens`。
- `LLMService` 改为使用分离的 `httpx.Timeout` 配置，减少读超时导致的 `request_failed`。

### 当前效果

- Session History 现在以后端 `/sessions/{session_id}/history` 为准，恢复后不会再只看到连续的 user 消息。
- Agent Chat 中的项目级资产/代码盘点问题现在会进入 `project_qa`，并在 `debug_view.route.selected_tool_id` 标记为 `query_project_inventory`。
- Assets Inspect 继续只负责选中资产检查，不承担项目级资产盘点。
- Code Review / Assets Inspect 仍保留 `status=skipped` 的稳定降级，但在已配置 LLM 的情况下，实际命中 `request_failed` 的概率应该会明显下降。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- `python -m pytest tests/integration/test_system_and_tasks.py -q` 通过，`37 passed`。

## 2026-04-24 二次排查：Inventory 空结果与 Code Review LLM 兜底

用户继续联调后发现两个真实问题：Agent Chat 询问“我当前项目的蓝图资产有哪些，你列一下”时可能空回复或只返回“知识库没找到”，Code Review 的 LLM 分析仍容易显示 skipped。后端本轮重点补强可诊断性和稳定兜底。

### 主要代码改动

- `ProjectInventoryService.query()` 调整查询顺序：项目资产列表类问题先按资产类型/代码文件列表查询，再按完整 query 和 query terms 做精确匹配，避免中文整句 query 导致空命中。
- Project Inventory 空结果新增 `summary.empty_reason`，当前支持 `no_project_inventory_snapshot` 和 `no_matching_inventory_items`。
- 明确 `project_id/project_name` 时不再偷用其他项目的 latest snapshot，避免多项目测试串数据。
- `TaskService._execute_project_qa_live()` 在选择了 Inventory 但没有命中时也会生成明确自然语言回答，不再返回空 `assistant_message`。
- `classify_request()` 对显式 `project_qa` 也会识别项目级 Inventory 问题，并选择 `query_project_inventory`。
- `LLMService.complete_json_object()` 在 JSON 解析失败时保留原始 `text`，供上层做文本兜底。
- Code Review / Assets Inspect 在 LLM 返回文本但不是 JSON 时，会转为 `completed_text_fallback`，把文本放进 `llm_analysis.text`，不再直接 skipped。
- Code Review 若请求没有提供可解析的选中文件内容，会返回 `llm_analysis.reason_code = "missing_selected_code_content"`，帮助判断是前端 payload 不足还是 LLM 问题。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- `python -m pytest tests/unit/test_router.py tests/unit/test_llm_service.py -q` 通过，`6 passed`。
- `python -m pytest tests/integration/test_system_and_tasks.py -q` 通过，`41 passed`。

## 2026-04-24 Code Review 高亮展示字段收口

UE 端反馈 Code Review 高亮按钮原本展示 LLM 回答、建议和概要，现在变成完整 JSON。后端判断这是展示契约边界不够硬：Debug/raw 字段可以保留 JSON，但用户展示字段必须保持自然语言。

### 主要代码改动

- Code Review LLM payload 新增展示层归一化：`summary/issues/recommendations/next_steps` 即使出现嵌套 dict/list，也会提取为用户可读字符串。
- `completed_text_fallback` 遇到 JSON-like 原始文本时会尝试解析并提取概要、问题和建议；解析不可靠时不再把整段 JSON 暴露给 `llm_analysis.text`。
- `data.llm_review.text` 继续保留原始 LLM 文本，仅用于 Debug View。
- `user_view.blocks[block_type="llm_analysis"].text` 和 `data.llm_analysis.text` 继续作为前端高亮按钮的首选字段。

### 前端影响

- 不需要改接口和 payload。
- 如果高亮按钮仍显示完整 JSON，说明前端消费了 `data.llm_review`、`debug_view.raw_result`、artifact 或 `analysis_input.source_excerpt` 这类 Debug/raw 字段；应切回 `user_view.blocks[].text` 或 `data.localized_review`。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- 新增 Code Review JSON-like LLM fallback 集成测试，确认高亮展示字段不再以 `{` 开头，也不包含原始 `overview` key。

## 2026-04-24 输出语言偏好统一

本轮开始支持 UE 前端的 `中文 / English` 切换按钮，默认中文。核心目标是让 Agent Chat、Project QA 和工具型 Skill 的用户可见文本不再因为用户输入语言而漂移。

### 主要代码改动

- 新增 `app/i18n/language.py`，统一处理语言检测、`zh-CN/en-US/auto` 标准化和消息内语言覆盖识别。
- `classify_request()` 的语言优先级调整为：消息内显式覆盖、`runtime_options.preferred_output_language`、session 偏好、编辑器 locale、默认 `zh-CN`。
- `auto` 不再跟随用户输入语言；英文问题如果没有前端按钮或 session 指定英文，也会默认输出中文。
- `LocaleDescriptor.language_source` 新增 `message_override` 和 `editor_locale`，便于 Debug View 判断语言来源。
- session 持久化只记录稳定语言偏好；消息里的“用英文回答/用中文回答”是单轮覆盖，不改写 session 偏好。
- `SessionService` 的默认语言展示从 `auto` 改为 `zh-CN`。
- 根据 UE 前端 2026-04-25 handoff 复核，工具型任务不再写入 Agent Chat session history，只保留在 task 列表、Debug View 和 Trace 中。

### 前端影响

- 需要新增语言切换按钮，默认 `zh-CN`，英文时传 `en-US`。
- 每次任务请求都建议带 `runtime_options.preferred_output_language`。
- 启动或恢复 session 时可通过 `POST /api/v1/sessions` 同步 `preferred_output_language`。

### 验证

- `python -m pytest tests/unit/test_router.py -q` 通过。
- `python -m pytest tests/integration/test_system_and_tasks.py::test_logs_analyze_workflow_returns_structured_events tests/integration/test_system_and_tasks.py::test_assets_inspect_can_summarize_types_and_relationships -q` 通过。
- `python -m pytest tests/unit/test_router.py tests/integration/test_system_and_tasks.py -q` 通过，`51 passed`。
