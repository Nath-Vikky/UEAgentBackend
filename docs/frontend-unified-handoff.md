# UE Frontend Unified Handoff

## 1. 这份文档怎么用

这份文档是 UE 前端从零开始联调后端时的统一入口。

前端优先阅读这一份即可。只有在需要补充类型定义或 UE 插件侧说明时，再额外查看：

- `forward.md`
- `app/schemas/requests.py`
- `app/schemas/responses.py`
- `app/schemas/common.py`

核心约束：

- 所有接口统一走 `/api/v1/*`
- 用户主界面只消费 `user_view`
- 调试界面只消费 `debug_view`
- 不要自己根据 `data` 重新拼主展示文案
- 不要在前端复刻一套“文本路由器”

## 2. 当前后端能力状态

当前后端已经可以进入 UE 前端联调阶段，下面这些能力都可用：

- `/api/v1/system/*` 启动探活、能力、配置、运行时 profile
- `/api/v1/chat/runs` 统一聊天入口
- `/api/v1/tasks/*` 显式任务入口
- `user_view` / `debug_view` 双视图
- Proposal 审批流
- `config_generate` 确认后产生产物
- `GET /api/v1/chat/runs/{run_id}/events/stream` 事件回放
- `GET /metrics` 和 `GET /api/v1/system/alerts` 调试/运维接口

## 3. 前端启动顺序

建议启动后按这个顺序调用：

1. `GET /api/v1/system/health`
2. `GET /api/v1/system/bootstrap`
3. `GET /api/v1/system/capabilities`
4. `GET /api/v1/system/runtime-profiles`
5. `GET /api/v1/knowledge-base/status`

前端拿到这些信息后即可初始化：

- 服务是否可用
- 默认 profile
- 能力开关
- Knowledge Base 状态
- 调试面板基础信息

## 4. 主要接口

### 4.1 统一聊天

- `POST /api/v1/chat/runs`
- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/user-view`
- `GET /api/v1/chat/runs/{run_id}/debug-view`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/chat/runs/{run_id}/cancel`

### 4.2 显式任务

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

### 4.3 Proposal

- `GET /api/v1/proposals/pending`
- `GET /api/v1/proposals/{proposal_id}`
- `POST /api/v1/proposals/{proposal_id}/decision`
- `GET /api/v1/proposals/decisions/{decision_id}`

### 4.4 系统与运维

- `GET /api/v1/system/settings`
- `GET /api/v1/system/alerts`
- `GET /metrics`

## 5. Agent Chat 路由规则

`POST /api/v1/chat/runs` 当前会落到四种主路径：

- `direct_answer`
- `project_qa`
- `single_tool`
- `workflow`

前端需要看这几个字段：

- `intent.route_type`
- `task.task_type`
- `task.status`
- `task.finish_reason`

### 5.1 这次路由策略的关键调整

现在后端不会再因为“带了项目上下文”就直接强制走知识库问答。

新的规则是：

- 显式任务类型仍然优先
  - 例如 `task_type=project_qa`、`code_review`、`config_generate`
- 明确工具/工程动作信号仍然优先
  - 例如 review、analyze、generate config、validate config
- 明确项目问答信号会走 `project_qa`
  - 例如问题直接提到“这个文件 / 当前模块 / 当前项目 / 项目文档 / 知识库 / backend.md”
  - 或显式传了 `domain_filters` / `kb_domains_hint`
- 只有弱上下文时，默认先走 `direct_answer`
  - 例如前端带了 `project_name`、`current_file`，但用户其实只是在问通用知识
- 如果场景模糊且后端已配置可用 LLM，后端会做一次 LLM 路由复核
  - LLM 只在“弱上下文 + 非工具任务”的模糊聊天场景下参与
  - 它只负责在 `direct_answer` 和 `project_qa` 之间二选一
  - 它不会替代显式任务路由

### 5.2 前端需要怎么配合

前端应继续把真实上下文如实传给后端，包括：

- `project_name`
- `current_file`
- `current_module`
- `selected_assets`
- `recent_open_files`
- `kb_domains_hint`

但前端不要为了“想要自由聊天”而故意删上下文，也不要自己在本地根据文本做二次路由。

一句话原则：

- 前端负责提供真实上下文
- 后端负责判断这次应该自由聊天还是检索知识后回答

### 5.3 新的调试字段

为了让前端和调试面板更容易理解路由结果，`debug_view.route` 现在可以包含这些字段：

- `decision_source`
  - 例如 `explicit_task_type`、`heuristic_strong_project_signal`、`heuristic_weak_project_signal`、`llm_route_judge`
- `project_signal_strength`
  - `strong` / `weak` / `none`
- `context_present`
- `project_hint_count`
- `context_reference_present`
- `explicit_kb_scope`
- `llm_route_decision`
  - 仅在 LLM 参与模糊路由复核时出现
  - 包含 `status`、`route_type`、`confidence`、`reason`、`model`、`profile_id`

这些字段主要给调试界面使用，不要求用户主界面展示。

## 6. 双视图消费规则

### 6.1 User View

用户主界面只读这些字段：

- `user_view.title`
- `user_view.text`
- `user_view.blocks`
- `user_view.citations_preview`
- `user_view.quick_actions`
- `user_view.status_hint`

兜底字段：

- `presentation.user_title`
- `presentation.user_text`

### 6.2 Debug View

调试界面建议展示：

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

## 7. 当前新增但不破坏前端的字段变化

这几轮后端改动都是增量增强，不是 breaking change。

### 7.1 `direct_answer` 已接真实 LLM

当后端配置了可用 LLM：

- `direct_answer` 不再返回占位文本
- `data.answer_generation.mode = live_llm`
- `debug_view.tools[*].tool_id` 会出现 `llm_direct_answer`

当 LLM 不可用：

- 仍返回结构化结果
- 路由仍是 `direct_answer`
- `data.answer_generation.mode = degraded_fallback`
- `debug_view.warnings` 会带降级原因

### 7.2 `project_qa` 可能是 LLM 综合回答

项目问答仍保留：

- `citations`
- `citations_preview`
- `retrieval_trace`
- `confidence`

新增：

- `data.answer_generation.mode`
  - `llm_synthesized`
  - `retrieval_summary_fallback`

### 7.3 Proposal 确认后会产生产物

以 `config_generate` 为例，用户确认 Proposal 后：

- `task.status = completed`
- `task.finish_reason = proposal_confirmed`
- `data.approval_result` 会出现
- `user_view.status_hint = approved`
- `/api/v1/tasks/{task_id}/artifacts` 会新增 `approved_config`
- `events/stream` 会新增 `proposal_followup_completed`

拒绝时：

- `task.status = cancelled`
- `task.finish_reason = proposal_rejected`
- `data.approval_result.decision = rejected`
- `user_view.status_hint = rejected`

## 8. Proposal 流程

推荐流程：

1. 触发任务或统一聊天
2. 如果 `task.status = waiting_confirmation`，展示 Proposal 卡片
3. 用户点击确认或拒绝
4. 调 `POST /api/v1/proposals/{proposal_id}/decision`
5. 重新拉取：
   - `GET /api/v1/tasks/{task_id}`
   - 或 `GET /api/v1/proposals/{proposal_id}`
6. 如需看产物，再调：
   - `GET /api/v1/tasks/{task_id}/artifacts`

Proposal 卡片建议直接消费这些字段：

- `proposal_id`
- `title`
- `proposal_type`
- `before_summary`
- `after_summary`
- `rationale`
- `risk_flags`
- `dry_run_preview`
- `display_hints`
- `requires_confirmation`
- `confirmation.state`
- `confirmation.decision_endpoint`

## 9. SSE / 轮询规则

`GET /api/v1/chat/runs/{run_id}/events/stream` 当前是事件回放接口，适合：

- 回看任务过程
- 刷新后的恢复显示
- 调试面板事件时间线

它目前不是 token 级实时流，因此前端仍然要保留轮询/详情拉取能力。

推荐组合：

- 详情页：`GET /api/v1/tasks/{task_id}`
- 调试事件：`GET /api/v1/chat/runs/{run_id}/events/stream`
- 产物面板：`GET /api/v1/tasks/{task_id}/artifacts`

## 10. 最小状态机

前端至少支持这些任务状态：

- `completed`
- `waiting_confirmation`
- `cancelled`
- `failed`

常见 `finish_reason`：

- `completed`
- `waiting_confirmation`
- `proposal_confirmed`
- `proposal_rejected`
- `cancelled_by_user`
- `execution_error`

## 11. 错误处理建议

常见错误码：

- `task_not_found`
- `run_not_found`
- `profile_not_found`
- `proposal_not_found`
- `proposal_already_decided`
- `proposal_decision_not_found`
- `kb_job_not_found`
- `kb_document_not_found`
- `internal_error`

前端建议：

- 404 展示“资源不存在或已失效”
- 409 展示“Proposal 已处理”
- 500 展示“后端执行异常，请切到 Debug View 查看细节”

## 12. 当前仍保留的边界

- `events/stream` 仍是回放流，不是 token 实时流
- `trace_summary.provider` 目前仍是本地 trace 元数据，不代表远端 LangSmith 已真实接通
- `code_generate` 仍不会直接写入用户工程文件

这些边界不影响前端开始开发。

## 13. 需要交给前端的文件

如果只给前端一份后端说明文档，就给这一份：

- `docs/frontend-unified-handoff.md`

最小补充文件：

- `forward.md`
- `app/schemas/requests.py`
- `app/schemas/responses.py`
- `app/schemas/common.py`

如果前端还要自己起后端或排查联调问题，再补：

- `README.md`
- `docs/backend-user-guide.md`
- `docs/task-debugging-guide.md`

## 14. 一句话结论

前端现在可以按这份文档直接开始搭 UE 面板和联调。

这次关于聊天路由的后端改动不会破坏原有接口，只是把“自由聊天 vs 项目检索问答”的判断做得更合理，也把调试字段补全了。
