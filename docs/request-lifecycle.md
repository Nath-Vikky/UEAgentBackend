# 请求生命周期复盘

本文用真实请求路径说明一次 UE 前端请求如何经过后端各层，方便调试和面试讲解。

## 1. 通用入口

UE 前端请求一般进入：

- `POST /api/v1/chat/runs`
- `POST /api/v1/tasks/project-qa`
- `POST /api/v1/tasks/code-review`
- `POST /api/v1/tasks/code-generate`
- `POST /api/v1/tasks/logs-analyze`
- `POST /api/v1/tasks/assets-inspect`

路由层文件：

- `app/api/routes/agent_runs.py`
- `app/api/routes/tasks.py`

它们最终都会调用 `TaskService.create_task()`。

## 2. TaskService 主流程

核心文件：`app/services/task_service.py`

简化流程：

```text
UnifiedTaskRequest
  -> classify_request()
  -> get_or_create_session()
  -> build_context_bundle()
  -> optionally append user message
  -> _execute_route()
  -> build_skill_runtime_descriptor()
  -> build_agent_decision_trace()
  -> persist task / events / artifacts
  -> optionally append assistant message
  -> update_session_memory()
  -> UnifiedTaskResponse
```

调试时优先看：

- `intent`
- `locale`
- `retrieval_trace`
- `debug_view.route`
- `debug_view.context_bundle`
- `debug_view.skill`
- `debug_view.agent_decision_trace`
- `user_view`

## 3. Agent Chat：普通聊天

请求：

```http
POST /api/v1/chat/runs
```

典型问题：

```text
Explain what topological sorting means in simple terms.
```

生命周期：

1. `classify_request()` 判断为 `direct_answer`。
2. `build_context_bundle()` 带上最近会话和编辑器上下文。
3. `_execute_direct_answer_live()` 尝试调用 LLM。
4. 如果 LLM 不可用，返回 degraded fallback。
5. `retrieval_trace.mode = "not_used"`。
6. `debug_view.skill.skill_id = "ProjectQASkill"`。
7. 会写入 chat history。

关键 Debug 字段：

- `intent.route_type = "direct_answer"`
- `retrieval_trace.mode = "not_used"`
- `debug_view.skill.lifecycle.retrieval.status = "skipped"`
- `debug_view.skill.lifecycle.llm.status`

## 4. Agent Chat：当前项目资产问答

请求：

```http
POST /api/v1/chat/runs
```

典型问题：

```text
当前项目有哪些蓝图资产？
```

前置条件：

UE 前端需要先通过 Project Inventory 提交项目快照：

```http
POST /api/v1/project-inventory/snapshot
```

生命周期：

1. Router 判断这是项目事实问题，route 到 `project_qa`。
2. Tool plan 选择 `query_project_inventory`。
3. 不把问题误判成 Assets Inspect，因为 Assets Inspect 只处理用户在面板里选中的资产。
4. `ProjectInventoryService.query()` 查询当前项目快照。
5. 如果问的是“蓝图资产”，按 `asset_type = Blueprint` 过滤。
6. 有 LLM 时综合回答；没有 LLM 时返回 inventory fallback。

关键 Debug 字段：

- `debug_view.route.selected_tool_id = "query_project_inventory"`
- `data.tool_plan.use_inventory = true`
- `data.inventory.items`
- `data.inventory.summary.inferred_asset_type`
- `debug_view.agent_decision_trace.decisions.tool_decision`

常见问题：

- 如果 `data.inventory.summary.empty_reason = "no_project_inventory_snapshot"`，说明 UE 前端还没提交项目快照。
- 如果只有内容浏览器选中的一个资产，说明前端只在 Assets Inspect payload 里传了 selected assets，没有提交完整 Project Inventory。

## 5. Project QA：知识库问答

请求：

```http
POST /api/v1/tasks/project-qa
```

典型问题：

```text
这个项目的代码规范里怎么处理 Actor 生命周期？
```

生命周期：

1. Router 判断需要项目知识。
2. `KnowledgeBaseService.project_qa()` 检索 KB。
3. 根据配置选择 lexical / vector / hybrid。
4. 生成 citations。
5. LLM 可用时综合证据；不可用时返回检索摘要。

关键 Debug 字段：

- `retrieval_trace.mode`
- `retrieval_trace.retrieved_docs`
- `data.citations`
- `debug_view.retrieval`
- `debug_view.agent_decision_trace.decisions.retrieval_decision`

排查：

- `/api/v1/knowledge-base/status` 查看 `summary.rag_readiness`。
- `indexed_chunks = 0` 表示没有可检索内容。
- `lexical_ready = true` 说明即使没向量也能降级检索。

## 6. Code Review

请求：

```http
POST /api/v1/tasks/code-review
```

配套文件扫描：

```http
POST /api/v1/tasks/code-review/files
```

生命周期：

1. UE 前端让用户选择文件。
2. 请求带 `payload.project_root` 和 `payload.file_path`。
3. `CodeReviewSkill.collector` 读取文件内容。
4. `rules` 做确定性检查。
5. `retrieval` 查代码规范和引擎笔记。
6. `llm_analyzer` 可选调用 LLM。
7. `projector` 输出用户可见 blocks。

关键 Debug 字段：

- `data.review_scope.source_kind`
- `data.review_scope.read_status`
- `data.review_scope.content_length`
- `data.rule_hits`
- `data.llm_analysis.status`
- `data.llm_analysis.reason_code`
- `user_view.blocks`
- `debug_view.skill.lifecycle`

如果 LLM 一直 skipped：

- `missing_openai_api_key`：没有配置 LLM。
- `missing_selected_code_content`：前端没有提供可读取的 `project_root + file_path` 或直接代码内容。
- `read_status != "ok"`：后端没有读到文件。

前端展示注意：

- 高亮按钮应读 `user_view.blocks` 或 `data.llm_analysis`。
- 不要把 `data.llm_review`、`debug_view.raw_result`、artifact 原文当用户展示。

## 7. Code Generate

请求：

```http
POST /api/v1/tasks/code-generate
```

生命周期：

1. 接收用户需求。
2. 优先检索 `code_reference`、`examples`、`engine_notes`。
3. 有参考代码时基于参考和需求生成。
4. 无参考代码时由 LLM 生成草案或 fallback。
5. 不直接写入用户工程。

关键 Debug 字段：

- `data.reference_matches`
- `data.generated_code`
- `data.generation_mode`
- `debug_view.skill.lifecycle.retrieval`
- `debug_view.skill.lifecycle.llm`

## 8. Logs Analyze

请求：

```http
POST /api/v1/tasks/logs-analyze
```

生命周期：

1. UE 前端采集或用户粘贴 log text。
2. 后端提取 severity、signature、module。
3. 可选检索 incident history / engine notes。
4. 输出原因、建议和 next steps。

关键 Debug 字段：

- `data.signatures`
- `data.severity_groups`
- `data.recommendations`
- `user_view.blocks`

## 9. Assets Inspect

请求：

```http
POST /api/v1/tasks/assets-inspect
```

生命周期：

1. UE 前端传当前选中资产 metadata。
2. 后端检查命名、类型、依赖和设置。
3. 可选调用 LLM 生成更自然的总结。
4. 输出 issues、recommendations、relationship summary。

关键 Debug 字段：

- `data.violations`
- `data.type_insights`
- `data.relationship_summary`
- `data.llm_analysis`
- `debug_view.skill.lifecycle`

边界：

- Assets Inspect 不负责回答“当前项目有哪些资产”。这类自由聊天问题应通过 ProjectQASkill 调用 Project Inventory。

## 10. 响应持久化

会话与任务分开：

- Chat / Project QA 会写入 `/sessions/{session_id}/history`。
- 工具型任务不写入聊天 history，避免污染 Agent Chat 时间线。
- 所有任务都可在 `/tasks/recent`、`/sessions/{session_id}/tasks` 和 `/tasks/{task_id}` 查看。

如果聊天历史顺序异常：

- 前端应以 `/sessions/{session_id}/history` 渲染聊天时间线。
- 不要把 tasks list 和 chat history 混排成同一聊天流。

## 11. 最小复盘清单

排查一个请求时按这个顺序看：

1. `intent.route_type` 是否符合预期。
2. `debug_view.route.selected_tool_id` 是否选对工具。
3. `debug_view.context_bundle` 是否带了必要上下文。
4. `retrieval_trace` 是否真的检索。
5. `debug_view.skill.lifecycle` 哪一段 skipped/degraded。
6. `data.*.reason_code` 是否说明缺配置或缺输入。
7. `user_view.blocks` 是否是前端应该展示的自然语言结构。
8. `debug_view.agent_decision_trace` 是否能解释整条决策链。
