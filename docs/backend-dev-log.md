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
