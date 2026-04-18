# 后端接口基础契约文档

## 顶层稳定字段

所有统一任务响应都包含：

- `success`
- `task`
- `intent`
- `locale`
- `user_view`
- `debug_view`
- `presentation`
- `assistant_message`
- `data`
- `usage`
- `trace_summary`
- `retrieval_trace`
- `planner_diagnostics`
- `step_results`
- `action_proposals`
- `errors`

## 当前已实现接口

### System

- `GET /api/v1/system/health`
- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/capabilities`
- `GET /api/v1/system/settings`
- `GET /api/v1/system/runtime-profiles`
- `POST /api/v1/system/runtime-profiles/{id}/activate`
- `POST /api/v1/system/runtime-profiles/{id}/set-default`

### Tasks

- `POST /api/v1/tasks/project-qa`
- `GET /api/v1/tasks/recent`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/user-view`
- `GET /api/v1/tasks/{task_id}/debug-view`
- `GET /api/v1/tasks/{task_id}/trace`

### Chat Runs

- `POST /api/v1/chat/runs`
- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/user-view`
- `GET /api/v1/chat/runs/{run_id}/debug-view`

### KB / Proposal

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`
- `GET /api/v1/proposals/pending`

## 当前接口语义

- Phase 1 目标是先稳定契约，不是交付完整能力。
- 所有任务类接口都已落库，并能查询双视图和调试快照。
- `errors[]` 始终作为统一错误容器返回。

