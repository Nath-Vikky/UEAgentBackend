# 前端面板接入文档

当前文档对应 Phase 3，面向 UE 前端面板开发。目标是把“哪个面板调哪个接口、用户态和调试态各显示什么”讲清楚。

## 建议初始化流程

1. 调 `GET /api/v1/system/bootstrap`
2. 调 `GET /api/v1/system/capabilities`
3. 调 `GET /api/v1/system/runtime-profiles`
4. 调 `GET /api/v1/knowledge-base/status`

## 面板与接口映射

### CodeReview

- 接口：`POST /api/v1/tasks/code-review`
- 关键上下文：
  - `context.current_file`
  - `context.current_module`
- 关键 payload：
  - `diff_text`

### CodeGenerator

- 接口：`POST /api/v1/tasks/code-generate`
- 关键 payload：
  - `requirement_description`
  - `target_type`

### LogAnalyzer

- 接口：`POST /api/v1/tasks/logs-analyze`
- 关键 payload：
  - `log_text`

### ConfigGenerator

- 接口：`POST /api/v1/tasks/config-generate`
- 关键 payload：
  - `requirement_description`
  - `object_type`
  - `schema`

### ConfigValidator

- 接口：`POST /api/v1/tasks/config-validate`
- 关键 payload：
  - `schema`
  - `config_json`

### AssetInspector

- 接口：`POST /api/v1/tasks/assets-inspect`
- 关键上下文：
  - `context.selected_assets`

### PerfAnalysis

- 接口：`POST /api/v1/tasks/perf-analyze`
- 关键 payload：
  - `report_text`
  - `insights_summary`

## User View 渲染建议

### 通用字段

- `user_view.title`
- `user_view.text`
- `user_view.blocks`
- `user_view.citations_preview`
- `user_view.quick_actions`
- `user_view.status_hint`

### 面板推荐重点

- CodeReview：
  - `summary` 块
  - `list` 块
  - `citations_preview`
- CodeGenerator：
  - `list` 块
  - `quick_actions`
- LogAnalyzer：
  - `summary` 块
  - `list` 块
- ConfigGenerator：
  - `summary` 块
  - `json_preview` 块
- ConfigValidator：
  - `summary` 块
- AssetInspector：
  - `summary` 块
  - `list` 块
- PerfAnalysis：
  - `summary` 块
  - `list` 块

## Debug View 渲染建议

建议所有面板都支持以下区域：

- 路由诊断：
  - `debug_view.intent`
  - `debug_view.route`
- 检索诊断：
  - `debug_view.retrieval`
- 工具执行：
  - `debug_view.tools`
- 步骤明细：
  - `debug_view.step_results`
- 原始结构化结果：
  - `debug_view.raw_result`
- 产物信息：
  - `debug_view.artifacts`
- Trace 入口：
  - `trace_summary`

## Artifact 面板建议

任务响应成功后，如果存在 Artifact，前端应提供“查看产物”入口。

推荐流程：

1. 从响应里拿 `task.task_id`
2. 调 `GET /api/v1/tasks/{task_id}/artifacts`
3. 使用返回的 `label`、`artifact_type`、`path` 构建产物列表

## Trace / Event 面板建议

推荐流程：

1. 从响应里拿 `task.run_id`
2. 调 `GET /api/v1/chat/runs/{run_id}/events/stream`
3. 把事件按 `seq` 和 `timestamp` 排序展示

当前 SSE 是事件回放，适合：

- 调试链路回看
- 任务步骤面板
- Demo 过程展示

## 状态处理建议

### 检索降级

- 当 `retrieval_trace.degraded_mode=true`
- 在调试面板展示“当前为降级检索”

### 低置信度

- 当 `data.confidence < 0.4`
- 高亮 `quick_actions`

### 有 Proposal

- 当 `action_proposals` 非空
- 渲染 Proposal 卡片
- 当前阶段按“建议动作”展示，不做最终执行确认

### 有 Warning

- 当 `debug_view.warnings` 非空
- 在调试面板高亮

## 面板实现原则

- 用户面只消费 `user_view`
- 调试面只消费 `debug_view`、`trace_summary` 和 `step_results`
- 不要用 `data` 直接拼用户主文案
- 不要假设所有任务都会返回 citation
- `code-generate` 和 `config-generate` 目前都属于非破坏性能力
