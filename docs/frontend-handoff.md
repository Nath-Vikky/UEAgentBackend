# 前端联调整体交接文档

当前文档对应 `backend.md` 的 Phase 1 到 Phase 4。它给前端同学一个总览入口，具体专题请继续看：

- [unified-agent-handoff.md](./unified-agent-handoff.md)
- [proposal-approval-handoff.md](./proposal-approval-handoff.md)
- [debug-view-fields.md](./debug-view-fields.md)
- [model-and-profile-switching.md](./model-and-profile-switching.md)
- [task-interface-handoff.md](./task-interface-handoff.md)
- [frontend-panel-integration.md](./frontend-panel-integration.md)
- [task-debugging-guide.md](./task-debugging-guide.md)

## 建议启动顺序

1. `GET /api/v1/system/health`
2. `GET /api/v1/system/bootstrap`
3. `GET /api/v1/system/capabilities`
4. `GET /api/v1/system/runtime-profiles`
5. `GET /api/v1/knowledge-base/status`

## 当前交互模式

### 统一聊天入口

- `POST /api/v1/chat/runs`
- 用于统一承接：
  - `direct_answer`
  - `project_qa`
  - `single_tool`
  - `workflow`

### 显式任务入口

- `POST /api/v1/tasks/project-qa`
- `POST /api/v1/tasks/code-review`
- `POST /api/v1/tasks/code-generate`
- `POST /api/v1/tasks/logs-analyze`
- `POST /api/v1/tasks/config-generate`
- `POST /api/v1/tasks/config-validate`
- `POST /api/v1/tasks/assets-inspect`
- `POST /api/v1/tasks/perf-analyze`

前端如果已经知道当前面板对应的能力，建议优先调用显式任务接口。统一聊天入口更适合自由输入式交互。

## 当前新增的 Phase 4 后续动作

- 若响应里 `task.status = waiting_confirmation`
  - 前端应展示 Proposal 卡片或待确认入口
- 若持有 `run_id`
  - 可调用 `GET /api/v1/chat/runs/{run_id}/events/stream`
  - 可调用 `POST /api/v1/chat/runs/{run_id}/cancel`
- 若持有 `proposal_id`
  - 可调用 `GET /api/v1/proposals/{proposal_id}`
  - 可调用 `POST /api/v1/proposals/{proposal_id}/decision`

## User View 使用规则

前端只消费：

- `user_view.title`
- `user_view.text`
- `user_view.blocks`
- `user_view.citations_preview`
- `user_view.quick_actions`
- `user_view.status_hint`

兼容兜底：

- `presentation.user_title`
- `presentation.user_text`

不要直接拿 `data` 或 `debug_view` 拼用户主文案。

## Debug View 使用规则

建议调试面板展示：

- `debug_view.raw_request`
- `debug_view.normalized_request`
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
- `usage`

## 任务后续查询规则

每次成功响应都会带：

- `task.task_id`
- `task.run_id`

前端可以据此继续读取：

- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/trace`
- `GET /api/v1/tasks/{task_id}/artifacts`
- `GET /api/v1/chat/runs/{run_id}/events/stream`

## 联调注意事项

- 中文输入默认输出中文，英文输入默认输出英文
- 若用户显式要求“用英文回答 / 用中文回答”，后端会覆盖自动语言判定
- 当前 `config-generate` 已经支持真正的 `waiting_confirmation`
- 当前 `code-generate` 仍是非破坏性能力，不会直接改工程文件
- `trace_summary.provider` 当前是本地 stub 元数据，不代表远端链路已接通
