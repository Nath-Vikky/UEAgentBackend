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
