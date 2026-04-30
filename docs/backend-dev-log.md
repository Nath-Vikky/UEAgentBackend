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

## 2026-04-25 Context Manager v1

本轮开始执行后续优化路线中的阶段 A：统一上下文管理。目标是让 Agent Chat、Project QA 和工具型 Skill 不再各自拼上下文，而是先生成一份可解释、可裁剪、可调试的 compact context。

### 主要代码改动

- 新增 `app/agent/context_manager.py`，生成 `context_bundle_v1`。
- `TaskService.create_task()` 在路由后统一构造 `context_bundle`，并传给 `direct_answer`、`project_qa`、`CodeReviewSkill` 和 `CodeGenerateSkill`。
- `direct_answer` 和 `project_qa` 的 LLM prompt 现在会读取 compact context bundle，而不是只依赖请求里的当前消息。
- `DebugView` schema 新增 `context_bundle` 字段，避免响应投影时丢弃上下文调试信息。
- `debug_view.memory_summary.context_budget` 记录本轮上下文预算摘要，方便后续阶段 B 做真正的 Memory Summary / 上下文压缩。
- 工具型任务继续不写入 Agent Chat session history，但最近工具任务摘要会进入 `context_bundle.tool_context`，方便后续自由聊天引用“刚才做过什么工具任务”。

### 前端影响

- 主 UI 暂不需要修改。
- 如果 UE 前端要增强 Debug View，可新增 `Context Bundle` 分区读取 `debug_view.context_bundle` 和 `debug_view.memory_summary.context_budget`。
- 前端回传文档时建议说明是否展示了 `recent_messages`、`tool_context` 和 `budget.warnings`。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- 重点集成测试通过：工具任务不污染聊天历史但可进入 tool context、Project QA 返回 context bundle、direct chat 跳过 RAG 但仍携带 context bundle。

## 2026-04-25 Memory Summary v1

本轮继续完成阶段 B：轻量会话记忆摘要。实现目标是让长会话不必把全部历史都塞进 prompt，同时保持个人作品级边界，不做复杂长期用户画像。

### 主要代码改动

- 新增 `app/agent/memory_manager.py`，使用确定性压缩策略生成 `memory_summary_v1`。
- `TaskService.create_task()` 在 Agent Chat / Project QA 持久化 assistant 回复后更新 session memory。
- `Context Manager` 现在能读取 dict 形式的 `memory_summary`，并投影到 `debug_view.context_bundle.session_summary`。
- `Context Manager` 读取历史消息时改为优先取最新消息，再按时间恢复正序，避免长历史下 recent messages 拿到旧消息。
- `SessionService` 顶层返回 `memory_summary`，方便 Debug View / Monitor 查看。
- 清空 session 时会移除 `memory_summary` 和旧 `session_summary`，避免残留记忆。

### 边界

- 第一版不调用 LLM 做摘要，不新增数据库表，不做跨项目长期记忆。
- 工具型任务仍然只进入 task 列表和 `tool_context` 摘要，不写入聊天 memory。
- 主 UI 无需修改，Debug View 可以选择展示 memory 状态。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- 新增长会话压缩集成测试，覆盖 memory 触发、下一轮 Context Bundle 读取摘要、recent messages 保持最新历史。

## 2026-04-25 Agent Decision Trace v1

本轮继续完成阶段 E 的第一版：把分散在 route、context bundle、memory、retrieval trace、skill runtime、fallback warning 里的信息汇总为一条统一 Agent 决策链。

### 主要代码改动

- 新增 `app/agent/decision_trace.py`，生成 `agent_decision_trace_v1`。
- `DebugView` schema 新增 `agent_decision_trace`。
- `TaskService.create_task()` 在响应组合前生成决策链，挂入 `debug_view.agent_decision_trace`。
- 决策链固定包含 `input_summary`、`language_decision`、`intent_decision`、`context_decision`、`retrieval_decision`、`tool_decision`、`memory_decision`、`fallback_decision`、`final_response_plan`。
- 第一版不额外调用 LLM，只汇总已有后端判断，避免把 Debug 能力做成新的不稳定依赖。

### 前端影响

- 主 UI 不需要修改。
- Debug View 可选新增 `Agent Decision Trace` 分区，读取 `debug_view.agent_decision_trace.summary` 和 `decisions`。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- Direct Chat 和 Project QA 集成测试已覆盖 `agent_decision_trace_v1`、route summary、retrieval decision 和 context decision。

## 2026-04-25 RAG Readiness v1

本轮完成阶段 C 的轻量版：不新增复杂评测服务，而是把现有本地 eval runner 和 KB 状态变得更可解释。

### 主要代码改动

- `KnowledgeBaseService.status()` 新增 `effective_mode`。
- `GET /api/v1/knowledge-base/status` 新增 `rag_readiness`。
- `rag_readiness` 返回 lexical、embedding、vector store 是否 ready，以及是否仍可服务 Project QA。
- `rag_readiness.degraded_reasons` 说明为什么从 hybrid/vector 降级。
- `rag_readiness.domain_counts` 展示当前知识库 domain 覆盖情况。
- `rag_readiness.eval_command` 给出本地 RAG eval 推荐命令。
- RAG eval summary 测试补充 `no_result_ratio` 断言。

### 边界

- 不引入 reranker 服务。
- 不做学术级 benchmark。
- 不自动爬全站官方文档。
- 当前目标是能在 Debug View 和面试演示中说清楚：是否可检索、是否降级、如何评测。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- `python -m pytest tests/eval/test_rag_eval_metrics.py tests/integration/test_system_and_tasks.py::test_kb_refresh_builds_documents_and_chunks -q` 通过。

## 2026-04-25 Skill Protocol v1

本轮完成阶段 D：把 5 个核心功能统一到固定内置 Skill 协议下，便于后续功能优化时按 collector、rules、retrieval、llm_analyzer、projector 分层扩展。

### 主要代码改动

- `app/skills/registry.py` 新增 `skill_protocol_v1` manifest，给每个核心 Skill 暴露 `input_schema`、`llm_analyzer`、`debug_contract` 和 `protocol`。
- `GET /api/v1/system/capabilities` 新增 `skill_architecture.protocol_version`、`protocol_components` 和 `runtime_lifecycle_field`。
- `app/skills/runtime.py` 统一生成 `debug_view.skill.lifecycle`，包括 collector、rules、retrieval、llm、projector 五段执行状态。
- `TaskService` 在构建 skill runtime 时传入执行数据，使 lifecycle 能解释 LLM 是 completed、skipped 还是 degraded。
- `debug_view.skill.lifecycle.llm.reason` 优先使用稳定机器码，例如 `missing_openai_api_key`，方便前端 Debug View 和测试读取。

### 边界

- 不做动态 Skill 安装、不做 marketplace、不做复杂沙箱。
- 后续新增能力优先归入现有 5 个 Skill 的某一层，避免功能边界继续发散。
- 主 UI 不强制修改；Debug View 可选展示 Skill lifecycle 流水线。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- capabilities、direct chat、code review 关键 Skill Protocol 集成测试通过。

## 2026-04-25 Learning Docs v1

本轮完成阶段 F：把 Agent 架构、RAG / Memory、Skill 扩展方法和请求生命周期整理成面试展示与自学复盘文档。

### 新增文档

- `docs/agent-architecture-study.md`：解释本项目为什么是一个 Agent 后端、整体 loop、模块边界、和 nanobot 的参考关系。
- `docs/rag-and-memory-study.md`：解释 ingestion pipeline、lexical/vector/hybrid retrieval、embedding、Qdrant、官方文档整理边界和 memory 压缩。
- `docs/skill-development-guide.md`：解释 fixed built-in Skill 架构，以及 collector、rules、retrieval、llm_analyzer、projector 的扩展方法。
- `docs/request-lifecycle.md`：按 Agent Chat、Project QA、Code Review、Code Generate、Logs Analyze、Assets Inspect 复盘一次请求从 UE 到后端的完整路径。

### 文档入口

- `README.md` 已补充学习文档链接。
- `docs/improveplan.md` 标记本轮 Agent 架构优化路线 v1 完成。

### 前端影响

- 无强制前端修改。
- UE 前端如果要继续增强 Debug View，可参考 `docs/frontend-unified-handoff.md` 中已有 Context Bundle、Memory Summary、Agent Decision Trace、RAG Readiness、Skill Protocol 字段。

## 2026-04-25 Code Review LLM JSON-like 解析增强

实测时发现 Code Review 首次 LLM 分析可能返回“看起来像 JSON、但不是严格 JSON”的内容，导致用户高亮卡片显示“LLM 返回了类似 JSON 的结构化内容，但后端无法可靠解析”。Assets Inspect 正常，是因为它的输出 schema 更简单，模型更容易返回合法 JSON。

### 主要代码改动

- `app/services/llm_service.py` 增强 JSON 提取：支持 Markdown 代码块、尾逗号、未加引号的 key、Python 风格单引号字典、简单注释清理。
- `CodeReviewSkill` 的 LLM prompt 明确要求合法 compact JSON，不包 Markdown，不复制含引号源码片段。
- `CodeReviewSkill` 的 fallback 增强：即使 JSON-like 文本仍无法修复，也会从原文提取 `summary/title/reason/suggestion`，避免把解析失败提示当成主要 LLM 回答。

### 前端影响

- 不需要修改接口。
- 高亮按钮继续读取 `user_view.blocks[block_type="llm_analysis"].text` 或 `data.llm_analysis.text`。
- `data.llm_review.text` 仍只用于 Debug View，不进入普通用户展示。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- `python -m pytest -p no:cacheprovider tests/unit/test_llm_service.py tests/integration/test_system_and_tasks.py::test_code_review_llm_json_like_text_fallback_is_sanitized_for_highlights tests/integration/test_system_and_tasks.py::test_code_review_malformed_json_like_text_extracts_llm_summary tests/integration/test_system_and_tasks.py::test_assets_inspect_live_llm_uses_compact_timeout_config -q` 通过。

## 2026-04-25 Local Grep Retrieval v1

本轮开始执行 2026-04-26 计划中的双检索策略：RAG 继续保留，新增不依赖 embedding / Qdrant 的本地 markdown/code grep 检索。

### 主要代码改动

- 新增 `app/services/local_search_service.py`，支持 domain 过滤、关键词匹配、snippet、score、matched_terms。
- `KnowledgeBaseService.status()` 新增 `local_search_readiness`。
- `KnowledgeBaseService.project_qa()` 在 RAG 无命中时 fallback 到 local grep。
- `CodeGenerateSkill` 优先把 local grep 命中的 `code_reference/examples/engine_notes` 作为参考输入。
- `CodeReviewSkill` 通过 guidance retrieval 链路使用 local grep 补充 `team_rules/engine_notes/project_docs/examples`，并同步到 `debug_view.local_search`。
- `DebugView` schema 新增 `local_search`。
- 默认 `KB_SOURCE_PATHS` 接入 `./knowledge`，后续已在 2026-04-26 收口为仅扫描 `./knowledge`。

### 本地知识种子

- 新增 `knowledge/engine-notes`：Actor 生命周期、软引用与异步加载、StaticMesh/Nanite/LOD/Collision、Modules/Build.cs。
- 新增 `knowledge/examples`：异步资产加载示例。
- 新增 `knowledge/team-rules`：UE 代码审查规则。
- 新增 `knowledge/asset-rules`：Blueprint / StaticMesh 资产检查清单。
- 新增 `knowledge/code-reference`：Actor/Component 模式示例。

### 前端影响

- 主 UI 不需要修改。
- Debug View 可选显示 `debug_view.local_search`。

### 验证

- `python -m ruff check app tests --no-cache` 通过。
- Local Search 单元测试、系统 bootstrap、Code Generate 本地参考命中集成测试通过。

## 2026-04-26 知识库范围与 Code Generate 展示修正

本轮根据实际测试反馈修正两个体验问题：Agent Chat 的用户知识库不应引用后端开发文档；Code Generate 的虚拟草稿不应被前端理解为真实写入磁盘的文件。

### 主要代码改动

- 默认 `KB_SOURCE_PATHS` 从 `../backend.md,../forward.md,./docs,./knowledge` 收口为 `./knowledge`。
- 当前本地 `.env` 同步改为 `KB_SOURCE_PATHS=./knowledge`。
- Code Generate 的泛化 `target_type` 兼容增强：`general/code/cpp/ue_cpp` 等会按 UE C++ 草案处理。
- Code Generate 兜底模板不再轻易返回 `draft.txt`，未知非代码类型使用 `GeneratedDraft.md`。
- `generated_items[]` 新增 `write_status=not_written` 和 `is_virtual=true`。
- `data.write_policy.written_to_disk=false` 明确说明后端没有写入工程文件。

### 前端影响

- 知识库来源路径显示无需改接口；如果仍看到 `backend.md` / `forward.md` / `docs/...`，需要触发 `POST /api/v1/knowledge-base/reindex` 清理旧索引。
- Code Generate 主 UI 应把 `generated_items` 渲染为代码结果按钮 / Tab / 列表，不要把 `file_path` 文案描述成“已生成到磁盘”。
- `write_status=not_written` 是正常状态，不是错误。

## 2026-04-26 常用 UE 代码知识库补强

本轮根据测试反馈补强 Code Generate 的常用 UE 场景。用户问“角色增强输入代码怎么写”时，之前因为知识库缺少 Enhanced Input Character 示例，且兜底模板只有普通 Actor 骨架，导致返回 BeginPlay/Tick 空实现。现在进一步补齐交互组件、射线交互、GameInstanceSubsystem 和 DataAsset/GameplayTag 笔记。

### 主要代码改动

- 新增 `knowledge/engine-notes/ue-enhanced-input-character.md`。
- 新增 `knowledge/engine-notes/ue-common-code-generation-patterns.md`。
- 新增 `knowledge/code-reference/enhanced-input-character-example.h`。
- 新增 `knowledge/code-reference/enhanced-input-character-example.cpp`。
- 新增 `knowledge/code-reference/interaction-component-example.h/.cpp`。
- 新增 `knowledge/code-reference/line-trace-interaction-component-example.h/.cpp`。
- 新增 `knowledge/code-reference/game-instance-subsystem-example.h/.cpp`。
- 新增 `knowledge/examples/enhanced-input-buildcs-note.md`。
- 新增 `knowledge/examples/dataasset-gameplaytag-note.md`。
- `generate_code_draft()` 增强中文/英文 Enhanced Input Character 请求识别。
- `generate_code_draft()` 增强交互组件、射线交互、Subsystem 请求识别。
- 泛化 `target_type=ue_cpp/general/code/cpp` 时，如果需求包含“角色增强输入 / Enhanced Input / Input Mapping Context”等信号，会返回 `ACharacter` 草稿。
- UE C++ 草稿路径改为更常见的 `Source/<Module>/Public/<Class>.h` 和 `Source/<Module>/Private/<Class>.cpp`。
- Code Generate prompt 增加 Enhanced Input / Character 生成约束，提醒 LLM 生成 Mapping Context、Input Action、EnhancedInputComponent 绑定和 Build.cs 依赖说明。
- Code Generate prompt 增加交互组件、射线交互、Subsystem 场景约束，要求尽量给出具体方法体而不是空骨架。

### 前端影响

- 主 UI 不需要修改。
- 继续展示 `generated_items[].code`。
- 测试时建议确认“角色增强输入代码怎么写”能展开看到 `.h/.cpp`，并包含 `AddMappingContext`、`BindAction`、`Move`、`Look`。
- 也建议测试“交互组件 overlap 怎么写”“射线交互组件怎么写”“全局管理器子系统怎么写”。

## 2026-04-26 UE 前端回传记录：Code Generate 草稿展示

UE 前端回传的 `frontend-unified-handoff.md` 已确认第 24 节的 Code Generate 展示契约落地。前端现在会把 `generated_items` 当成虚拟代码草稿按钮 / Tab 展示，点击后预览 `generated_items[].code`，并把 `file_path` 标注为建议路径。

### 当前结论

- `write_status=not_written`、`is_virtual=true` 已被前端视为正常状态，不再作为错误或真实落盘文件处理。
- 后端暂不需要为 Code Generate 展示再新增字段。
- 后续联调重点转到第 25 节常用 UE 场景：Enhanced Input Character、Interaction Component、LineTrace Interaction、GameInstanceSubsystem。

### 下一次前端回传希望确认

- 是否能完整展示 `.h/.cpp` 代码正文，而不是只展示建议路径。
- 是否能在草稿正文中看到 `AddMappingContext`、`BindAction`、`LineTraceSingleByChannel`、`UGameInstanceSubsystem` 等关键符号。
- `payload.target_type`、`context.current_module` 的实际提交值，方便后端继续优化模块名和路径推断。

## 2026-04-26 Agent Chat 知识库目录与中英检索收口

用户继续测试后确认 Code Generate 当前展示链路基本可用，新的问题集中在 Agent Chat / Project QA：询问“知识库有哪些内容”时会返回文件甚至代码内容；询问“actor的生命周期是什么”时，看起来像是 LLM 自己回答，用户不容易判断知识库是否奏效。

### 主要代码改动

- 新增知识库目录查询识别：`知识库有哪些内容`、`知识库里有什么`、`list knowledge base contents` 这类问题现在返回目录摘要。
- 目录摘要使用 `answer_mode=knowledge_catalog`，只列文档标题、domain、路径、chunk 数，不展开源码正文。
- `data.catalog` 返回 `document_count`、`domain_counts`、`items`、`source_paths`，用于 Debug View 判断当前索引范围。
- Project QA 的 `data.answer_mode` 和 `data.answer_generation.mode` 会标明本轮是 `knowledge_catalog`、普通 retrieval fallback，还是 LLM synthesis。
- 本地 lexical RAG / local grep 增加轻量中英查询扩展，例如“生命周期”会扩展到 `lifecycle / constructor / BeginPlay / Tick / EndPlay`。
- 扩展词只影响 query 侧，不改写知识库原文，也不替代 embedding / Qdrant。

### 当前结论

- “知识库有哪些内容”这类元问题应返回目录，不应返回代码正文。
- “actor的生命周期是什么”在未接入向量模型时也能更稳定命中 `knowledge/engine-notes/ue-actor-lifecycle.md`。
- 如果 LLM 已配置，最终回答仍可能由 LLM 综合表达；判断知识库是否参与，优先看 `data.retrieved_docs`、`data.citations`、`debug_view.retrieval`。

### 验证

- `python -m pytest -p no:cacheprovider tests/unit/test_local_search_service.py -q` 通过。
- `python -m pytest -p no:cacheprovider tests/integration/test_system_and_tasks.py::test_agent_chat_knowledge_catalog_lists_sources_without_code_bodies tests/integration/test_system_and_tasks.py::test_project_qa_chinese_actor_lifecycle_hits_engine_note -q` 通过。
- `python -m ruff check app tests --no-cache` 通过。

## 2026-04-26 Code Review Agent Workflow v1

本轮开始执行面试级 Agent 项目增强计划，先选 Code Review 做最小闭环：不新增主菜单、不写入工程文件，而是在现有代码审查结果后追加“修复草稿”和“验证清单”，用于展示 Agent 如何组合工具链。

### 主要代码改动

- 新增 `app/agent/review_workflow_advisor.py`。
- Code Review 输出新增 `data.agent_workflow`、`data.fix_draft`、`data.validation_plan`。
- `user_view.blocks` 在原有 `summary -> llm_analysis -> issues -> recommendations -> references -> next_steps` 之后追加 `agent_workflow`、`fix_draft`、`validation_plan`。
- Debug View 的 `tools` 和 `step_results` 增加 `draft_fix_plan`、`build_validation_plan`。
- `fix_draft` 明确 `written_to_disk=false`、`is_virtual=true`，只作为建议展示。
- `validation_plan` 会根据规则命中生成编译、PIE、UObject 生命周期、Tick 性能、线程上下文、资产引用、蓝图编译、Output Log 复查等检查项。
- `skill_catalog` 的 CodeReviewSkill projector outputs 补充 `data.agent_workflow`、`data.fix_draft`、`data.validation_plan`。

### 前端影响

- 主 UI 不强制修改。
- 旧 Code Review 高亮顺序不变，前 6 个 block 仍保持稳定。
- 如果前端要增强展示，可在 Code Review 结果区新增三个折叠卡：Agent Workflow、Fix Draft、Validation Plan。

### 验证

- `python -m ruff check app/agent/review_workflow_advisor.py app/skills/executors/code_review.py app/skills/registry.py tests/integration/test_system_and_tasks.py --no-cache` 通过。
- `python -m pytest -p no:cacheprovider tests/integration/test_system_and_tasks.py::test_code_review_file_listing_and_selected_file_review -q` 通过。

## 2026-04-26 Validation Advisor v1

本轮继续完成面试级 Agent 项目增强阶段 B：把验证建议从 Code Review 扩展到 Code Generate、Logs Analyze、Assets Inspect，形成“分析/生成之后告诉用户如何验证”的研发闭环。

### 主要代码改动

- 新增 `app/agent/validation_advisor.py`。
- `CodeGenerateSkill` 新增 `data.validation_plan` 和 `validation_plan` 用户视图块。
- `LogsAnalyzeSkill` 新增 `data.validation_plan` 和 `validation_plan` 用户视图块。
- `AssetsInspectSkill` 新增 `data.validation_plan` 和 `validation_plan` 用户视图块。
- 对应 Debug View / Step Results 增加 `build_validation_plan`。
- `skill_catalog` 的 projector outputs 补充 `data.validation_plan`。

### 当前边界

- 不自动写入工程。
- 不自动运行 UE 测试。
- 不保存、重命名、迁移资产。
- 只提供面向编辑器人工验证和后续日志分析的 checklist。

## 2026-04-26 面试展示文档 v1

本轮补齐面试展示和自学复盘入口，目标是让项目不只“能跑”，还可以在面试中快速讲清楚 Agent 架构和研发管线价值。

### 新增文档

- `docs/interview-demo-script.md`：5-8 分钟演示脚本，覆盖 Agent Chat、Code Generate、Code Review Workflow、Assets Inspect、Logs Analyze。
- `docs/agent-project-study-notes.md`：复盘 Agent loop、Context / Memory、RAG / Local Grep、Skill、User View / Debug View、Validation Advisor、Project Inventory。

### 文档入口

- `README.md` 已加入两个新文档链接。

## 2026-04-26 UE 前端回传复核：Workflow / Validation

UE 前端回传的 `frontend-unified-handoff.md` 与 `backend-action-items.md` 已同步后端第 25-29 节。前端当前策略与后端一致：不新增主菜单、不改变核心接口，新增 `agent_workflow`、`fix_draft`、`validation_plan` 先通过通用 User View block fallback 和 Debug View Raw Response 承接。

### 复核结论

- Code Generate 常用 UE 场景继续使用 `generated_items` 草稿按钮 / Tab。
- Agent Chat 的 `knowledge_catalog` 暂不做独立知识库目录 UI，先通过普通回答和 Debug View 查看。
- Code Review 的 Workflow / Fix Draft / Validation Plan 不影响原有 summary、llm_analysis、issues、recommendations。
- Code Generate、Logs Analyze、Assets Inspect 的 `validation_plan` 可先作为普通 block 展示。
- 当前后端无需新增字段或调整接口，可进入联调测试阶段。

### 测试关注

- 前端不能把 `fix_draft` 展示成“已修复”。
- 前端不能把 `validation_plan` 展示成“已执行测试”。
- `written_to_disk=false`、`is_virtual=true`、`automation_level=manual_or_editor` 都是正常建议状态。

## 2026-04-26 Logs Analyze 输入优化

本轮优化日志分析体验，解决前端必须粘贴完整日志文本才能分析的问题。后端保持原接口 `POST /api/v1/tasks/logs-analyze` 不变，但 payload 输入方式更灵活。

### 主要代码改动

- `analyze_ue_log()` 支持从 `log_file_path` / `log_path` / `file_path` / 路径型 `log_source` 读取日志文件。
- 支持 `selected_log_text`、`log_excerpt`、`error_excerpt`、`error_lines` 这类短错误片段。
- 支持 `notes` / `user_notes` 和 `attachment_paths` / `attachments`。
- 没有 `line_window` 时默认读取文件尾部窗口，避免把超长 UE 日志整体塞入分析链路。
- 有 `line_window` 时读取指定行号范围。
- `data.input_context` 和 `data.parser_diagnostics.input_collection` 增加 `input_mode`、`read_diagnostics`、`attachment_diagnostics`，便于 Debug View 排查。
- `LogsAnalyzeSkill` 的 collector 从 `ue_log_text_payload` 更新为 `ue_log_input_payload`。

### 前端影响

- 不新增主菜单，不改接口路径。
- Logs Analyze 面板应取消“必须粘贴文本”的限制。
- `Analyze Log` 启用条件改为：存在粘贴片段或存在日志文件路径。
- 普通用户仍看结构化 `user_view.blocks`；文件读取诊断放 Debug View。

### 边界

- 后端只读取前端显式传入的路径，不主动扫描项目日志目录。
- 后端只读日志，不删除、不移动、不修改文件。
- 附件只作为辅助文本上下文，不做崩溃 dump 二进制解析。

## 2026-04-27 Logs Analyze LLM 分析与检索质量门槛

本轮继续优化日志分析的可解释性，明确区分“规则解析结果”“LLM 综合解释”和“知识库参考”。

### 主要代码改动

- `LogsAnalyzeSkill` 新增 `data.llm_analysis`、`data.llm_analysis_raw`。
- `user_view.blocks` 在 `Log Summary` 后追加 `llm_analysis`，再展示 `Issue Families` 和建议动作。
- LLM 未配置时稳定返回 `llm_analysis.status=skipped` 和 `reason_code=missing_openai_api_key`，不影响规则解析结果。
- Debug View 增加 `llm_log_analysis_synthesis` tool/step。
- 日志知识库检索新增 `retrieval_quality_gate`，低于阈值的 `incident_history / engine_notes / project_docs` 命中不会进入用户 citations，也不会作为 LLM 事实上下文。

### 当前策略

- 先用确定性解析提取 Error/Fatal、Warning、callstack、模块和 `/Game/` 资源路径。
- 再用 LLM 对解析事实做自然语言综合解释。
- 知识库只在 `confidence` 或 `top_score` 达标时作为辅助参考。
- 如果知识库不达标，Logs Analyze 仍正常用规则结果和 LLM 自身能力解释日志。

### 前端影响

- Logs Analyze 主结果区建议显示“LLM 分析结果”卡片。
- `llm_analysis.status=skipped` 显示为轻提示，不作为任务失败。
- `retrieval_quality_gate` 只放 Debug View。

## 2026-04-27 面试增强第一阶段

本轮开始执行“9/10 Agent 项目边界版”优化，但保持个人作品和 UE 联调稳定性优先。

### 主要代码改动

- `app/tools/registry.py` 升级为声明式 Tool Registry，工具能力卡包含触发词、输入字段、schema、副作用级别、超时和检索需求。
- `app/agent/router.py` 不再维护独立 `TOOL_KEYWORDS`，工具候选来自 Tool Registry。
- `/api/v1/system/capabilities` 新增 `tool_registry`，前端和面试展示可以直接读取能力卡。
- 新增 `app/core/startup_checks.py`，`/api/v1/system/health` 返回 `startup_checks`。
- `app/main.py` 启动时输出 warning/error 级配置校验结果。
- `Agent Chat / Project QA` 新增 `data.react_loop` 和 `debug_view.react_loop`，用于展示 ReAct Lite 轨迹。
- 新增 `.github/workflows/ci.yml`：Ruff、pytest、RAG eval smoke。
- `scripts/run_rag_eval.py` 新增 `--min-hit-at-k`、`--min-route-accuracy` 阈值。

### 文档补充

- `docs/improveplan.md`：记录必做增强、可选加分和开发边界。
- `docs/backend-user-guide.md`：补充 Tool Registry、ReAct Lite、配置校验、测试/eval/CI 用法。
- `docs/architecture.md`：新增架构图和分层说明。

### 边界

- ReAct Lite 当前是受控可解释轨迹，不让 LLM 自动执行写操作。
- CI 不做部署、不做 Docker 镜像推送、不做跨平台矩阵。
- 配置校验对本地开发友好：缺 Key、缺 Qdrant 先 warning，不阻塞服务启动。

## 2026-04-27 ReAct 受控工具选择 v1

本轮把 `Agent Chat / Project QA` 的 `react_loop` 从事后解释升级为受控工具规划：LLM 可用时可以建议只读工具，后端负责白名单校验和 deterministic fallback。

### 主要代码改动

- `Project QA` 新增 `_react_lite_tool_plan()`。
- LLM planner 只能选择：
  - `retrieve_project_knowledge`
  - `query_project_inventory`
  - `read_project_file`
- 新增 `read_project_file` ToolSpec 能力卡。
- 新增只读文件读取逻辑：
  - 必须限制在 `context.project_root` 内。
  - 只允许文本/code/config 类型后缀。
  - 限制读取字节数，避免超长文件进入上下文。
- Project QA 响应新增 `data.project_file`、`debug_view.project_file`、`tool_plan.planner_decision`、`tool_plan.tool_calls`。
- `debug_view.react_loop.steps[]` 会记录 `read_project_file` 的 action / observation。

### 测试

- 新增集成覆盖：自由聊天询问当前文件时，后端读取 `project_root + current_file` 并写入 Debug View。

### 边界

- 受控 ReAct 只用于 Project QA。
- 不做自动写文件或自动执行命令。
- LLM 规划失败不影响原 deterministic 路径。

## 2026-04-27 Tool Contract v1

本轮补齐 Tool Registry 的契约校验能力，目标是让后续新增工具更稳定、更容易调试。

### 主要代码改动

- `ToolSpec` 新增 `output_schema`。
- Tool capability card 暴露 `input_schema` 和 `output_schema`。
- 新增 `app/tools/contracts.py`：
  - `validate_tool_registry`
  - `validate_tool_call_input`
  - `validate_tool_result`
- `startup_checks` 新增 `tool_registry_contracts`。
- `Project QA` 响应新增 `data.tool_contracts` 和 `debug_view.tool_contracts`。

### 测试

- 单元测试覆盖 Registry 自检、缺少必填输入、合法结果校验。
- 集成测试覆盖 Health 中的 Tool Registry check，以及当前文件读取工具的 input/result contract。

### 边界

- 只做轻量 required/type 校验。
- 不引入 jsonschema 依赖。
- 不做动态工具热加载。

## 2026-04-27 Self-Reflection 轻量版

本轮新增回答后的质量自检，用确定性规则判断回答是否有证据、是否降级、是否需要补上下文。

### 主要代码改动

- 新增 `app/agent/self_reflection.py`。
- `Project QA` 和 `Direct Answer` 响应新增 `data.self_reflection`。
- Debug View 新增 `debug_view.self_reflection`。
- Agent Decision Trace 新增 `self_reflection_decision`。

### 自检项

- `answer_present`
- `evidence_available`
- `confidence_floor`
- `degraded_warnings`

### 边界

- 不额外调用 LLM。
- 不进入普通用户主 UI。
- 不做多轮反思或多 Agent 辩论。

## 2026-04-27 Docker 本地演示入口

本轮补充容器化演示骨架，用于项目留档和面试展示环境一致性。

### 新增文件

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `Makefile`

### 默认行为

- `docker compose up --build` 启动 `app + qdrant`。
- App 暴露 `8000`。
- Qdrant 暴露 `6333`。
- 默认 `EMBEDDING_ENABLED=false`，优先保证 lexical RAG 和后端主体能力可启动。

### 边界

- 不做 K8s / Helm。
- 不做镜像推送。
- 不做生产部署参数优化。
- Docker 只作为本地演示和可复现运行环境。

## 2026-04-27 轻量长期记忆 v1

本轮补齐 Agent Memory 能力，但保持个人作品边界：不用 LLM 抽取、不依赖 Qdrant、不做用户画像。

### 主要代码改动

- `app/agent/memory_manager.py`
  - 新增长期记忆抽取。
  - 新增 `recall_long_term_memory()`。
  - `update_session_memory()` 即使未达到 session summary 阈值，也会抽取长期记忆。
- `app/agent/context_manager.py`
  - Context Bundle 新增 `long_term_memory`。
  - Prompt excerpt 注入 `Long-term project memory`。
- `app/agent/decision_trace.py`
  - `memory_decision` 增加长期记忆召回状态和条目。
- `app/db/repositories/sessions.py`
  - clear session 时清理当前 session 的长期记忆条目。

### 测试

- 新增集成覆盖：Session A 写入项目约定，Session B 使用同一 `project_name` 能在 Context Bundle 召回。

### 边界

- SQLite + keyword recall。
- 不做向量记忆、不做图记忆。
- 不新增前端接口。

## 2026-04-27 RAG Eval Markdown Report

本轮把 RAG eval 从“命令行 JSON 输出”补成“可读报告”。

### 主要代码改动

- 新增 `app/rag/evaluation/reporting.py`，负责把 eval JSON report 渲染成 Markdown。
- `scripts/run_rag_eval.py` 新增 `--markdown-output` 参数。
- 新增单测覆盖 Markdown report 的 summary 和 cases 输出。
- 生成 `docs/rag-eval-report.md`，用于面试展示当前检索质量、路由准确率和引用覆盖。
- CI 会额外上传 `ci-rag-eval.json` 和 `ci-rag-eval.md` artifact。

### 当前 smoke 结果

- `cases=4`
- `hit_at_k=0.5`
- `mrr=0.5`
- `route_accuracy=1.0`
- `citation_coverage=1.0`
- `no_result_ratio=0.5`

### 边界

- 这是本地 smoke eval，不是大规模 benchmark。
- 目前只验证固定样例集，后续扩充知识库或任务类型时再扩充 dataset。
- Markdown 报告只用于复盘和面试展示，不是线上监控系统。

## 2026-04-27 可选 Token SSE 流式入口

前端回传确认：当前 UE HTTP 客户端仍以完整 JSON 响应为主，暂不支持 `text/event-stream` 持续读取和逐 token 更新同一条 assistant 气泡。因此后端采用兼容方式新增可选入口，不改变旧接口。

### 主要代码改动

- 新增 `POST /api/v1/chat/runs/stream`。
- `GET /api/v1/chat/runs/{run_id}/events/stream` 保持历史事件回放语义不变。
- `TaskService.create_task()` 支持可选 `stream_sink`。
- `LLMService.complete()` 支持可选流式模式，OpenAI-compatible `stream=true` 时逐 delta 回调。
- Project QA 流式事件包含：
  - `tool_call`
  - `tool_result`
  - `assistant_delta`
  - `final`
- Direct Answer 流式事件包含：
  - `assistant_delta`
  - `final`
- 新增集成测试覆盖未配置 LLM 时的 SSE fallback：仍返回 `stream_opened/run_started/final`。

### 边界

- 只对 `Agent Chat / Project QA` 提供可选流式入口。
- Code Review / Code Generate / Logs Analyze / Assets Inspect 继续同步返回。
- 必须保留非流式 `POST /api/v1/chat/runs` fallback。
- LLM 未配置或流式请求失败时，不伪造 token，依靠 `final` 返回完整响应或 `error` 报告失败。
- 暂不做全项目 async，不引入消息队列。

## 2026-04-30 UE C++ 蒸馏知识包 v1

本轮把本地 `XG-UE-Cpp-Course-Skill-main` 作为参考源，蒸馏出适合本项目的 UE C++ 知识包。重点是覆盖面试和实际使用高频主题，而不是复制完整课程。

### 主要代码改动

- 新增 `knowledge/engine-notes/uecpp-reflection-containers-delegates.md`。
- 新增 `knowledge/engine-notes/uecpp-async-networking-gas.md`。
- 新增 `knowledge/examples/uecpp-http-websocket-asyncaction-note.md`。
- 新增 `knowledge/examples/developer-settings-subsystem-note.md`。
- 新增 `knowledge/team-rules/uecpp-review-threading-networking-rules.md`。
- 新增 `knowledge/prompt-packs/ue-cpp-practices.md`。
- 新增 HTTP、DeveloperSettings、GAS 的最小 code reference。
- `LocalSearchService` / ingestion capabilities / parser 新增 `prompt_packs` domain。
- `sparse.py` 补充中文查询到英文 UE 术语的扩展词。
- `generate_code_draft()` 新增 HTTP AsyncAction、WebSocket Subsystem、DeveloperSettings、GAS AttributeSet 兜底模板。
- `CodeGenerationService` 的检索 domain 默认加入 `prompt_packs`。

### 验证

- `python -m compileall app`
- `pytest tests/unit/test_code_generate_tool.py`
- `pytest tests/unit/test_local_search_service.py`

### 边界

- 不直接提交外部课程原文或大段 Skill 文档。
- 新增知识是自写总结和最小模式示例。
- 不新增 UE 前端菜单；现有 Code Generate / Project QA / Code Review 自动受益。
- 如果需要向量 RAG 覆盖，仍需执行 `POST /api/v1/knowledge-base/reindex` 并配置 embedding / Qdrant。

## 2026-04-30 Agent Chat UE 技术知识路由修正

本轮复核用户反馈：Code Generate / Code Review 能命中本地知识库，但 Agent Chat 询问 GAS、多线程等 UE 技术概念时像是 LLM 直接回答。

### 主要代码改动

- `app/agent/router.py`
  - 新增 UE 技术知识 domain hints 和 question hints。
  - 新增 `heuristic_ue_knowledge_signal` 路由分支。
  - 保持 `query_project_inventory` 和明确当前文件/项目问答的优先级高于 UE 通用知识路由。
- `tests/unit/test_router.py`
  - 覆盖 “GAS技能系统是什么” 和 “UE多线程怎么做” 路由到 `retrieve_project_knowledge`。
  - 覆盖 “当前项目有哪些蓝图资产，你列一下” 仍路由到 `query_project_inventory`。

### 验证

- `pytest tests/unit/test_router.py tests/unit/test_local_search_service.py tests/unit/test_code_generate_tool.py -q`

### 边界

- 不把外部参考仓库 283 个 knowledge 文件全量复制进项目。
- 当前知识库仍是蒸馏版，后续按测试缺口补充高频 UE 场景。
- UE 前端不需要改接口，只需在 Debug View 兼容新的 `decision_source` 字符串。

## 2026-04-30 本地私有全量知识源接入

本轮把“外部仓库作为参考”的边界落地成双轨机制：公开仓库保持原创蒸馏知识，本地使用者可以通过 `.env` 接入自己合法拥有的全量资料。

### 主要代码改动

- `.env.example`
  - 增加本地私有知识源示例。
- `.gitignore`
  - 忽略 `private-knowledge/`、`external-knowledge/`、`local-knowledge/` 等本地资料目录。
- `scripts/scan_knowledge_sources.py`
  - 新增知识源扫描工具。
  - 只统计路径、后缀、domain、大小和缺失路径。
  - 支持 JSON / Markdown 输出。
- `tests/unit/test_scan_knowledge_sources.py`
  - 覆盖 domain 统计、缺失路径和 Markdown 报告输出。

### 文档

- README 记录 `KB_SOURCE_PATHS` 私有扩展示例。
- User Guide 补充“本地私有全量知识源接入”。
- Frontend Handoff 说明前端无须改 UI，只会看到更多 citations / references。
- Improve Plan 记录公开蒸馏库和本地私有全量库双轨方案。

### 边界

- 不提交外部课程原文。
- 不生成私有知识正文摘要。
- 扫描报告建议输出到 `storage/artifacts/`，该目录默认不提交。
