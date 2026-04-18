# Proposal 与审批交接文档

当前文档对应 Phase 4，面向前端同学，说明待确认卡片字段、确认接口和状态流转。

## Proposal 字段

响应中的 Proposal 结构：

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

## 当前会进入审批等待的能力

- `config_generate`

当前行为：

- 任务返回后：
  - `task.status = waiting_confirmation`
  - Proposal 状态为 `pending`

## 待审批列表

- `GET /api/v1/proposals/pending`

适合用在：

- 待确认抽屉
- 独立审批面板
- 页面刷新后的恢复显示

## Proposal 详情

- `GET /api/v1/proposals/{proposal_id}`

返回：

- `item`
- `task`
- `decisions`

## 提交决策

- `POST /api/v1/proposals/{proposal_id}/decision`

请求体：

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

## 决策后的状态流转

### `confirmed`

- Proposal：
  - `confirmation.state = confirmed`
- Task：
  - `status = completed`
  - `finish_reason = proposal_confirmed`

### `rejected`

- Proposal：
  - `confirmation.state = rejected`
- Task：
  - `status = cancelled`
  - `finish_reason = proposal_rejected`

## 前端建议流程

1. 用户触发任务。
2. 如果 `task.status = waiting_confirmation`，展示 Proposal 卡片。
3. 用户点击确认或拒绝。
4. 调决策接口。
5. 再刷新：
   - `GET /api/v1/tasks/{task_id}`
   - 或 `GET /api/v1/proposals/{proposal_id}`

## 调试字段联动

审批流里推荐一起看：

- `task.status`
- `task.finish_reason`
- `action_proposals`
- `trace_summary`
- `debug_view.finish_reason`
- `debug_view.output_complete`
