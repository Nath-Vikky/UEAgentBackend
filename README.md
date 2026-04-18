# UE Agent Backend

当前实现已经覆盖 `backend.md` 的 Phase 1 到 Phase 5：

- 后端骨架与统一 `/api/v1/*`
- 双视图契约与统一聊天入口
- 项目问答 RAG
- 核心工程任务与工作流
- Proposal 审批闭环、运行取消、Artifact、Trace、SSE
- 多能力评测、回归套件、知识库维护、告警快照与最终交付文档

## 当前可用能力

- 系统：
  - `/api/v1/system/*`
- 统一聊天：
  - `/api/v1/chat/runs*`
- 显式任务：
  - `/api/v1/tasks/*`
- Proposal：
  - `/api/v1/proposals/*`
- 知识库：
  - `/api/v1/knowledge-base/*`
- 监控：
  - `/metrics`

## 快速启动

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

首次联调建议顺序：

1. `GET /api/v1/system/health`
2. `GET /api/v1/system/bootstrap`
3. `GET /api/v1/system/capabilities`
4. `GET /api/v1/knowledge-base/status`
5. `POST /api/v1/knowledge-base/refresh`

## Phase 5 新增重点

- 评测脚本：
  - `python scripts/run_rag_eval.py --dataset tests/eval/rag_project_qa_dataset.jsonl`
  - `python scripts/run_task_eval.py`
- 回归套件：
  - `python scripts/run_regression_suite.py`
- 知识库维护：
  - `POST /api/v1/knowledge-base/reindex`
  - `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry`
  - `GET /api/v1/knowledge-base/documents`
  - `GET /api/v1/knowledge-base/documents/{doc_id}`
  - `DELETE /api/v1/knowledge-base/documents/{doc_id}`
- 告警快照：
  - `GET /api/v1/system/alerts`

## 验证命令

```bash
pytest -q -p no:cacheprovider
ruff check app tests scripts --no-cache
python scripts/run_regression_suite.py
```

## 最新报告

- RAG 评测：
  - `storage/artifacts/evals/rag-eval-20260418T043006Z.json`
- 多能力任务评测：
  - `storage/artifacts/evals/task-eval-20260418T043007Z.json`
- 回归套件：
  - `storage/artifacts/regression/regression-suite-20260418T043008Z.json`

## 文档索引

- [docs/backend-user-guide.md](./docs/backend-user-guide.md)
- [docs/backend-ops-guide.md](./docs/backend-ops-guide.md)
- [docs/backend-final-delivery.md](./docs/backend-final-delivery.md)
- [docs/frontend-final-package.md](./docs/frontend-final-package.md)
- [docs/frontend-unified-handoff.md](./docs/frontend-unified-handoff.md)
- [docs/evaluation-and-acceptance-report.md](./docs/evaluation-and-acceptance-report.md)
- [docs/version-changelog.md](./docs/version-changelog.md)
- [docs/frontend-handoff.md](./docs/frontend-handoff.md)
- [docs/unified-agent-handoff.md](./docs/unified-agent-handoff.md)
- [docs/proposal-approval-handoff.md](./docs/proposal-approval-handoff.md)
- [docs/debug-view-fields.md](./docs/debug-view-fields.md)
- [docs/model-and-profile-switching.md](./docs/model-and-profile-switching.md)
- [docs/task-interface-handoff.md](./docs/task-interface-handoff.md)
- [docs/frontend-panel-integration.md](./docs/frontend-panel-integration.md)
- [docs/task-debugging-guide.md](./docs/task-debugging-guide.md)
- [docs/backend-dev-log.md](./docs/backend-dev-log.md)
