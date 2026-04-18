# 模型与 Profile 切换说明文档

当前文档对应 Phase 4，说明如何切换聊天模型、embedding 模型、RAG 模式和运行时 Profile。

## 一、通过 `.env` 切换

### 聊天模型

- 修改 `CHAT_MODEL`

### Embedding 模型

- 修改 `EMBEDDING_MODEL`

### 是否启用 Embedding

- 修改 `EMBEDDING_ENABLED`

### RAG 模式

- 修改 `RAG_MODE`
  - `hybrid`
  - `semantic`
  - `lexical`

### RAG 降级模式

- 修改 `RAG_FALLBACK_MODE`
  - 当前默认 `lexical_only`

### LangSmith 相关

- 修改 `LANGSMITH_TRACING`
- 修改 `LANGSMITH_PROJECT`

修改 `.env` 后请重启服务。

## 二、通过运行时 Profile 切换

### 查看所有 Profile

- `GET /api/v1/system/runtime-profiles`

### 激活 Profile

- `POST /api/v1/system/runtime-profiles/{profile_id}/activate`

### 设为默认 Profile

- `POST /api/v1/system/runtime-profiles/{profile_id}/set-default`

## 三、如何验证切换已经生效

推荐检查：

1. `GET /api/v1/system/settings`
2. `GET /api/v1/system/runtime-profiles`
3. 发起一个聊天或任务请求
4. 查看：
   - `trace_summary`
   - `debug_view.metrics`
   - `locale`
   - `retrieval_trace`

## 四、当前实现边界

- Profile 切换和设置快照已经能联调验证
- `trace_summary` 已暴露 `langsmith_enabled` 和 `langsmith_project`
- 当前本地环境下 LangSmith / OTel 仍是 stub 元数据，而不是远端真实上报
