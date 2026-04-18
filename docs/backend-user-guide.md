# UE Agent Backend 使用手册

当前手册覆盖 `backend.md` 的 Phase 1 到 Phase 4：后端骨架、双视图契约、RAG 底座、工程任务接口、统一聊天入口和 Proposal 审批闭环。

## 当前可用接口

- 系统：
  - `GET /api/v1/system/health`
  - `GET /api/v1/system/bootstrap`
  - `GET /api/v1/system/capabilities`
  - `GET /api/v1/system/settings`
  - `GET /api/v1/system/runtime-profiles`
- 统一聊天：
  - `POST /api/v1/chat/runs`
  - `GET /api/v1/chat/runs/{run_id}`
  - `GET /api/v1/chat/runs/{run_id}/user-view`
  - `GET /api/v1/chat/runs/{run_id}/debug-view`
  - `GET /api/v1/chat/runs/{run_id}/events/stream`
  - `POST /api/v1/chat/runs/{run_id}/cancel`
- 任务：
  - `POST /api/v1/tasks/project-qa`
  - `POST /api/v1/tasks/code-review`
  - `POST /api/v1/tasks/code-generate`
  - `POST /api/v1/tasks/logs-analyze`
  - `POST /api/v1/tasks/config-generate`
  - `POST /api/v1/tasks/config-validate`
  - `POST /api/v1/tasks/assets-inspect`
  - `POST /api/v1/tasks/perf-analyze`
  - `GET /api/v1/tasks/recent`
  - `GET /api/v1/tasks/{task_id}`
  - `GET /api/v1/tasks/{task_id}/user-view`
  - `GET /api/v1/tasks/{task_id}/debug-view`
  - `GET /api/v1/tasks/{task_id}/trace`
  - `GET /api/v1/tasks/{task_id}/artifacts`
- Proposal：
  - `GET /api/v1/proposals/pending`
  - `GET /api/v1/proposals/{proposal_id}`
  - `POST /api/v1/proposals/{proposal_id}/decision`
  - `GET /api/v1/proposals/decisions/{decision_id}`
- 知识库：
  - `GET /api/v1/knowledge-base/status`
  - `POST /api/v1/knowledge-base/refresh`
  - `POST /api/v1/knowledge-base/import`
  - `GET /api/v1/knowledge-base/import-jobs/{job_id}`
- 观测：
  - `GET /metrics`

## 快速启动

1. 参考 [env-setup.md](./env-setup.md) 创建虚拟环境并安装依赖。
2. 在 `backend/` 目录复制 `.env.example` 为 `.env`。
3. 执行：

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

4. 首次启动后建议先访问：

- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/capabilities`
- `GET /api/v1/knowledge-base/status`

## 关键环境变量

- `DATABASE_URL`
  - 本地默认 `sqlite:///./storage/app.db`
- `KB_SOURCE_PATHS`
  - 默认知识源列表
- `RAG_MODE`
  - 支持 `hybrid`、`semantic`、`lexical`
- `RAG_FALLBACK_MODE`
  - 当前默认 `lexical_only`
- `EMBEDDING_ENABLED`
  - 关闭后直接走词法检索兜底
- `QDRANT_URL`
  - 若不可达，系统会在 debug 字段里标记降级
- `LANGSMITH_TRACING`
  - 当前决定 `trace_summary.provider` 的展示逻辑
- `LANGSMITH_PROJECT`
  - 当前写入 trace 摘要与系统设置快照

## 如何使用统一聊天入口

调用 `POST /api/v1/chat/runs`：

- 普通闲聊会落到 `direct_answer`
- 工程文档、研发说明、接口/规范问题会落到 `project_qa`
- 明确工程动作会落到 `single_tool` 或 `workflow`

如果响应里拿到了 `run_id`，可以继续访问：

- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/chat/runs/{run_id}/cancel`

## 如何使用显式任务接口

### 项目问答

- 接口：`POST /api/v1/tasks/project-qa`
- 关键 payload：
  - `user_query`
  - `domain_filters`

### 代码审查

- 接口：`POST /api/v1/tasks/code-review`
- 关键 payload：
  - `diff_text`

### 代码生成

- 接口：`POST /api/v1/tasks/code-generate`
- 当前返回代码草稿和 patch plan，不会直接写文件

### 日志分析

- 接口：`POST /api/v1/tasks/logs-analyze`
- 关键 payload：
  - `log_text`

### 配置生成

- 接口：`POST /api/v1/tasks/config-generate`
- 当前会生成草稿、校验结果和 Proposal
- 任务状态会进入 `waiting_confirmation`

### 配置校验

- 接口：`POST /api/v1/tasks/config-validate`
- 关键 payload：
  - `schema`
  - `config_json`

### 资产检查

- 接口：`POST /api/v1/tasks/assets-inspect`
- 关键上下文：
  - `context.selected_assets`

### 性能分析

- 接口：`POST /api/v1/tasks/perf-analyze`
- 关键 payload：
  - `report_text`
  - 可选 `insights_summary`

## Proposal 与审批怎么用

### 查看待审批 Proposal

- `GET /api/v1/proposals/pending`

### 查看单个 Proposal 详情

- `GET /api/v1/proposals/{proposal_id}`

### 提交决策

```json
{
  "decision": "confirmed",
  "actor": "tester",
  "comment": "Looks good.",
  "metadata": {}
}
```

或：

```json
{
  "decision": "rejected",
  "actor": "tester",
  "comment": "Need another revision."
}
```

决策提交后：

- Proposal 状态会变成 `confirmed` 或 `rejected`
- 对应任务会从 `waiting_confirmation` 变成：
  - `completed`
  - 或 `cancelled`

## 如何查看 Artifact、Trace、SSE 和 Metrics

### Artifact

- `GET /api/v1/tasks/{task_id}/artifacts`

### Trace

- `GET /api/v1/tasks/{task_id}/trace`

### SSE 事件回放

- `GET /api/v1/chat/runs/{run_id}/events/stream`

### Metrics

- `GET /metrics`
- 当前会输出：
  - `agent_tasks_total`
  - `agent_proposals_pending_total`
  - `agent_proposal_decisions_total`
  - `agent_audit_logs_total`
  - `agent_waiting_confirmation_total`

## 如何做评测与回归

### RAG 评测

```bash
python scripts/run_rag_eval.py --dataset tests/eval/rag_project_qa_dataset.jsonl
```

### 多能力任务评测

```bash
python scripts/run_task_eval.py
```

### 一键回归

```bash
python scripts/run_regression_suite.py
```

## 如何做知识库维护

### 重建索引

- `POST /api/v1/knowledge-base/reindex`

### 重试导入任务

- `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry`

### 查看文档列表

- `GET /api/v1/knowledge-base/documents`

### 查看单文档详情

- `GET /api/v1/knowledge-base/documents/{doc_id}`

### 删除文档

- `DELETE /api/v1/knowledge-base/documents/{doc_id}`

## 前端应该读取哪些字段

- 用户展示：
  - `user_view.title`
  - `user_view.text`
  - `user_view.blocks`
  - `user_view.citations_preview`
  - `user_view.quick_actions`
  - `user_view.status_hint`
- 调试展示：
  - `debug_view.intent`
  - `debug_view.route`
  - `debug_view.retrieval`
  - `debug_view.retrieval_summary`
  - `debug_view.tools`
  - `debug_view.step_results`
  - `debug_view.metrics`
  - `debug_view.session_summary`
  - `debug_view.memory_summary`
  - `debug_view.output_complete`
  - `debug_view.finish_reason`
  - `debug_view.raw_result`
  - `debug_view.artifacts`
  - `trace_summary`
- 语言相关：
  - `locale.detected_input_language`
  - `locale.final_output_language`

## 切换模型和 RAG 模式

- 切换聊天模型：
  - 修改 `CHAT_MODEL`
- 切换 embedding 模型：
  - 修改 `EMBEDDING_MODEL`
- 切换 RAG 模式：
  - 修改 `RAG_MODE`
- 强制关闭 embedding：
  - 设置 `EMBEDDING_ENABLED=false`
- 切换 Profile：
  - 使用 `POST /api/v1/system/runtime-profiles/{profile_id}/activate`

修改 `.env` 后请重启服务。

## 常见问题

### 1. `knowledge-base/status` 显示空库

- 先执行 `POST /api/v1/knowledge-base/refresh`
- 检查 `KB_SOURCE_PATHS`
- 检查导入任务返回的 `job.stats.failures`

### 2. 为什么 `config-generate` 返回的是 `waiting_confirmation`

- 这是 Phase 4 的正式行为
- 当前草稿已生成，但后续采用动作需要人工确认

### 3. 为什么 `code-generate` 没有直接改工程文件

- 当前仍是计划型能力
- 只返回代码草稿、文件建议和 patch plan

### 4. 为什么 `/metrics` 里看不到很多指标

- 当前实现优先覆盖任务、Proposal、审计等核心 Phase 4 指标
- 还没有接入完整的长生命周期 Prometheus client

### 5. 本地 SQLite 报 `disk I/O error`

- 这是当前沙箱环境下的已知问题
- 自动化验证可临时使用 `sqlite+pysqlite:///:memory:`
- 正式本地开发仍建议保留默认文件型 SQLite

### 6. 当前 LangSmith 是真实远端 trace 吗

- 目前是“接口契约已落地，本地 stub 元数据可见”
- `trace_summary` 已包含 `provider`、`langsmith_enabled`、`langsmith_project`
- 远端真实上报仍可在后续真实环境继续接入
