# RAG 降级与故障处理文档

Phase 2 的原则是：即使向量库或 embedding 不可用，项目问答也不能整个失效。

## 当前降级目标

- 向量库不可用时仍能回答部分项目问答
- embedding 不可用时仍保留本地词法检索
- 调试信息里必须明确标记降级状态

## 场景 1：Qdrant 无法连接

### 表现

- `knowledge-base/status.qdrant_available=false`
- `retrieval_trace.degraded_mode=true`

### 当前处理

- 保留本地检索
- `reason` 中记录不可用原因
- 若配置仍是 `hybrid`，会切到 `local_hybrid_fallback`

## 场景 2：embedding 模型关闭或不可用

### 表现

- `knowledge-base/status.embedding_available=false`
- `retrieval_trace.mode=lexical_only`

### 当前处理

- 仅使用本地词法匹配
- citation / confidence / debug 字段仍继续返回

## 场景 3：知识库为空

### 表现

- `knowledge-base/status.documents=0`
- 首次项目问答会尝试按默认源自动 seed

### 当前处理

- 若仍无文档，问答结果会返回低置信度和 `no_retrieval_hits`
- 前端应提示用户刷新知识库

## 场景 4：导入部分文档失败

### 表现

- `job.stats.failures` 非空
- `error_message` 会记录失败数量
- 原文件会复制到 `storage/kb/failed/`

### 当前处理

- 不中断整个导入任务
- 已成功的文档照常进入知识库

## 排障建议

1. 先看 `GET /api/v1/knowledge-base/status`
2. 再看导入任务详情
3. 再看任务级 `debug_view.retrieval`
4. 最后看 `storage/artifacts/tasks/{task_id}/debug_snapshot.json`

## 当前边界

- 导入任务仍是同步执行
- 降级后的检索质量会受语料和关键词覆盖度影响
- 还没有把降级状态接到完整监控 / 告警系统
