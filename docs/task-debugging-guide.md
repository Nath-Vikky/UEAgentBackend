# 任务调试手册

当前文档面向后端、前端和联调同学，说明如何手动构造请求、查看 Trace、定位任务失败和读取 Artifact。

## 1. 最小调试链路

建议按这个顺序排查：

1. 调任务接口，拿到 `task_id` 和 `run_id`
2. 看响应里的 `debug_view`
3. 调 `GET /api/v1/tasks/{task_id}/trace`
4. 调 `GET /api/v1/tasks/{task_id}/artifacts`
5. 调 `GET /api/v1/chat/runs/{run_id}/events/stream`
6. 必要时打开 `storage/artifacts/tasks/{task_id}/debug_snapshot.json`

## 2. 如何构造任务请求

### 通用原则

- `session.messages[-1].content` 要与 `payload.user_query` 保持一致
- `context.active_panel` 尽量传真实面板名
- 工程上下文字段尽量补齐：
  - `project_name`
  - `current_file`
  - `current_module`
  - `selected_assets`
- 调试阶段建议：
  - `runtime_options.debug = true`
  - `runtime_options.return_debug_projection = true`

### 常见必填字段

- 代码审查：
  - `payload.diff_text`
- 日志分析：
  - `payload.log_text`
- 配置生成：
  - `payload.requirement_description`
  - `payload.schema`
- 配置校验：
  - `payload.schema`
  - `payload.config_json`
- 资产检查：
  - `context.selected_assets`
- 性能分析：
  - `payload.report_text`

## 3. 先看哪些字段

### 路由是否正确

看：

- `intent.route_type`
- `debug_view.route`
- `planner_diagnostics`

### 语言是否正确

看：

- `locale.detected_input_language`
- `locale.final_output_language`
- `locale.language_source`

### 检索是否正确

看：

- `retrieval_trace`
- `debug_view.retrieval`
- `debug_view.warnings`

### 工具或工作流是否执行

看：

- `debug_view.tools`
- `debug_view.step_results`
- `step_results`

## 4. Trace 如何看

调用：

```text
GET /api/v1/tasks/{task_id}/trace
```

重点字段：

- `trace_summary`
- `step_results`
- `events`

当前常见事件类型：

- `run_started`
- `route_selected`
- `retrieval_started`
- `retrieval_completed`
- `step_started`
- `step_completed`
- `text_delta`
- `proposal_emitted`
- `run_completed`

## 5. SSE 如何看

调用：

```text
GET /api/v1/chat/runs/{run_id}/events/stream
```

说明：

- 当前实现是“事件回放”
- 适合在前端或调试工具里重放本次任务步骤
- 如果返回 404，先确认 `run_id` 是否来自这次任务响应

## 6. Artifact 如何看

调用：

```text
GET /api/v1/tasks/{task_id}/artifacts
```

返回中重点字段：

- `artifact_id`
- `artifact_type`
- `label`
- `path`

也可以直接看：

```text
storage/artifacts/tasks/{task_id}/
```

常见 Artifact：

- `code_draft.json`
- `config_validation_report.json`
- 资产检查报告
- 工作流结果 JSON

## 7. 失败定位建议

### 路由不符合预期

- 看 `context.active_panel` 是否正确
- 看 `payload.user_query` 是否包含明确动作词
- 看 `debug_view.route.candidate_tool_ids`

### 没有检索结果

- 看 `retrieval_trace.retrieved_docs`
- 看 `retrieval_trace.filters_applied`
- 看 `knowledge-base/status`

### 代码生成结果太空

- 看 `payload.requirement_description`
- 看 `payload.target_type`
- 看 `data.patch_plan`

### 配置校验没有命中错误

- 确认 `payload.config_json` 是对象
- 确认 `payload.schema` 是合法对象
- 看 `data.validation_summary.checked_fields`

### SSE 事件缺失

- 确认任务已完成并成功落库
- 确认使用了响应返回的 `run_id`

## 8. 本地文件调试入口

每个任务都会在本地生成调试快照：

```text
storage/artifacts/tasks/{task_id}/debug_snapshot.json
```

当接口响应已经结束、前端面板又无法复现场景时，优先看这个文件。

## 9. 当前阶段调试结论

- Phase 3 已具备稳定的任务级调试链路
- 最核心的排查入口是 `debug_view`、`trace`、`artifacts` 和 `events/stream`
- 如果问题来自真实执行动作缺失，不是 bug，而是当前阶段仍保持“非破坏性”的设计限制
