# UE Agent Backend 运维说明

当前文档覆盖到 Phase 4：服务启动、数据库迁移、知识库维护、任务 Artifact、Proposal 审批、审计记录、事件回放和 `/metrics`。

## 运行形态

- 服务：FastAPI + Uvicorn
- 本地数据库：SQLite
- ORM / 迁移：SQLAlchemy 2.x + Alembic
- 知识库存储：
  - `storage/kb/raw/`
  - `storage/kb/normalized/`
  - `storage/kb/failed/`
- 任务调试快照：
  - `storage/artifacts/tasks/{task_id}/debug_snapshot.json`
- 任务产物目录：
  - `storage/artifacts/tasks/{task_id}/`
- Prometheus 文本指标：
  - `GET /metrics`

## 关键目录

- `storage/app.db`
- `storage/artifacts/tasks/`
- `storage/artifacts/evals/`
- `storage/kb/raw/`
- `storage/kb/normalized/`
- `storage/kb/failed/`

## 初始化与恢复

### 初始化

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 知识库重刷

- 默认刷新：
  - `POST /api/v1/knowledge-base/refresh`
- 自定义源：
  - `POST /api/v1/knowledge-base/refresh` 并传 `source_paths`

### 本地数据库重建

仅在本地开发环境使用：

1. 停服务。
2. 删除 `storage/app.db`。
3. 重新执行 `alembic upgrade head`。
4. 重新刷新知识库。

## Phase 4 运维面

### 重点接口

- `GET /api/v1/tasks/recent`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/trace`
- `GET /api/v1/tasks/{task_id}/artifacts`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/chat/runs/{run_id}/cancel`
- `GET /api/v1/proposals/pending`
- `POST /api/v1/proposals/{proposal_id}/decision`
- `GET /metrics`

### 核心观测内容

- 任务主记录：
  - 状态、任务类型、run_id、trace_id、finish_reason
- 任务事件：
  - 路由选择、检索开始/结束、步骤完成、Proposal 发射、运行取消
- 任务产物：
  - 代码草稿
  - 配置校验报告
  - 资产检查报告
  - 工作流输出 JSON
- 审计日志：
  - `task_persisted`
  - `proposal_emitted`
  - `proposal_decision_recorded`
  - `run_cancelled`

## 如何检查 waiting_confirmation

### 待审批 Proposal

- 调 `GET /api/v1/proposals/pending`

### 关联任务

- 调 `GET /api/v1/proposals/{proposal_id}`
- 看返回中的 `task.status`

### 决策后状态验证

- 决策提交后重新调：
  - `GET /api/v1/tasks/{task_id}`
  - `GET /api/v1/proposals/{proposal_id}`

## Trace、SSE 与 Artifact

### Trace

- `GET /api/v1/tasks/{task_id}/trace`

### SSE 事件回放

- `GET /api/v1/chat/runs/{run_id}/events/stream`
- 当前常见事件：
  - `run_started`
  - `route_selected`
  - `retrieval_started`
  - `retrieval_completed`
  - `step_started`
  - `step_completed`
  - `proposal_emitted`
  - `run_completed`
  - `run_cancelled`

### Artifact

- `GET /api/v1/tasks/{task_id}/artifacts`
- 或直接进入：
  - `storage/artifacts/tasks/{task_id}/`

## `/metrics` 运维建议

当前指标包括：

- `agent_tasks_total`
- `agent_proposals_pending_total`
- `agent_proposal_decisions_total`
- `agent_audit_logs_total`
- `agent_waiting_confirmation_total`

适合先做：

- 待审批积压观察
- 审批通过/拒绝趋势观察
- 任务状态分布观察
- 审计事件增量观察

## `/api/v1/system/alerts` 运维建议

- 用于给本地运维面板或前端调试面板直接消费告警快照
- 当前会给出：
  - 错误率
  - P95 延迟
  - 每小时成本
  - RAG miss rate
  - KB 导入失败率
  - Proposal 积压数量
  - Proposal 最长等待时间

## 回归与验收脚本

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

## 知识库维护接口

- 重建索引：
  - `POST /api/v1/knowledge-base/reindex`
- 导入任务重试：
  - `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry`
- 文档列表：
  - `GET /api/v1/knowledge-base/documents`
- 文档详情：
  - `GET /api/v1/knowledge-base/documents/{doc_id}`
- 文档删除：
  - `DELETE /api/v1/knowledge-base/documents/{doc_id}`

## 降级与故障判断

### 观察点

- `GET /api/v1/knowledge-base/status`
- `debug_view.retrieval`
- `trace_summary`
- `storage/artifacts/tasks/{task_id}/debug_snapshot.json`
- `/metrics`

### 常见状态

- `degraded_mode=true`
  - 当前没有完整走向量检索
- `mode=lexical_only`
  - embedding 不可用或主动切到 lexical
- `mode=local_hybrid_fallback`
  - hybrid 配置下向量能力不可用，已切到本地混合兜底
- `task.status=waiting_confirmation`
  - 响应已经生成，后续动作待确认
- `task.status=cancelled`
  - 用户取消或 Proposal 被拒绝

## 当前已知问题

- 当前终端沙箱内，文件型 SQLite 可能触发 `disk I/O error`
- `direct_answer` 现在会优先走已配置的在线 LLM；如果 LLM 不可用，会返回结构化降级回复
- 资产计划/资产执行还没有进入完整审批执行桥
- `LangSmith` 与 `OTel` 仍是本地 stub 元数据，不是远端真实链路
- `/metrics` 目前是文本聚合输出，不是完整 Prometheus client 生命周期集成
