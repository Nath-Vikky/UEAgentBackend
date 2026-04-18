# Debug 视图字段说明文档

当前文档对应 Phase 4，整理 `debug_view`、`trace_summary` 和相关调试字段的含义。

## `debug_view` 字段

### 请求与归一化

- `raw_request`
  - 脱敏后的原始请求
- `normalized_request`
  - 标准化后的完整请求体

### 路由与意图

- `intent`
  - 意图识别结果
- `route`
  - 路由与规划信息

### 检索

- `retrieval`
  - 详细检索链路
- `retrieval_summary`
  - 轻量摘要：
    - `mode`
    - `retrieved_count`
    - `degraded_mode`

### 工具与步骤

- `tools`
  - 工具调用列表
- `step_results`
  - 多步执行结果

### 结果与产物

- `raw_result`
  - 原始结构化结果
- `artifacts`
  - 任务产物列表

### Trace 与运行信息

- `trace_links`
  - Trace 跳转信息
- `metrics`
  - 当前运行的轻量指标：
    - `latency_ms`
    - `estimated_cost_usd`
    - `input_tokens`
    - `output_tokens`
- `session_summary`
  - 当前会话摘要
- `memory_summary`
  - 当前响应相关的轻量内存/物料摘要
- `output_complete`
  - 当前响应是否完整可展示
- `finish_reason`
  - 本次任务结束原因
- `warnings`
  - 调试警告

## `trace_summary` 字段

- `trace_id`
- `route_type`
- `final_status`
- `finish_reason`
- `provider`
- `langsmith_enabled`
- `langsmith_project`

## 当前 `provider` 说明

- 当前本地实现会返回：
  - `langsmith_stub`
  - 或 `local_trace`

含义是：

- Phase 4 已经把 trace 契约和观测字段落地
- 但远端 LangSmith 实际上报仍未在本地环境完成

## 最小调试组合建议

如果前端只能展示一小部分，优先展示：

- `intent`
- `route`
- `retrieval_summary`
- `tools`
- `step_results`
- `metrics`
- `output_complete`
- `finish_reason`
- `trace_summary`
