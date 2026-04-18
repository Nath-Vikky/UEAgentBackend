# Phase 3 演示说明

当前文档给出 4 组可重复的 Phase 3 演示用例，目标是覆盖多步工作流、单工具能力、Artifact 和调试链路。

## 演示前准备

1. 启动后端服务。
2. 调 `GET /api/v1/system/bootstrap` 确认服务正常。
3. 调 `POST /api/v1/knowledge-base/refresh` 刷新默认知识源。
4. 准备可以展示 `user_view`、`debug_view`、`artifacts`、`events` 的前端面板或 API 客户端。

## Demo 1：代码审查工作流

### 请求

- 接口：`POST /api/v1/tasks/code-review`
- 核心 payload：

```json
{
  "payload": {
    "user_query": "Review this Unreal diff for lifetime and loading issues.",
    "diff_text": "@@\n+ UObject* RawAsset = nullptr;\n+ virtual void Tick(float DeltaTime) override;\n+ auto Asset = LoadObject<UObject>(nullptr, TEXT(\"/Game/Hero/Hero01\"));\n"
  }
}
```

### 预期结果

- `intent.route_type = workflow`
- `data.issue_list` 非空
- `data.severity_summary` 可展示
- `GET /api/v1/tasks/{task_id}/artifacts` 有结果
- `GET /api/v1/chat/runs/{run_id}/events/stream` 至少能看到：
  - `run_started`
  - `route_selected`
  - `step_completed`

## Demo 2：日志分析工作流

### 请求

- 接口：`POST /api/v1/tasks/logs-analyze`
- 核心 payload：

```json
{
  "payload": {
    "user_query": "Analyze this crash log.",
    "log_text": "[2026.04.17-10.00.00] LogTemp: Error: Access violation\nCallstack: 0x0001 Demo!MyModule\nLogStreaming: Warning: Failed to load /Game/Maps/TestMap"
  }
}
```

### 预期结果

- `intent.route_type = workflow`
- `data.findings` 非空
- `data.structured_events` 非空
- `data.parser_diagnostics` 有结构化字段

## Demo 3：配置生成与 Proposal

### 请求

- 接口：`POST /api/v1/tasks/config-generate`
- 核心 payload：

```json
{
  "payload": {
    "user_query": "Generate a character spawn config.",
    "requirement_description": "Spawn the default hero with an enabled state.",
    "object_type": "HeroSpawnConfig",
    "schema": {
      "type": "object",
      "required": ["name", "enabled"],
      "properties": {
        "name": { "type": "string" },
        "enabled": { "type": "boolean" },
        "count": { "type": "integer", "minimum": 0 }
      }
    }
  }
}
```

### 预期结果

- `intent.route_type = workflow`
- `data.draft_config` 非空
- `data.validation_results` 存在
- `action_proposals` 非空
- `artifacts` 非空

## Demo 4：性能分析工作流

### 请求

- 接口：`POST /api/v1/tasks/perf-analyze`
- 核心 payload：

```json
{
  "payload": {
    "user_query": "Analyze this frame hitch report.",
    "report_text": "FrameTime: 41.2 ms\nGameThread: 21.5 ms\nDrawCalls: 4200\nPeak Memory: 3072 MB",
    "insights_summary": "Streaming spikes and synchronous loading were observed during the hitch."
  }
}
```

### 预期结果

- `intent.route_type = workflow`
- `data.metric_summary.peak_frame_time_ms` 存在
- `data.suspicious_points` 非空
- `data.optimization_suggestions` 非空

## 可选 Demo 5：代码生成草稿

### 请求

- 接口：`POST /api/v1/tasks/code-generate`

### 预期结果

- `intent.route_type = single_tool`
- `data.code_draft` 非空
- `data.file_structure_suggestions` 非空
- `action_proposals` 非空
- Artifact 中能看到 `code_draft.json`

## 演示讲解重点

- 统一任务响应结构已经稳定
- `user_view` 和 `debug_view` 可以并行服务用户面和调试面
- 每个任务都会回传 `task_id` / `run_id`
- Artifact、Trace、SSE 已具备基本演示能力
- Phase 3 仍坚持“非破坏性”，把真正写入留给后续审批阶段
