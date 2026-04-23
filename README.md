# UE Agent Backend

这是配合 Unreal Editor 插件使用的本地 Agent 后端。项目定位是个人作品集，不做服务器部署、多人权限体系或企业级运维包装，目标是把能力收口到少而清晰、可联调、可展示的一版。

## 当前保留的 5 个核心功能

- `Agent Chat / Project QA`
- `Code Review`
- `Code Generate`
- `Logs Analyze`
- `Assets Inspect`

以下能力仍保留兼容代码，但已经退出主菜单范围：

- `config_generate`
- `config_validate`
- `assets_plan`
- `assets_execute`
- `perf_analyze`

## 为什么它可以算一个 Agent 后端

它不只是把请求转发给 LLM，而是具备完整的 Agent 闭环：

- 统一入口与任务路由
- 自由聊天与项目问答分流
- 知识库导入、检索和可选向量召回
- session / task / run / artifact / trace 持久化
- `user_view / debug_view` 双视图
- `/metrics`、`/api/v1/system/alerts`、事件回放、调试快照

## 关键接口

### 系统

- `GET /api/v1/system/health`
- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/capabilities`
- `GET /api/v1/system/runtime-profiles`
- `GET /api/v1/system/settings`
- `GET /api/v1/system/alerts`
- `GET /metrics`

### 聊天与任务

- `POST /api/v1/chat/runs`
- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/tasks/project-qa`
- `POST /api/v1/tasks/code-review`
- `POST /api/v1/tasks/code-review/files`
- `POST /api/v1/tasks/code-generate`
- `POST /api/v1/tasks/logs-analyze`
- `POST /api/v1/tasks/assets-inspect`
- `GET /api/v1/tasks/recent`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/artifacts`

### Session

- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/history`
- `GET /api/v1/sessions/{session_id}/tasks`
- `POST /api/v1/sessions/{session_id}/clear`

### Knowledge Base

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`
- `POST /api/v1/knowledge-base/import`
- `POST /api/v1/knowledge-base/reindex`
- `GET /api/v1/knowledge-base/documents`
- `GET /api/v1/knowledge-base/jobs/{job_id}`
- `POST /api/v1/knowledge-base/jobs/{job_id}/retry`
- `DELETE /api/v1/knowledge-base/documents/{doc_id}`

### Project Inventory

- `POST /api/v1/project-inventory/snapshot`
- `GET /api/v1/project-inventory/summary`
- `GET /api/v1/project-inventory/assets`
- `GET /api/v1/project-inventory/assets/{asset_id}`
- `GET /api/v1/project-inventory/code-files`
- `POST /api/v1/project-inventory/query`

## 快速启动

在 `backend/` 目录下执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果只是临时本地验证，不跑迁移通常也能先启动，因为应用启动时会尝试 `create_all`。

## 最小配置

### 只接入 LLM

至少配置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `CHAT_MODEL`

### 启用知识库

再补：

- `KB_SOURCE_PATHS`
- `KB_DIR`

### 启用 Embedding / Qdrant

再补：

- `EMBEDDING_ENABLED=true`
- `EMBEDDING_MODEL`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `QDRANT_COLLECTION`

## 当前保留的文档入口

- [docs/backend-user-guide.md](./docs/backend-user-guide.md)
- [docs/frontend-unified-handoff.md](./docs/frontend-unified-handoff.md)
- [docs/backend-dev-log.md](./docs/backend-dev-log.md)

## 当前联调状态

截至 2026-04-21，UE 端反馈的 Agent Chat 路由 500、Code Review 文件扫描字段、选中文件读取调试信息、Assets Inspect 默认命名检查已经补齐。前端对接请优先阅读 [docs/frontend-unified-handoff.md](./docs/frontend-unified-handoff.md)，其中第 11 节记录了本轮新增字段和 UI 渲染注意事项。

二次联调后，Code Review 已固定输出 `summary/issues/recommendations/references/next_steps`，并在 LLM 可用时尝试综合审查；LLM 或 KB 不足时会降级到当前文件内容和通用 Unreal/C++/C# 规则。Assets Inspect 的用户可见 `reason/suggestion` 已按最终输出语言本地化。

## 当前边界

- `events/stream` 仍然是事件回放，不是 token 级实时流
- `code_generate` 已支持“先查代码知识再生成”，但仍不直接写用户工程，也不做编译验证
- `LangSmith / OTel` 仍是本地契约与元数据层，不是远端生产观测链路
- 资产依赖与引用关系仍依赖插件从编辑器侧采集后传给后端

## 2026-04-22 架构补充

- `GET /api/v1/system/capabilities` 现在包含 `skill_catalog` 和 `skill_architecture`，用于说明 5 个固定内置 Skill 的边界。
- 每次任务响应现在包含 `debug_view.skill`、`data.skill`、`trace_summary.skill_id`，用于确认本次执行对应哪个固定 Skill。
- Code Review 的 UE 源码扫描/读取属于 `CodeReviewSkill` 内部 collector，不是单独主功能。
- `CodeReviewSkill`、`CodeGenerateSkill`、`LogsAnalyzeSkill`、`AssetsInspectSkill` 已抽离为独立 executor，前端调用方式不变。
- `GET /api/v1/knowledge-base/status` 现在包含 `ingestion_pipeline`、`format_groups`、`parser_dependencies`、`knowledge_domains`。
- `POST /api/v1/knowledge-base/import` 的文本导入同时兼容 `text` 和 `content`，并保存 `metadata`、`tags`、`doc_type`。
- 后续收缩计划已同步到 `docs/improveplan.md`，方便 GitHub 仓库内统一查看。

## 2026-04-23 前端联调补充

- Project Inventory 快照响应已稳定包含 `snapshot.status`、`snapshot.summary`、`snapshot.scan_diagnostics`。
- `code_files[].last_modified` 已与 `modified_at` 兼容，前端扫描结果可直接提交。
- Code Review / Assets Inspect 的 `llm_analysis` 已包含用户可见 `reason` 和调试用 `reason_code`。
