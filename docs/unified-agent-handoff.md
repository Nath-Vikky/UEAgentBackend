# 统一 Agent 交接文档

当前文档对应 Phase 4，说明统一聊天入口如何区分日常对话、项目问答和工程任务。

## 入口

- `POST /api/v1/chat/runs`

## 路由结果类型

- `direct_answer`
  - 无工程上下文、无任务动作信号
- `project_qa`
  - 命中文档、接口、规范、工程说明
- `single_tool`
  - 明确只读校验或计划型单工具任务
- `workflow`
  - 多步任务、带检索、带步骤结果、可能产出 Proposal

## 当前路由信号

- `context.active_panel`
- `context.current_file`
- `context.current_module`
- `context.selected_assets`
- `payload.user_query`
- 明确动作词：
  - `review`
  - `analyze`
  - `generate`
  - `validate`
  - `inspect`
  - `perf`

## 前端怎么用

### 自由输入聊天面板

- 统一走 `POST /api/v1/chat/runs`
- 不需要前端先判断任务类型

### 确定性面板

- 如果前端已经明确是代码审查、配置生成等面板
- 更推荐走显式任务接口

## 响应里要看哪些字段

- `intent.intent_type`
- `intent.route_type`
- `intent.reason`
- `planner_diagnostics`
- `task.task_type`
- `task.status`

## 当前 Phase 4 的重要行为

- 统一聊天入口已经可以直接命中 `config_generate`
- 当结果包含待确认 Proposal 时：
  - `task.status = waiting_confirmation`
  - `action_proposals[*].confirmation.state = pending`

## 统一聊天后的后续动作

- 看结果：
  - `GET /api/v1/chat/runs/{run_id}`
- 看事件：
  - `GET /api/v1/chat/runs/{run_id}/events/stream`
- 取消等待中的 run：
  - `POST /api/v1/chat/runs/{run_id}/cancel`
