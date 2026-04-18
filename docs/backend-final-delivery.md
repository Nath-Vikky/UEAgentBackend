# 后端最终交付文档

## 一、当前交付范围

当前后端已经覆盖 `backend.md` 的 Phase 1 到 Phase 5，具备：

- 统一 `/api/v1/*` 接口体系
- 双视图响应契约：
  - `user_view`
  - `debug_view`
  - `presentation`
- 统一聊天入口与显式任务入口
- 项目问答 RAG
- 核心工程任务：
  - 代码审查
  - 代码生成草稿
  - 日志分析
  - 配置生成
  - 配置校验
  - 资产检查
  - 性能分析
- Proposal 审批闭环
- Artifact、Trace、SSE 事件回放
- 审计日志与 Prometheus 文本指标
- 多能力评测脚本与回归套件
- 知识库重建、导入重试、文档管理

## 二、接口总览

### 系统

- `GET /api/v1/system/health`
- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/capabilities`
- `GET /api/v1/system/settings`
- `GET /api/v1/system/runtime-profiles`
- `POST /api/v1/system/runtime-profiles/{profile_id}/activate`
- `POST /api/v1/system/runtime-profiles/{profile_id}/set-default`
- `GET /api/v1/system/alerts`

### 统一聊天

- `POST /api/v1/chat/runs`
- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/user-view`
- `GET /api/v1/chat/runs/{run_id}/debug-view`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/chat/runs/{run_id}/cancel`

### 任务

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

### Proposal

- `GET /api/v1/proposals/pending`
- `GET /api/v1/proposals/{proposal_id}`
- `POST /api/v1/proposals/{proposal_id}/decision`
- `GET /api/v1/proposals/decisions/{decision_id}`

### 知识库

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`
- `POST /api/v1/knowledge-base/import`
- `GET /api/v1/knowledge-base/import-jobs/{job_id}`
- `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry`
- `POST /api/v1/knowledge-base/reindex`
- `GET /api/v1/knowledge-base/documents`
- `GET /api/v1/knowledge-base/documents/{doc_id}`
- `DELETE /api/v1/knowledge-base/documents/{doc_id}`

### 监控

- `GET /metrics`

## 三、能力边界

### 已支持

- 只读分析
- 草稿生成
- 任务级审批等待
- 运行取消
- 知识库维护
- 本地评测与回归

### 当前未支持或仅为 stub

- 真实远端 LangSmith 上报
- 真实 OTel 导出
- 审批后的真实工程写入执行桥
- 多用户权限模型
- 生产级异步任务队列

## 四、部署方式

### 本地开发

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 建议前置条件

- Python 3.12 优先
- `.venv` 虚拟环境
- `.env` 完整配置

## 五、运维要点

- 通过 `knowledge-base/status` 检查知识库健康
- 通过 `tasks/{task_id}/trace` 和 `events/stream` 做任务回放
- 通过 `proposals/pending` 处理待审批积压
- 通过 `/metrics` 和 `/api/v1/system/alerts` 观察：
  - 失败率
  - P95 延迟
  - 每小时成本
  - RAG miss rate
  - KB 导入失败率
  - Proposal 积压

## 六、推荐验收入口

- 回归报告：
  - `storage/artifacts/regression/regression-suite-20260418T043008Z.json`
- RAG 评测报告：
  - `storage/artifacts/evals/rag-eval-20260418T043006Z.json`
- 多能力任务评测报告：
  - `storage/artifacts/evals/task-eval-20260418T043007Z.json`

## 七、交付结论

当前后端已经从“可运行 demo”推进到“可重复联调、可回归验证、可做项目演示和内部交接”的阶段。后续若进入真实项目落地，优先建议继续补：

- 审批后执行桥
- 真实 LangSmith / OTel 导出
- 更完整的生产部署与告警系统
