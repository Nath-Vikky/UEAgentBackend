# 任务接口交接文档

当前文档对应 `backend.md` 的 Phase 3，面向前端和联调同学，说明每个工程任务接口的最小请求体、关键返回字段和后续查询方式。

## 通用请求结构

所有任务接口都使用统一请求体：

```json
{
  "task_type": "code_review",
  "session": {
    "session_id": "demo_session",
    "messages": [
      {
        "role": "user",
        "content": "Review this Unreal diff.",
        "language": "auto"
      }
    ]
  },
  "context": {
    "project_name": "DemoProject",
    "active_panel": "CodeReview",
    "current_file": "Source/MyModule/MyActor.cpp",
    "current_module": "MyModule",
    "selected_assets": []
  },
  "payload": {
    "user_query": "Review this Unreal diff."
  },
  "ui_state": {
    "active_view": "user",
    "selected_panel": "CodeReview"
  },
  "runtime_options": {
    "profile_id": "default",
    "stream": false,
    "debug": true,
    "preferred_output_language": "auto",
    "return_debug_projection": true
  }
}
```

## 通用响应结构

所有任务都会返回：

- `task.task_id`
- `task.run_id`
- `task.task_type`
- `intent.route_type`
- `user_view`
- `debug_view`
- `data`
- `step_results`
- `retrieval_trace`
- `action_proposals`

可选的后续读取接口：

- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/trace`
- `GET /api/v1/tasks/{task_id}/artifacts`
- `GET /api/v1/chat/runs/{run_id}/events/stream`

## `POST /api/v1/tasks/code-review`

### 最关键请求字段

- `payload.diff_text`
- 可选 `context.current_file`
- 可选 `context.current_module`

### 关键返回字段

- `intent.route_type`
  - 固定为 `workflow`
- `data.issue_list`
- `data.severity_summary`
- `data.suggestions`
- `data.need_human_followup`
- `data.citations`
- `user_view.blocks`
- `debug_view.tools`
- `debug_view.step_results`

### 产物

- 审查结果 JSON

## `POST /api/v1/tasks/code-generate`

### 最关键请求字段

- `payload.requirement_description`
- 可选 `payload.target_type`

### 关键返回字段

- `intent.route_type`
  - 固定为 `single_tool`
- `data.code_draft`
- `data.file_structure_suggestions`
- `data.patch_plan`
- `data.assumptions`
- `data.known_risks`
- `action_proposals`

### 产物

- `code_draft.json`

### 注意

- 当前不会直接写入工程文件
- 前端应把它展示为草稿和建议，而不是已执行修改

## `POST /api/v1/tasks/logs-analyze`

### 最关键请求字段

- `payload.log_text`

### 关键返回字段

- `intent.route_type`
  - 固定为 `workflow`
- `data.summary`
- `data.findings`
- `data.issue_families`
- `data.suspected_causes`
- `data.structured_events`
- `data.parser_diagnostics`
- `data.citations`

### 产物

- 日志分析结果 JSON

## `POST /api/v1/tasks/config-generate`

### 最关键请求字段

- `payload.requirement_description`
- `payload.object_type`
- `payload.schema`

### 关键返回字段

- `intent.route_type`
  - 固定为 `workflow`
- `data.draft_config`
- `data.validation_results`
- `data.retrieved_references`
- `action_proposals`

### 产物

- 配置草稿 JSON

### 注意

- 当前阶段会产出 Proposal，但不会直接执行写入

## `POST /api/v1/tasks/config-validate`

### 最关键请求字段

- `payload.schema`
- `payload.config_json`

### 关键返回字段

- `intent.route_type`
  - 固定为 `single_tool`
- `data.errors`
- `data.warnings`
- `data.suggestions`
- `data.validation_summary`

### 产物

- `config_validation_report.json`

## `POST /api/v1/tasks/assets-inspect`

### 最关键请求字段

- `context.selected_assets`

### 关键返回字段

- `intent.route_type`
  - 固定为 `single_tool`
- `data.summary`
- `data.violations`
- `data.rename_suggestions`
- `data.duplicate_candidates`
- `data.citations`

### 产物

- `asset_inspection_report.json`

## `POST /api/v1/tasks/perf-analyze`

### 最关键请求字段

- `payload.report_text`
- 可选 `payload.insights_summary`

### 关键返回字段

- `intent.route_type`
  - 固定为 `workflow`
- `data.summary`
- `data.metric_summary`
- `data.suspicious_points`
- `data.optimization_suggestions`
- `data.citations`

### 产物

- 性能分析结果 JSON

## 返回字段消费建议

### 用户主界面

- 优先读取 `user_view`
- `user_view.blocks` 可按 `block_type` 分发
- `user_view.citations_preview` 只做轻量引用预览

### 调试界面

- 优先读取 `debug_view`
- 结构化原始结果看 `debug_view.raw_result`
- 检索与工具执行链看 `debug_view.retrieval`、`debug_view.tools`、`debug_view.step_results`

### 结果详情面板

- 用 `data` 渲染可展开的结构化详情
- 用 `action_proposals` 渲染 Proposal 卡片
- 用 `artifacts` 或产物接口渲染下载/查看入口
