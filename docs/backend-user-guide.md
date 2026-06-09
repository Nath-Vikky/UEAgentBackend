# UE Agent Backend User Guide

## 0. 文档边界

公开仓库默认只保留面向使用者和读者的文档：

- `README.md`：项目介绍、架构概览、快速启动和常用验证命令。
- `CONTRIBUTING.md`：开发、测试、扩展 Skill/Tool 的基本约定。
- `docs/backend-user-guide.md`：完整使用手册。
- `docs/release-notes/`：公开版本说明。

评测报告、开发计划、交接记录、阶段复盘和学习笔记默认作为本地资料保存，不进入公开文档集。需要查看最新量化结果时，请重新运行对应脚本，报告会生成到 `storage/artifacts/evals/`。

## 1. 项目定位

这个后端服务配合 Unreal Editor 插件使用，定位是本地单机开源项目。它不追求企业级部署和过宽的功能面，而是收口到 5 个核心能力：

- `Agent Chat / Project QA`
- `Code Review`
- `Code Generate`
- `Logs Analyze`
- `Assets Inspect`

## 2. 为什么它满足 Agent 项目的基本定义

它不是简单的 LLM 转发层，而是具备完整的 Agent 基础闭环。

### 统一入口

- `POST /api/v1/chat/runs`
- `POST /api/v1/tasks/*`

### 路由判断

后端会判断当前请求属于：

- `direct_answer`
- `project_qa`
- `single_tool`
- `workflow`

这意味着“是否需要检索知识库”由后端统一决策，不由前端硬编码。

### 知识库与检索

- 支持项目文档导入
- 支持本地词法检索
- 支持可选 `Embedding + Qdrant`
- `project_qa` 会先检索，再把证据交给 LLM 综合回答
- `code_generate` 会先检索 `code_reference` 再生成代码草稿

### 状态与记忆

后端会持久化：

- session
- messages
- tasks
- runs
- artifacts
- trace summary
- proposal

### 调试与观测

后端提供：

- `user_view / debug_view`
- `/metrics`
- `/api/v1/system/alerts`
- `/api/v1/chat/runs/{run_id}/events/stream`

### Tool Registry 与 ReAct Lite

- 工具能力统一登记在 `app/tools/registry.py`。
- 每个工具都有 capability card：`tool_id`、`task_type`、描述、触发词、输入字段、副作用级别、超时、可选 `executor`、`input_schema` 和 `output_schema`。
- `/api/v1/system/capabilities` 会返回 `capabilities.tool_registry.tools`，方便前端和调试页面查看当前后端支持哪些工具。
- `Agent Chat / Project QA` 会在 Debug View 输出 `react_loop`，展示轻量版 `thought -> action -> observation -> final` 轨迹。
- 当前 ReAct Lite 只用于可解释工具决策，不会让 LLM 自动写入工程或执行危险操作。

当前 `Agent Chat / Project QA` 的受控工具白名单：

- `retrieve_project_knowledge`：检索知识库。
- `query_project_inventory`：查询 UE 插件提交的项目资产/代码快照。
- `read_project_file`：只读读取当前 UE 项目内的文本/code 文件。

`read_project_file` 使用条件：

- 前端需要传 `context.project_root`。
- 前端需要传 `context.current_file`，或 payload 中传 `file_path/read_file_path`。
- 后端通过 `app/tools/project_file.py` 校验文件必须位于 `project_root` 内。
- 只允许读取 `.h/.cpp/.cs/.md/.txt/.json/.ini/.uproject/.uplugin/.yaml/.yml` 等文本文件。
- 默认最多读取约 40KB，最大 120KB。
- 只读，不写入、不删除、不移动、不执行。

### Agent Turn Context / Context Budget / Permission Gate

Improv6 adds a small Agent decision foundation without changing the public
request contract. Each task response can now expose these diagnostic blocks:

- `debug_view.agent_turn_context`
- `debug_view.context_budget_report`
- `data.agent_turn_context`
- `data.context_budget_report`

`agent_turn_context` is the backend's per-turn view of the request. It combines
the latest user message, selected UE objects, current Blueprint/graph, selected
Level Actors, selected Material Instances, recent tool summaries, Project
Inventory status, RAG status, MCP provider status, and available tool cards.
This is used to make follow-up prompts such as "this asset", "this Blueprint",
"this actor", or "the material I selected" easier to resolve before falling
back to generic KB retrieval.

`context_budget_report` explains where the prompt/context budget is spent. It
breaks context into recent messages, active UE context, Project Inventory, RAG,
memory, tool summaries, editor operations, and system policy. It is deterministic
and intended for Debug View, eval, and regression checks.

`ToolPermissionDecision` is the internal permission gate for tools:

- `read_only` tools may run automatically when allowed for the route.
- `plan_only` tools may produce plans but cannot touch the UE project.
- `confirmed_write` / `reversible_write` / `destructive_write` tools must become
  pending Proposals.
- MCP-discovered write tools are still mapped back to Proposal flow and cannot
  directly execute UE writes from the backend.

`tool_use_summaries` are display-safe summaries of tool outputs. They keep item
counts, status, warnings, and safe output keys, while hiding raw MCP payloads,
raw JSON-RPC content, and large debug payloads from User View.

`response_critic` is a lightweight deterministic output guard. Before a task
response is returned and persisted to chat history, the backend checks the
visible User View text and blocks for internal implementation details such as
`mcp_get_*`, `ToolSpec`, raw JSON/RPC wording, tool names, and raw result
payloads. If such details are found, it repairs the user-facing text into a
natural-language summary and keeps the raw diagnostics in Debug View. The
report is available at:

- `debug_view.response_critic`
- `data.response_critic`

This guard does not execute tools or change project facts. It only separates
human-facing answers from developer diagnostics.

`intent_draft` and `verified_intent` are the first step of the Improv6 Agent
decision chain upgrade:

- `intent_draft` projects the current route into a structured draft containing
  user goal, intent type, target kind, target reference, project-context need,
  live-editor-context need, knowledge need, write intent, candidate tools, and
  rationale.
- `verified_intent` applies deterministic safety checks over the draft. It
  verifies whether the selected/current target is actually available, checks
  tool registration, applies `ToolPermissionDecision`, and records corrections
  such as `write_tool_requires_proposal` or
  `selected_context_needs_active_target`.
- The current implementation is deterministic and trace-first. A future LLM
  intent drafter can emit the same schema, while the verifier keeps the final
  safety boundary.

`context_resolution` and `tool_plan_v1` are the next structured steps in the
same chain:

- `context_resolution` resolves short references such as "this asset", "this
  Blueprint", "this actor", or "the selected material" into a concrete UE
  target. It records `status`, `source`, `target_id`, `target_display_name`,
  available fields, and missing fields.
- `tool_plan_v1` projects the verified intent and resolved context into a
  stable tool plan. It records the selected tool, side-effect level, argument
  draft, fallback tools, permission decision, and whether the request must
  become a Proposal.

These fields are currently diagnostic and orchestration inputs; existing task
handlers still execute through the same public routes. They make the Agent
decision chain easier to test, inspect, and eventually migrate to an LLM-led or
LangGraph-style graph without changing the HTTP request shape.

No UEAgentTool change is required for these fields. They are backend-side
diagnostics and future Agent orchestration inputs.

### Tool Contract

后端有轻量工具契约校验：

- `validate_tool_registry()`：启动时检查工具注册表。
- `validate_tool_call_input()`：检查 ReAct 工具调用输入是否满足 required/type。
- `validate_tool_result()`：检查工具结果是否满足 required/type。
- `app/tools/context.py`：提供 `ToolContext`、`ToolResult`、`CompositeToolResult`，作为后续新工具 executor / MCP transport 的标准入参和出参 envelope。
- `app/tools/executor_runtime.py`：执行已迁移的本地 executor 前，会先运行工具输入 preflight；缺少必填字段、类型错误、enum 错误会返回 `ToolResult(status="blocked", error_code="tool_preflight_failed")`，不会进入 executor。

查看位置：

- `GET /api/v1/system/health` 的 `startup_checks.tool_registry_contracts`
- `Project QA` 响应的 `data.tool_contracts`
- `Debug View` 的 `debug_view.tool_contracts`

这层校验不引入重依赖，只用于本地稳定性和 Debug 透明度，不会替代完整企业级 schema 平台。

### ToolContext / ToolResult 使用边界

当前稳定路径仍然是 `TaskService -> RouteExecutionDispatcher -> TaskHandler -> SkillExecutor/Service`。`ToolContext` 和 `ToolResult` 是后端内部契约，不要求 UE 前端修改，也不会改变现有 HTTP 响应结构。

后续新增或迁移工具时建议遵循：

- 从 `ToolSpec` 读取 `tool_id`、`timeout_ms`、side effect 和 schema。
- 用 `ToolContext.from_request()` 收集 payload、active context、runtime options 和 trace id。
- executor 返回 `ToolResult.completed()`、`ToolResult.failed()` 或普通 `ToolResult(status="degraded"/"blocked"/"skipped")`。
- Debug View 统一使用 `ToolResult.to_debug_entry()`，减少每个工具自行拼接调试字段。
- 写操作仍然必须走 Proposal confirmation，`ToolResult` 只描述结果，不绕过确认边界。
- `ToolResult.metadata.preflight` 会记录本次工具输入校验结果，包含 `missing_fields`、`type_errors`、`enum_errors`、`unknown_fields` 和 `unknown_field_suggestions`。

当前已迁移的 read-only executor 试点：

- `read_project_file`：`app.tools.project_file:read_project_file_executor`
- `validate_design_config`：`app.tools.config_validate:validate_design_config_executor`

试点边界：

- 只迁移 read-only 工具。
- 不迁移 confirmed-write 工具。
- 不改变 UE 前端请求 / 响应。
- Debug View 新增的 `tool_result_v1` 结构是内部诊断字段。
- 参数预检失败时工具会被 `blocked`，这属于安全阻断，不是 UE 前端执行失败。

### MemoryProvider 使用边界

后端新增 `app/agent/memory_providers.py`，用于把不同记忆来源统一成 provider contract。当前不是新的记忆产品，也不会改变用户可见响应，只是让后续扩展更规整。

当前 provider：

- `SessionLongTermMemoryProvider`：包装原有 `recall_long_term_memory()`，Context Bundle 已通过它读取 `long_term_memory`。
- `FileMemoryProvider`：可选本地私有记忆 provider。`LOCAL_MEMORY_ENABLED=true` 时读取
  `LOCAL_MEMORY_ROOT` 下的 Markdown/TXT 文件，默认目录是 `./runtime/memory`，该目录已被 Git 忽略。
- `WebMemoryProvider`：包装 `WebMemoryService.recall()`，Context Bundle 现在会在 `WEB_MEMORY_ENABLED=true` 时读取最近的高质量 Web Memory。

标准入参/出参：

- `MemoryQuery`：包含 `query`、`project_name`、`limit`、`domain_hints` 和 metadata。
- `MemoryProviderResult`：包含 `provider_id`、`status`、`items`、`raw` 和 `summary`。

边界：

- 不改变 `data.context_bundle.long_term_memory` 的字段。
- 不改变 Web Memory API。
- Web Memory 会单独出现在 `data.context_bundle.web_memory` 和 `data.context_bundle.memory.sources`，不会混入正式 `long_term_memory`。
- Web Memory 仍然只是可追溯的网页摘要缓存，不会写入 `knowledge/`，也不会替代本地 KB/RAG。
- 不新增企业级用户画像或跨项目记忆同步。
- 后续如果增加 Project Memory / Team Memory，优先实现 provider，而不是直接塞进 `context_manager.py`。

File Memory boundary:

- File Memory is exposed as `data.context_bundle.file_memory` and
  `data.context_bundle.memory.sources[].provider_id = "local_file_memory"`.
- File Memory is not KB ingestion, not vector indexing, and not public project
  documentation. Keep private notes under `runtime/memory`.

### Self-Reflection

后端会在回答生成后做一次轻量自检：

- `data.self_reflection`
- `debug_view.self_reflection`
- `agent_decision_trace.decisions.self_reflection_decision`

它检查：

- 回答是否为空。
- Project QA 是否有知识库、项目快照或当前文件证据。
- 置信度是否偏低。
- 是否出现降级 warning。
- Direct Answer 是否使用了 live LLM。

这不是额外的 LLM 评审，不增加模型调用成本；它主要用于 Debug View 和问题排查时解释“回答质量自检”。

### 轻量长期记忆

后端现在支持项目级轻量长期记忆：

- 用户说“请记住”“项目约定”“UE 版本是 5.4”“蓝图命名要加 BP_ 前缀”等内容时，后端会做确定性抽取。
- 记忆保存在当前 session 的 `metadata_json.long_term_memory_items`。
- 新 session 中，如果 `context.project_name` 相同，Context Bundle 会召回相关记忆。
- 召回结果在 `data.context_bundle.long_term_memory` 和 `debug_view.memory_summary.long_term_memory` 中可见。

示例：

```text
请记住：我们的项目 UE 版本是 5.4，所有蓝图命名要加 BP_ 前缀。
```

之后新会话继续传同一个 `project_name`，询问：

```text
创建新蓝图应该注意什么？
```

后端会把 UE 版本和 `BP_` 命名前缀作为长期项目记忆注入上下文。

边界：

- 不调用额外 LLM 抽取记忆。
- 不使用 Qdrant 做向量记忆。
- 不做用户画像或推荐系统。
- 清理 session 会清掉该 session 自己保存的长期记忆，其他 session 的同项目记忆不受影响。

### 配置校验

启动服务和访问 `GET /api/v1/system/health` 时可以查看 `startup_checks`：

- `llm_api_key`：未配置 `OPENAI_API_KEY` 时是 warning，服务仍可启动，LLM 相关能力走降级。
- `chat_model`：为空会标记 error，需要设置 `CHAT_MODEL`。
- `database`：检查数据库连接状态。
- `storage_dirs`：检查 storage、uploads、artifacts、kb 目录。
- `kb_source_paths`：检查 `KB_SOURCE_PATHS` 指向的知识库源目录是否存在。
- `qdrant_config`：提示向量检索配置状态；默认 `EMBEDDING_ENABLED=false`，只使用本地 lexical RAG 时不会探测 Qdrant。

LLM 排查补充：
- 自由聊天会优先使用当前 active Runtime Profile 的 `chat_model`。
- 内置 `default` Runtime Profile 会在后端启动或查询 runtime profiles 时自动同步 `.env` 中的 `CHAT_MODEL`、温度、token 上限等默认配置。
- 如果刚改过 `.env`，请重启后端，再查看 `GET /api/v1/system/runtime-profiles` 的 `active_profile_id` 和 `profiles[].chat_model`。
- 资产改名、Static Mesh 设置、Blueprint 创建属于 Editor Operation Proposal 链路；它们可以由规则和上下文生成提案，不代表在线 LLM 一定可用。

### 增强能力验证

本项目现在保留 4 类验证：

- 单元测试：`tests/unit`
- 集成测试：`tests/integration`
- 契约测试：`tests/contract`
- Eval：`tests/eval`

常用命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration tests/contract tests/eval
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --top-k 4 --min-hit-at-k 0.25 --min-route-accuracy 0.75 --output storage\artifacts\evals\local-rag-eval-smoke.json --markdown-output storage\artifacts\evals\local-rag-eval-smoke.md
.\.venv\Scripts\python.exe scripts\run_hallucination_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --min-grounding-accuracy 1.0 --max-unsupported-answer-rate 0.0 --output storage\artifacts\evals\hallucination-guard-latest.json --markdown-output storage\artifacts\evals\hallucination-guard-latest.md
.\.venv\Scripts\python.exe scripts\run_router_signal_eval.py --output storage\artifacts\evals\router-signal-eval-latest.json --markdown-output storage\artifacts\evals\router-signal-eval-latest.md
.\.venv\Scripts\python.exe scripts\run_blueprint_graph_operation_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py
```

GitHub Actions 当前仅保留手动触发入口，不再随 push 自动运行。日常验证以本地 Ruff、pytest 和 RAG eval 为准；CI 只用于需要时手动复核，不做部署。

`storage/artifacts/evals/*.md` 是本地生成的 Markdown 评估报告，展示 `hit_at_k`、`mrr`、`route_accuracy`、`citation_coverage` 等核心指标。当前评估是 smoke 级别，用于证明“可测、可复现、可继续优化”，不是企业级大规模 benchmark。

`scripts/run_blueprint_graph_operation_smoke.py` 是无 UE、无 LLM 的后端契约烟测。它会调用 `POST /api/v1/editor-operations/proposals` 验证 `print_string`（含 `ActorBeginOverlap -> PrintString`）、`branch_print_string`、`sequence_print_strings`、`delay_print_string`、`get_variable`、`set_variable`、`call_function`、`custom_event_print_string`、`enhanced_input_action_event`、`enhanced_input_print_string`、`connect_blueprint_nodes` 以及两个拒绝用例是否仍然稳定；同时会模拟一次 `POST /api/v1/editor-operations/results`，验证 Blueprint Graph 结果诊断、`editor_operation_graph_details` User View block 和 follow-up quick action 是否仍然连通。报告默认写入 `storage/artifacts/smoke/blueprint-graph-operation-smoke-latest.json`，该目录默认不进入 Git。

`scripts/run_editor_operation_chat_bridge_smoke.py` 是无 UE、无 LLM 的自由聊天桥接烟测。它会先写入一份临时 Project Inventory，然后通过 `POST /api/v1/chat/runs` 验证自然语言是否能稳定生成 `add_blueprint_node_template`（含普通 PrintString、当前 ConstructionScript 焦点、Overlap -> PrintString、Custom Event -> PrintString、Delay -> PrintString、Enhanced Input Triggered -> PrintString，以及中英文 `BP_ProjectSpecificName` 这类真实命名用例）、`compile_blueprint`、`create_blueprint_event_stub`、`place_actor_in_level`、`set_actor_metadata`、`move_assets`、`add_umg_widget`、`set_umg_widget_text`、`set_umg_widget_appearance`、`set_umg_widget_brush`、`set_umg_slot_layout_v2`、`duplicate_umg_widget`、`delete_umg_widget`、`set_material_instance_parameter` 和 `set_material_instance_static_switch` Proposal。报告默认写入 `storage/artifacts/smoke/editor-operation-chat-bridge-smoke-latest.json`。

幻觉守卫评测专门覆盖：
- 没有 Project Inventory 时，不能编造当前工程里不存在的蓝图、变量或组件。
- 检索不到专名证据时，不能用泛化 UE 文档凑答案。
- “知识库有哪些内容”应进入 catalog 模式，只列目录和用途，不展开源码正文。
- 有明确证据的 UE 问答需要返回 citations 和期望来源。

核心指标：
- `grounding_accuracy`：是否符合“有证据再回答、无证据则拒答或要求补充资料”的预期行为。
- `abstention_accuracy`：无证据样例是否正确拒答。
- `unsupported_answer_rate`：无证据样例中仍然编造细节的比例，稳定版目标是 `0.0`。

Agentic RAG A/B 对比：

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_agentic_ab.py --top-k 4 --max-hit-drop 0.0
```

这个脚本会在同一套数据集上分别运行：
- baseline：`payload.disable_agentic_rag=true`
- agentic：`payload.disable_agentic_rag=false`

输出文件：
- `storage/artifacts/evals/rag-agentic-ab-latest.json`
- `storage/artifacts/evals/rag-agentic-ab-latest.md`

报告适合用于项目说明：当前 Agentic RAG 不是复杂 planner，而是一个可量化、可关闭、可回归测试的轻量 query refinement 层。

### Docker 本地演示

本项目提供轻量 Docker / Compose 入口，用于本地演示和项目留档：

```powershell
docker compose up --build
```

默认服务：

- `app`: `http://127.0.0.1:8000`
- `qdrant`: `http://127.0.0.1:6333`

默认边界：

- Compose 默认 `EMBEDDING_ENABLED=false`，先跑 lexical RAG。
- Qdrant 服务会启动，但向量检索是否启用由 `.env` / compose 环境变量决定。
- 不做云部署、不做 K8s、不做镜像推送。
- `storage` 和 `qdrant_data` 使用 Docker volume 保存。

常用命令：

```powershell
docker compose down
docker compose logs -f app
```

如果本机有 `make`，也可以用：

```powershell
make docker-up
make docker-down
```

### 可选 Token SSE 流式入口

后端现在新增了可选聊天流式入口：

- `POST /api/v1/chat/runs/stream`

它只用于 `Agent Chat / Project QA`，不会改变 Code Review、Code Generate、Logs Analyze、Assets Inspect 的同步返回方式。旧接口仍然保留：

- `POST /api/v1/chat/runs`
- `GET /api/v1/chat/runs/{run_id}/events/stream`

两者区别：

- `POST /chat/runs`：非流式，返回完整 JSON，当前 UE 插件默认继续使用它。
- `GET /chat/runs/{run_id}/events/stream`：历史事件回放，用于查看已持久化事件。
- `POST /chat/runs/stream`：可选实时 SSE，事件名包括 `stream_opened`、`run_started`、`tool_call`、`tool_result`、`assistant_delta`、`final`、`error`。

边界：

- 必须保留非流式 fallback。
- 当前只在最终 LLM 回答阶段推送 `assistant_delta`；检索、Inventory、文件读取以 `tool_call/tool_result` 事件说明进度。
- LLM 不可用时仍会返回 `final`，但不会强行伪造 token。
- UE 前端需要支持 `text/event-stream` 持续读取和逐 token 更新同一条 assistant 气泡后，才建议正式接入。

## 3. 当前后端架构

### 接口层

- `app/api/routes/`
  - system
  - agent runs
  - tasks
  - sessions
  - proposals
  - knowledge base

### 服务层

- `app/services/task_service.py`：统一任务执行入口
- `app/services/llm_service.py`：OpenAI 兼容聊天、JSON 输出与路由判断
- `app/services/kb_service.py`：知识库导入、检索、向量重建
- `app/services/session_service.py`：session 创建、恢复与清理
- `app/services/proposal_service.py`：Proposal 审批与审批后回写
- `app/services/code_generation_service.py`：代码参考检索增强后的代码生成

### 工具与工作流层

- `app/tools/`：单工具能力
- `app/workflows/graphs/`：多步任务能力

### 知识库层

- `app/rag/ingestion/`
- `app/rag/retrieval/`
- `app/rag/indexing/`

### 观测层

- `app/observability/`

## 4. 当前正式产品边界

### 4.1 Agent Chat / Project QA

这是唯一保留的完整聊天入口。

现在支持：

- 普通聊天走 `direct_answer`
- 项目相关问答走 `project_qa`
- 后端根据用户问题和上下文，自主判断是否触发知识库
- `debug_view.route` 返回分流依据，例如：
  - `decision_source`
  - `project_signal_strength`
  - `llm_route_decision`

边界：

- 聊天入口不再替代其它功能的专用面板
- 只有确实需要项目事实时才会触发检索

### 4.2 Code Review

现在支持：

- 显式提交 `diff_text`
- 显式提交 `code` / `file_content`
- 通过 `project_root + file_path` 由后端直接读取文件
- `POST /api/v1/tasks/code-review/files` 获取可选代码文件列表

主线目标：

- 专注单文件审查
- 不做全工程自动巡检
- 不自动修复、不自动写回工程
- `user_view.blocks` 会包含 `llm_analysis`，用于展示 LLM 综合解释；LLM 未配置时会标记为 `status=skipped`

### 4.3 Code Generate

现在支持：

- 输入自然语言需求
- 先检索知识库中的代码参考、示例和项目文档
- 返回非破坏性的代码草稿结果
- 返回 `generated_items` 供前端做按钮 / Tab / 列表展示
- 返回 `reference_lookup`、`generation_mode`、`retrieved_references`
- 返回 `preflight_report`，对生成结果做轻量 UE C++ 预检
- 返回 `write_policy.written_to_disk=false`，并在每个 `generated_items[]` 上标记 `write_status=not_written`、`is_virtual=true`

边界：

- 不直接写用户工程
- 不自动 patch 文件
- 不做真实 compile / build 验证；`preflight_report` 只是静态烟测，不替代 UE 编译器或 UnrealHeaderTool
- 代码参考增强已经落地，但结果仍然是“建议草稿”而不是执行器

注意：`generated_items[].file_path` 是建议放置路径或虚拟草稿路径，不代表后端已经创建了这个文件。前端应把它渲染为“生成结果按钮 / Tab”，点击后展示 `generated_items[].code`，不要把它显示成“已生成到磁盘的文件路径”。

当前 Code Generate 已补充第一批常用 UE 场景模板：当需求包含“角色增强输入 / 角色输入增强 / Enhanced Input Character / Input Mapping Context / Input Action”等信号时，即使没有配置 LLM，也会返回 `ACharacter` 版本的 Enhanced Input 草稿，建议路径为 `Source/<Module>/Public/<Class>.h` 和 `Source/<Module>/Private/<Class>.cpp`，并在 `patch_plan` 中提示添加 `EnhancedInput` 模块依赖。交互组件、射线交互组件、GameInstanceSubsystem 也有基础兜底草稿。

如果 live LLM 返回的 Enhanced Input 代码只是普通 `AActor` / `BeginPlay` / `Tick` 骨架，后端会把这次 LLM 结果标记为 `llm_generation_rejected:enhanced_input_incomplete`，然后回退到确定性的 Enhanced Input Character 模板，避免前端拿到看似成功但内容不匹配的代码。

`preflight_report` 会检查 3-5 类常见生成问题：不安全路径、`.h/.cpp` 配对、UE `UCLASS / GENERATED_BODY / .generated.h` 反射结构、`.cpp` 是否包含同名头文件、Enhanced Input 是否包含 `InputAction / MappingContext / BindAction / AddMappingContext / Build.cs` 提示等。它会返回 `status=passed/warning/failed`、`quality_score`、`summary` 和 `findings[]`。如果出现 warning/error，仍然不会自动改工程，前端可把它作为“复制进工程前请复查”的提示。

### 4.4 Logs Analyze

现在支持：

- 传入 `log_text` / `selected_log_text` / `log_excerpt` / `error_excerpt` / `error_lines`，用于只分析几行 Error/Fatal
- 传入 `log_file_path` / `log_path` / `file_path`，用于从用户选择的日志文件读取
- 可选传入 `log_source`、`notes`、`attachment_paths`、`time_range`、`line_window`
- 返回结构化事件、问题类型、建议动作
- `user_view` 已按日志面板形态输出：
  - 摘要
  - LLM 综合分析
  - 问题类型
  - 建议动作
  - 日志窗口信息
  - 模块 / 资源线索

最小请求示例：

```json
{
  "payload": {
    "log_file_path": "F:/Epic Games/project/RushBa/Saved/Logs/RushBa.log",
    "line_window": {"start": 120, "end": 220},
    "notes": "点击 Play 后崩溃"
  }
}
```

如果用户只想分析几行错误，也可以只传：

```json
{
  "payload": {
    "selected_log_text": "LogTemp: Error: Access violation reading address\nCallstack: 0x0001 Demo!UMySubsystem",
    "log_source": "Output Log selected lines"
  }
}
```

边界：

- 日志采集应由插件或本地脚本负责
- 后端只读取前端显式传入的文本或路径，不主动扫描 UE 日志目录
- 后端默认读取日志文件尾部窗口，超长日志会截断；如果传入 `line_window`，则读取指定行范围
- 后端不会修改、删除或移动日志文件

LLM 与知识库策略：

- `data.llm_analysis` 会明确说明本次是否执行 LLM 综合解释。
- `llm_analysis.status=completed` 表示 LLM 已基于日志解析事实做综合判断。
- `llm_analysis.status=skipped` 表示未执行 LLM，常见原因是 `missing_openai_api_key`，规则解析结果仍然可用。
- 日志知识库检索会经过 `data.retrieval_quality_gate`，只有质量达标的 `incident_history / engine_notes / project_docs` 才会进入用户引用和 LLM 上下文。
- 低质量命中会保留在 Debug View 诊断中，不会强行作为普通用户答案依据。

### 4.5 Assets Inspect

现在支持：

- 传入选中资产列表
- 可选传入 `asset_items`
  - `asset_path`
  - `asset_type`
  - `package_path`
  - `dependencies`
  - `referencers`
- 返回命名、目录、重复候选、类型说明、关系摘要
- `user_view` 已按资产检查面板输出：
  - 检查摘要
  - LLM 综合分析
  - 规则问题
  - 重命名建议
  - 资产类型
  - 关系摘要
  - 参考规则摘要
- `data.llm_analysis` 会说明 LLM 分析状态、跳过原因、优先级和关键点

边界：

- 后端不直接解析 `.uasset`
- 资产依赖 / 引用关系仍需要前端从编辑器侧采集后传入

## 5. 已收缩但保留兼容代码的功能

以下功能仍有后端代码，但已经不是这版主线：

- `config_generate`
- `config_validate`
- `assets_plan`
- `assets_execute`
- `perf_analyze`

建议前端主菜单隐藏它们。

## 6. 启动方式

在 `backend/` 目录下执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果数据库是全新本地库，推荐先跑迁移。如果只是临时联调，不跑迁移通常也能先启动，因为启动时会尝试 `create_all`。

## 7. 最小 `.env` 配置

### 只接聊天模型

至少配置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `CHAT_MODEL`

此时：

- `direct_answer` 可以直接调用在线 LLM
- `project_qa` 可以使用本地词法检索

### 启用知识库

再补：

- `KB_SOURCE_PATHS`
- `KB_DIR`

### 启用 Embedding

再补：

- `EMBEDDING_ENABLED=true`
- `EMBEDDING_MODEL`

默认情况下 `EMBEDDING_ENABLED=false`，后端会优先使用本地 lexical 检索，不会在每次检索时探测 Qdrant。

### 启用 Qdrant

再补：

- `QDRANT_URL`
- `QDRANT_API_KEY`
- `QDRANT_COLLECTION`

## 8. 知识库怎么补充

### 刷新默认知识库

```http
POST /api/v1/knowledge-base/refresh
```

### 指定路径重建

```json
{
  "source_paths": [
    "../backend.md",
    "../forward.md",
    "./docs",
    "D:/MyProject/DesignDocs"
  ],
  "force_rebuild": true
}
```

### 临时导入一段文本

```http
POST /api/v1/knowledge-base/import
```

```json
{
  "source_type": "text",
  "title": "Combat Notes",
  "text": "Dash interrupts light attack recovery.",
  "domain": "project_docs",
  "project_id": "RushBa"
}
```

### 导入代码文件

知识库也支持把代码文件作为参考资料导入，例如：

- `.h`
- `.hpp`
- `.cpp`
- `.cs`
- `.py`

代码文件入库后会被归类为 `code_reference`，用于后续 `Code Generate` 的参考检索。

## 9. 只接 LLM 时检索怎么工作

如果只接入聊天模型，没有启用 `Embedding + Qdrant`，那么 `project_qa` 会按下面流程工作：

1. 本地知识库文档切块
2. 本地词法检索
3. 命中后可选再交给聊天模型综合回答

也就是说，向量链路不是必须条件。

如果用户问“知识库有哪些内容”这类目录问题，后端会走 `knowledge_catalog` 模式，只返回已索引文档的标题、分类和路径，不展开源码正文。这样可以避免把 `knowledge/code-reference` 里的 `.h/.cpp` 内容直接当成聊天回答。

中文问题也能检索英文知识笔记。当前后端会做轻量 query 扩展，例如“actor的生命周期是什么”会补充 `lifecycle`、`constructor`、`BeginPlay`、`Tick`、`EndPlay` 等英文检索词；这能提升未接入向量模型时的命中率。它不是完整翻译，也不替代向量检索，只是本地项目级的稳定增强。

### Agentic RAG v1：两轮检索与证据门槛

Project QA 和 Code Generate 现在会在第一轮 RAG 证据不足时，自动做一次轻量 query rewrite。它会把中文 UE 术语、domain filter、当前 module / file 等信息补进第二轮检索 query，例如“角色增强输入代码怎么写”会补充 `EnhancedInput`、`UInputAction`、`UEnhancedInputComponent`、`Build.cs` 等词。

这不是复杂 Planner，也不会无限循环。当前边界是最多 2 轮检索：
- 第一轮：按用户原始问题检索。
- 第二轮：仅当第一轮没有足够证据时才改写 query 后重试。
- 如果仍然没有证据，会在 `retrieval_quality_gate.evidence_insufficient=true` 中标记，而不是强行把弱命中当成事实。

可在响应里查看：
- `retrieval_trace.agentic_rag`：两轮检索的 query、质量判断、选择了哪一轮。
- `data.retrieval_quality_gate`：最终是否有可用证据、RAG 命中数、本地 grep 命中数。
- `data.reference_lookup.agentic_rag`：Code Generate 使用的改写检索摘要。

前端不需要强制适配这些字段；它们主要用于 Debug View、本地演示和后续 RAG 调优。

## 10. 检索模式说明

- `lexical`：只使用本地词法检索
- `hybrid`：词法检索 + 向量召回
- `semantic`：更偏向向量检索

回退模式：

- `lexical_only`
- `local_hybrid_fallback`

## 11. 监控怎么查看

### 健康检查

- `GET /api/v1/system/health`

### 系统快照

- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/settings`

### 告警

- `GET /api/v1/system/alerts`

### 指标

- `GET /metrics`

## 12. 主要指标有什么用

- 错误率：看后端是否开始频繁失败
- P95 延迟：看交互是否开始变慢
- 每小时成本：看 LLM 调用成本是否异常
- KB miss rate：看知识库是否经常检索不到
- KB 导入失败率：看知识库源文件是否有解析问题
- proposal backlog：看是否有等待确认的任务积压

## 13. 调试建议顺序

1. `GET /api/v1/system/health`
2. `GET /api/v1/system/bootstrap`
3. `GET /api/v1/system/capabilities`
4. `GET /api/v1/knowledge-base/status`
5. `POST /api/v1/sessions`
6. `POST /api/v1/chat/runs`
7. `POST /api/v1/tasks/code-review/files`
8. `POST /api/v1/tasks/code-review`
9. `POST /api/v1/tasks/code-generate`
10. `POST /api/v1/tasks/logs-analyze`
11. `POST /api/v1/tasks/assets-inspect`
12. `POST /api/v1/project-inventory/snapshot`
13. `GET /api/v1/project-inventory/summary`

## 14. 当前真实边界

- `events/stream` 仍然是事件回放，不是 token 级实时流
- `code_generate` 不直接写用户工程，也不做编译验证
- `LangSmith / OTel` 仍是本地契约层，不是远端生产观测链路
- 资产关系图依赖前端从编辑器侧采集元数据

## 15. UE 联调后的关键行为

### Agent Chat 路由

`POST /api/v1/chat/runs` 仍是唯一聊天入口。后端会先用规则判断 `direct_answer` / `project_qa`，当项目上下文信号较弱时再让 LLM 做一次路由复核。

LLM 复核只负责判断是否需要项目知识检索，不负责生成最终答案。无论 LLM 返回成功 JSON、非法 JSON、空内容或失败结果，后端都会返回结构化路由诊断，不应再因为路由复核触发 500。

### Code Review 文件扫描

`POST /api/v1/tasks/code-review/files` 用于扫描当前 UE 工程下的代码文件。请求示例：

```json
{
  "project_root": "F:/Epic Games/project/RushBa",
  "source_roots": ["Source", "Plugins"],
  "query": "Actor",
  "limit": 200
}
```

返回项会包含：
- `file_path`：相对 `project_root` 的路径，前端审查时可直接回传
- `label`：显示名
- `module_name`：从 `Source/<Module>` 或 `Plugins/<Plugin>/Source/<Module>` 推断
- `file_type`：如 `cpp`、`h`、`cs`
- `scan_diagnostics`：空列表或异常时的原因诊断

### Code Review 读文件审查

前端选择文件后，调用 `POST /api/v1/tasks/code-review`，在 `payload` 中传：

```json
{
  "project_root": "F:/Epic Games/project/RushBa",
  "source_roots": ["Source", "Plugins"],
  "file_path": "Source/RushBa/MyActor.cpp",
  "focus": "General"
}
```

兼容字段：如果 UE 端更方便传“选中文件对象”，后端也会识别
`payload.selected_file.relative_path`、`payload.selected_file.absolute_path`、`payload.selected_files[0].relative_path`
或 `payload.files[0].path`。如果前端已经读取了文本，可直接传 `payload.code`、`payload.source_text`、
`payload.file_content`、`payload.code_content`，或 `payload.files[0].content`。这些字段都会进入同一套
Code Review collector，成功时 `data.review_scope.read_status = "ok"` 或 `inline`，且不会再被误判为
`missing_selected_code_content`。

后端会读取该文件内容，并在 `data.review_scope` 中返回：
- `resolved_absolute_path`
- `read_status`
- `content_length`
- `applied_focus`
- `source_roots`
- `load_error`

如果读取失败，任务会返回明确错误，前端不应把它展示成普通审查完成。

### Assets Inspect 命名检查

`asset_items` 建议至少传入：

```json
{
  "asset_name": "NewMap",
  "asset_path": "/Game/NewMap.NewMap",
  "asset_type": "World",
  "package_path": "/Game/NewMap",
  "dependencies": [],
  "referencers": []
}
```

后端会先做确定性规则检查，再补充知识库参考。默认/占位名如 `NewMap`、`Untitled`、`NewBlueprint`、`NewMaterial`、`NewTexture`、`NewDataAsset` 会稳定返回 warning 和重命名建议；`World` 资产会建议使用 `L_` 或 `Map_` 前缀的项目语义命名。

### Project Inventory 快照

`POST /api/v1/project-inventory/snapshot` 用于接收 UE 插件提交的项目快照。后端只保存和查询结构化 JSON，不直接解析 `.uasset`。

建议提交：

```json
{
  "project_id": "RushBa",
  "project_name": "RushBa",
  "source": "ue_plugin",
  "assets": [
    {
      "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
      "asset_name": "SM_Rock",
      "asset_type": "StaticMesh",
      "package_path": "/Game/Environment",
      "dependencies": ["/Game/Materials/M_Rock"],
      "referencers": ["/Game/Maps/L_Test"],
      "settings": {
        "nanite_enabled": true,
        "lod_count": 3,
        "collision_complexity": "UseComplexAsSimple"
      },
      "properties": {
        "material_slots": ["M_Rock"],
        "triangle_count": 12000
      }
    }
  ],
  "code_files": [
    {
      "file_path": "Source/RushBa/Player/RBPlayerCharacter.cpp",
      "module_name": "RushBa",
      "file_type": "cpp",
      "classes": ["ARBPlayerCharacter"]
    }
  ],
  "level_actors": [
    {
      "actor_label": "BP_EnemySpawner_1",
      "actor_class": "BP_EnemySpawner_C",
      "level_name": "L_Test",
      "blueprint_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
      "transform": {"location": {"x": 100, "y": 0, "z": 20}},
      "components": ["SceneRoot", "Billboard"]
    }
  ],
  "material_instances": [
    {
      "material_instance_path": "/Game/Materials/MI_Rock.MI_Rock",
      "material_instance_name": "MI_Rock",
      "parent_material": "/Game/Materials/M_Rock.M_Rock",
      "scalar_parameters": [{"name": "Roughness", "value": 0.6}],
      "texture_parameters": [{"name": "BaseColor", "texture_path": "/Game/Textures/T_Rock_D"}]
    }
  ]
}
```

常用查询：

- `GET /api/v1/project-inventory/summary`：资产和代码文件总览
- `GET /api/v1/project-inventory/assets?asset_type=StaticMesh`：按资产类型查询
- `GET /api/v1/project-inventory/assets/{asset_id}`：查看单个资产详情
- `GET /api/v1/project-inventory/code-files?module_name=RushBa`：查询代码文件索引
- `GET /api/v1/project-inventory/blueprints?parent_class=ACharacter`：查询蓝图资产结构摘要，包括父类、组件、变量、函数、图表、轻量 `graph_summaries` 和接口
- `GET /api/v1/project-inventory/blueprint-graphs?blueprint_query=Player&graph_name=EventGraph`：聚焦查询蓝图图表摘要，包括 graph/node/pin 只读信息
- `GET /api/v1/project-inventory/level-actors?level_name=L_Test`：查询当前快照里的关卡 Actor 摘要
- `GET /api/v1/project-inventory/material-instances?parent_material=/Game/Materials/M_Rock.M_Rock`：查询材质实例参数摘要
- `POST /api/v1/project-inventory/query`：按自然语言关键词查询资产或代码索引

Project Inventory 已经接入 Agent Chat / Project QA。用户问“工程里有哪些资产”“有哪些开启 Nanite 的静态网格体”“某模块有哪些 C++ 文件”“当前项目有哪些蓝图”“BP_PlayerCharacter 有哪些变量/函数/图表/节点摘要”“当前关卡有哪些 Actor”“MI_Player 有哪些材质参数”这类项目事实问题时，后端会先查询项目快照，并把命中的资产 / 代码 / 蓝图结构 / 蓝图图表摘要 / 关卡 Actor / 材质实例摘要并入回答上下文。LLM 不可用时也会返回基于快照的基础回答。

Snapshot freshness:

- `PROJECT_INVENTORY_STALE_AFTER_SECONDS` 默认是 `300`，表示快照超过 5 分钟会标记为 `stale`。
- `POST /snapshot`、`GET /summary`、`POST /query`、Agent Chat 的 `data.inventory.summary` 和 `debug_view.active_context.inventory` 都会返回 `freshness`。
- `freshness.status` 可能是 `fresh`、`stale`、`missing` 或 `unknown`。
- `freshness.should_refresh=true` 时，UE 插件可以提示用户点击 `Sync Inventory Now`，但后端仍会基于最近一次快照回答，并在回答中说明该快照可能不是最新。
- 如果 Project QA 使用在线 LLM 综合回答，后端也会把 `freshness` 写入提示词，要求模型说明 stale 快照的边界。

兼容边界：

- 旧版 UE 插件只提交 `assets` 和 `code_files` 仍然完全可用。
- `level_actors` 和 `material_instances` 是可选增强字段；新版 UEAgentTool 打开面板时会自动静默提交一次 Inventory，也可以通过 `Sync Inventory Now` 手动重试。它会补采集当前已加载关卡 Actor 和 Material Instance 参数，自由聊天才能回答“当前关卡摆了哪些对象”“某个材质实例参数值是多少”等更具体问题。
- 后端只信任快照字段，不直接读取 `.umap`、`.uasset`，也不会推断快照里没有的 Actor 或材质参数。

## 16. 用户可见语言与 Code Review 输出质量

### 用户可见语言

后端会尽量保证 `user_view` 里的自然语言跟随最终输出语言。中文工作流下，下列字段应输出中文自然语言：
- `user_view.title`
- `user_view.text`
- `user_view.blocks[].title`
- `user_view.blocks[].text`
- `user_view.blocks[].data.items[].reason`
- `user_view.blocks[].data.items[].suggestion`
- `user_view.quick_actions[].label`

以下内容保持英文或原文是正常的：
- API 字段名
- `block_type`、`read_status`、`severity` 等稳定枚举
- 文件路径
- 代码符号
- 资产名
- `L_`、`Map_`、`BP_` 这类项目命名前缀

### Code Review 固定输出块

Code Review 的 `user_view.blocks` 当前固定优先输出：
- `summary`：审查范围、读取状态、严重度摘要、KB/LLM 情况
- `llm_analysis`：面向普通用户的 LLM 综合解释；LLM 未配置时为 `status=skipped`
- `issues`：具体问题；如果没有明显问题，会返回“未发现高风险规则命中”
- `recommendations`：可执行修改建议
- `references`：引用的知识库证据；没有命中时说明使用通用规则 fallback
- `next_steps`：编译、编辑器验证、补充知识库等后续动作

Code Review 现在还会在上述固定块之后追加用于说明链路的轻量 Agent 工作流块：

- `agent_workflow`：说明本轮是否按“采集代码 -> 规则扫描 -> 知识库参考 -> LLM 解释 -> 修复草稿 -> 验证清单”执行
- `fix_draft`：非破坏性修复草稿，只给建议，不写入工程
- `validation_plan`：编译、PIE、资产引用、日志复查等验证清单

对应数据也会出现在：

- `data.agent_workflow`
- `data.fix_draft`
- `data.validation_plan`
- `data.localized_review.agent_workflow`
- `data.localized_review.fix_draft`
- `data.localized_review.validation_plan`

这些字段用于展示“Agent 如何组合工具和推理步骤”，但仍保持本地 Agent 边界：不自动改文件、不自动运行 UE 测试、不替代人工确认。

### Validation Advisor

为了让工具结果更贴近游戏研发流程，后端现在会在多个 Skill 中附加 `validation_plan`：

- `Code Review`：修复建议之后，提示编译、PIE、UObject 生命周期、Tick、线程、资产引用、蓝图编译、日志复查。
- `Code Generate`：生成草稿之后，先附加 `preflight_report` 静态预检，再提示手动放置文件、编译模块、检查 Build.cs、配置 Enhanced Input 资产、验证 Trace / Overlap / Subsystem 场景。
- `Logs Analyze`：日志分析之后，提示保留完整日志窗口、复现步骤、首个 Error/Fatal、资产路径、相关模块。
- `Assets Inspect`：资产检查之后，提示重命名确认、Fix Up Redirectors、蓝图编译、StaticMesh 设置、Reference Viewer。

统一字段：

- `data.validation_plan`
- `data.preflight_report`
- `user_view.blocks[block_type="validation_plan"]`
- `step_results[].step_id = "preflight_generated_code"`
- `step_results[].step_id = "build_validation_plan"`
- `debug_view.tools[].tool_id = "preflight_generated_code"`
- `debug_view.tools[].tool_id = "build_validation_plan"`

边界：这些都是建议，不代表后端已经修改工程、运行测试或保存资产。

### LLM 综合审查

当 LLM 已配置且文件读取成功时，Code Review 会尝试额外进行 `llm_code_review_synthesis`：
1. 读取当前文件片段
2. 合并规则扫描结果
3. 合并知识库检索证据
4. 要求 LLM 返回结构化 JSON 综合审查

如果 LLM 不可用或返回非法 JSON，后端不会中断任务，而是稳定降级到规则扫描和知识库检索结果。可在 `data.llm_review.reason` 查看原因，例如：
- `missing_openai_api_key`
- `json_parse_failed`
- `file_read_failed_or_empty_source`

面向前端展示时优先使用 `data.llm_analysis` 和 `user_view.blocks[].block_type == "llm_analysis"`。该块是给用户看的解释卡片，`data.llm_review` 则保留为 Debug View 的原始 LLM 调用诊断。

### KB 不足时的审查策略

如果项目知识库没有命中足够证据，Code Review 仍会基于当前文件内容和通用 Unreal/C++/C# 规则给出结果，并在 `references` 块中明确说明“仅供参考”。这能避免前端看到空洞总结，也能帮助用户知道下一步应补充哪些项目规范。

## 17. 知识库、向量模型与向量数据库使用手册

这一节是后端当前推荐的长期使用方式。简单说：项目资料统一进入知识库，检索层根据任务需要取上下文，LLM 负责自由回答、综合推理和生成内容。只配置 LLM 也能跑；补上 embedding 和 Qdrant 后，检索质量会更好。

### 17.1 知识库导入链路

知识库统一走这一条 pipeline：

```text
source paths / inline text
-> loader
-> parser
-> cleaner
-> chunker
-> lexical index
-> embedding
-> vector store
-> retrieval
```

当前优先稳定支持：
- 文本文档：`.md`、`.txt`、`.json`、`.csv`、`.ini`、`.cfg`
- 代码文件：`.h`、`.hpp`、`.hh`、`.inl`、`.c`、`.cc`、`.cpp`、`.cxx`、`.cs`、`.py`
- HTML 文档：`.html`

增强支持：
- PDF：`.pdf`
- Word：`.docx`

PDF/DOCX 需要额外解析依赖，后端会优先尝试 `docling`，再尝试 `unstructured`。如果这些依赖没有安装，普通文本、代码和 HTML 导入不受影响。建议先把项目规范、代码示例、UE 插件说明整理成 Markdown、代码文件或 HTML，再把 PDF/DOCX 作为补充资料导入。

### 17.2 推荐的知识库目录组织

可以把资料按用途分目录，方便后续维护：

```text
knowledge/
  project_docs/
    gameplay-overview.md
    plugin-workflow.md
  code_reference/
    actor-spawn-example.cpp
    editor-subsystem-example.h
  asset_rules/
    naming-rules.md
  team_rules/
    code-style.md
  engine_notes/
    unreal-editor-api.html
  examples/
    inventory-component.cpp
```

后端会自动识别部分 domain，但更推荐在导入 inline text 时显式传 `domain`。常用 domain：
- `project_docs`：项目说明、玩法系统、插件工作流
- `code_reference`：可复用代码、示例类、UE API 用法
- `examples`：代码生成可参考的完整片段
- `team_rules`：团队规则、代码风格、提交流程
- `asset_rules`：资产命名、目录结构、引用规范
- `engine_notes`：Unreal Engine API、编辑器扩展笔记
- `incident_history`：历史 Bug、崩溃、排查记录
- `perf_notes`：性能分析记录
- `config_schema`：配置字段说明

### 17.3 通过配置导入本地资料

在 `.env` 里配置默认知识库路径：

```env
KB_SOURCE_PATHS=./knowledge
KB_DIR=./storage/kb
KB_MAX_FILE_BYTES=5000000
KB_CHUNK_SIZE=600
KB_CHUNK_OVERLAP=100
```

启动后调用：

```http
POST /api/v1/knowledge-base/refresh
```

请求体可以为空，此时使用 `KB_SOURCE_PATHS`。当前默认只扫描 `./knowledge`，这是 UE 用户知识库；后端开发文档和前端交接文档不应作为用户可见知识库来源。如果只想刷新指定路径：

```json
{
  "source_paths": [
    "./knowledge/project-docs",
    "./knowledge/code-reference"
  ],
  "force_rebuild": false
}
```

如果要彻底重建本地知识库：

```json
{
  "source_paths": [
    "./knowledge"
  ],
  "force_rebuild": true
}
```

`force_rebuild=true` 会清空本地已导入文档并重建索引，适合知识库结构大改、删除大量旧资料、或更换向量模型后使用。

### 17.4 通过 API 导入一段文本

适合从前端、脚本或临时笔记直接补充知识：

```http
POST /api/v1/knowledge-base/import
```

`source_type=text` 时，正文可以使用 `content` 或 `text` 字段；`domain`、`doc_type`、`tags`、`metadata` 会被保存到文档记录里，后续检索和 Debug View 都可以看到。

```json
{
  "source_type": "text",
  "title": "UE 资产命名规范",
  "content": "World 资产建议使用 L_ 或 Map_ 前缀；Blueprint 建议使用 BP_ 前缀。",
  "domain": "asset_rules",
  "metadata": {
    "author": "local",
    "version": "2026-04-22"
  }
}
```

代码生成资料建议这样导入：

```json
{
  "source_type": "text",
  "title": "Actor Tick 禁用示例",
  "content": "AMyActor::AMyActor() { PrimaryActorTick.bCanEverTick = false; }",
  "domain": "code_reference",
  "metadata": {
    "language": "cpp",
    "module": "RushBa"
  }
}
```

导入完成后，`CodeGenerateSkill` 可以优先检索 `code_reference` 和 `examples`，把命中的代码资料与用户需求一起交给 LLM 综合生成。

### 17.5 查看、删除与重建知识库

常用接口：
- `GET /api/v1/knowledge-base/status`：查看知识库状态、支持格式、向量库状态、降级原因
- `GET /api/v1/knowledge-base/documents`：查看已导入文档
- `POST /api/v1/knowledge-base/reindex`：重建索引和向量
- `DELETE /api/v1/knowledge-base/documents/{doc_id}`：删除指定文档并重建向量索引
- `GET /api/v1/knowledge-base/jobs/{job_id}`：查看导入任务进度
- `POST /api/v1/knowledge-base/jobs/{job_id}/retry`：重试失败导入任务

旧路径 `GET /api/v1/knowledge-base/import-jobs/{job_id}` 和 `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry` 仍保留兼容；新前端建议使用更短的 `/jobs` 路径。

如果你只是新增少量资料，使用 `refresh` 或 `import` 即可。如果你换了 embedding 模型、换了 Qdrant collection、或删除了大量资料，建议使用 `reindex` 或 `force_rebuild=true`。

### 17.6 只接入 LLM 时的检索方式

只配置 LLM、不配置 embedding/Qdrant 时，后端仍能使用本地词法检索：

```env
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=https://你的兼容服务/v1
CHAT_MODEL=你的聊天模型

EMBEDDING_ENABLED=false
RAG_MODE=lexical
RAG_FALLBACK_MODE=lexical_only
```

这种模式适合最小可运行调试：
- Agent Chat 可以自由聊天，也可以按路由判断进入项目问答
- 项目问答会使用本地 chunk 的关键词匹配
- Code Review 在 KB 命中不足时会退回当前文件内容和通用规则
- Code Generate 找不到代码参考时会直接让 LLM 生成

局限是语义召回较弱，例如“生成一个编辑器工具按钮”和“Editor Utility Widget 扩展”可能无法稳定匹配。后续补上 embedding 和 Qdrant 后，这类同义表达会更容易命中。

### 17.6.1 如何判断知识库是否真的参与回答

如果你觉得回答像是 LLM 自己的通用知识，可以先看 Debug View 或响应 JSON：

- `data.retrieved_docs`：非空说明本轮确实检索到了知识库 chunk。
- `data.citations`：普通 UI 可展示的引用来源。
- `debug_view.retrieval.retrieved_docs`：调试用检索详情。
- `data.answer_generation.mode`：`llm_synthesized` 表示 LLM 基于检索证据综合表达，`retrieval_summary_fallback` 表示直接返回检索摘要，`knowledge_catalog` 表示知识库目录回答。
- `data.answer_mode=knowledge_catalog`：说明用户问的是“知识库有哪些内容”这类目录问题。

常见理解方式：

- LLM 参与回答不等于知识库没用；如果 `retrieved_docs/citations` 有内容，说明 LLM 是在综合证据。
- 没有 embedding/Qdrant 时，中文问英文资料可能依赖关键词和轻量中英扩展，命中率不如向量检索。
- 知识库内容不足时，LLM 可以补充通用 UE 知识，但后端应在低证据时通过 citations / Debug View 让用户看清楚依据。

### 17.7 接入向量模型

当前 embedding 使用 OpenAI-compatible `/embeddings` 接口，复用以下配置：

```env
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=https://你的兼容服务/v1
EMBEDDING_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-large
```

如果你的服务地址是 `https://example.com/v1`，后端会调用：

```text
https://example.com/v1/embeddings
```

更换向量模型时建议：
- 修改 `EMBEDDING_MODEL`
- 调用 `POST /api/v1/knowledge-base/reindex`
- 如果向量维度变化，使用新的 `QDRANT_COLLECTION` 或让后端重建 collection

如果聊天模型和向量模型来自不同供应商，当前版本推荐先使用兼容同一 `OPENAI_BASE_URL` 的服务。后续可以把配置拆成 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`CHAT_BASE_URL`，但这是下一阶段增强，不是当前必需项。

### 17.8 接入 Qdrant 向量数据库

本地启动 Qdrant 的一种方式：

```powershell
docker run -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

`.env` 配置：

```env
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=ue_agent_default
RAG_MODE=hybrid
RAG_FALLBACK_MODE=local_hybrid_fallback
```

推荐每个 UE 项目使用独立 collection，例如：

```env
QDRANT_COLLECTION=rushba_local
```

这样不同项目的向量不会互相污染。Qdrant 可用、embedding 可用时，知识库会把 chunk 写入向量库；不可用时，后端会记录 degraded reason，并退回本地检索。

### 17.9 RAG 模式选择

`RAG_MODE` 控制检索策略：
- `lexical`：只使用本地词法检索，最稳、依赖最少
- `hybrid`：词法 + 向量综合排序，推荐默认值
- `semantic`：主要使用向量语义检索，适合资料量较多且 embedding 质量稳定时

`RAG_FALLBACK_MODE` 控制向量不可用时的退化方式：
- `lexical_only`：直接退回词法检索
- `local_hybrid_fallback`：本地词法 + 简单相似度混合，适合没有 Qdrant 但想要稍微更强的本地召回

推荐配置：
- 最小调试：`RAG_MODE=lexical`，`EMBEDDING_ENABLED=false`
- 本地演示：`RAG_MODE=hybrid`，`EMBEDDING_ENABLED=false`，走 lexical fallback，依赖最少
- 向量检索演示：`RAG_MODE=hybrid`，`EMBEDDING_ENABLED=true`，接入 Qdrant
- 资料很多且表达差异大：`RAG_MODE=semantic` 或 `hybrid`

### 17.10 各 Skill 如何使用知识库

`ProjectQASkill`：
- 先判断用户是在普通聊天还是项目问答
- 项目问答才检索知识库
- 回答中返回 citations 和 debug route

`CodeReviewSkill`：
- 文件扫描和读取属于内部 `collector`
- 优先基于当前文件内容做确定性规则扫描
- 再检索 `code_reference`、`team_rules`、`engine_notes`
- LLM 可用时进行综合审查；不可用时返回规则扫描结果

`CodeGenerateSkill`：
- 先检索 `code_reference` 和 `examples`
- 命中时把参考代码与用户需求一起给 LLM
- 未命中时由 LLM 直接生成代码
- 前端以“需求消息下挂代码结果按钮”的方式展示

`LogsAnalyzeSkill`：
- 日志采集由 UE 端或脚本完成
- 后端接收日志文本、错误片段或显式日志文件路径后做模式识别和 LLM 分析
- 如果知识库里有历史错误记录，可检索 `incident_history`

`AssetsInspectSkill`：
- 接收 UE 端选中资产的元数据
- 本地检查命名、类型、依赖、引用关系
- 可检索 `asset_rules` 和 `team_rules` 补充解释

### 17.11 查看本次任务对应的 Skill

每次任务响应都会带上 Skill runtime 信息，主要用于 Debug View 和前后端联调：

```json
{
  "debug_view": {
    "skill": {
      "skill_id": "CodeReviewSkill",
      "collector": "ue_project_code_file_scanner_and_reader",
      "rules": ["file_access_guard", "ue_cpp_lifecycle_checks"],
      "retrieval_domains": ["code_reference", "team_rules", "engine_notes"],
      "retrieval_active": true,
      "retrieval_mode": "hybrid",
      "projector_outputs": ["user_view.blocks", "data.review_scope"]
    }
  },
  "trace_summary": {
    "skill_id": "CodeReviewSkill"
  }
}
```

字段含义：
- `skill_id`：本次任务对应的固定内置 Skill
- `collector`：后端如何收集输入，例如聊天消息、UE 源码文件、日志文本或资产元数据
- `rules`：该 Skill 的确定性规则层
- `retrieval_domains`：该 Skill 推荐检索的知识库 domain
- `retrieval_active`：这次任务是否真的触发检索
- `retrieval_mode`：这次检索使用的模式；没有检索时通常是 `not_used`
- `projector_outputs`：前端优先消费哪些稳定输出字段

如果是延期兼容任务，`skill_id` 可能为 `null`，并显示 `status=deferred_or_legacy`。这说明该任务不是当前 5 个核心 Skill 之一。

当前执行层迁移状态：
- `CodeReviewSkill` 已经使用独立 executor，代码审查的本地化投影和 LLM 综合审查 prompt 也已迁入该 executor
- `CodeGenerateSkill` 已经使用独立 executor，代码生成的结果投影、引用预览和调试字段由 executor 统一组装
- `LogsAnalyzeSkill` 已经使用独立 executor，日志结构化结果、上下文块和历史案例检索投影由 executor 统一组装
- `AssetsInspectSkill` 已经使用独立 executor，资产规则、本地化问题、重命名建议、类型和关系摘要由 executor 统一组装
- `ProjectQASkill` 仍由 `TaskService` 内部方法编排，因为它与聊天路由、普通对话降级和上下文管理耦合更高
- 这属于后端内部结构优化，不改变 API 请求体或前端 UI 契约

### 17.12 LangSmith 配置说明

当前后端保留了 LangSmith 配置字段：

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ue-agent-dev
```

当前实现是 `langsmith_stub`：它会在 `trace_summary` 里记录 `trace_id`、`route_type`、`finish_reason`、`langsmith_project` 等调试信息，但还没有真正把 span 上传到 LangSmith 平台。因此现在即使填了 `LANGSMITH_API_KEY`，主要作用仍是为后续真实 tracing 预留配置。

后续如果要接入真实 LangSmith，建议按这些步骤增强：
- 在 route、collector、retrieval、llm、projector 周围创建 trace span
- 记录输入摘要，不直接上传完整源码或敏感日志
- 把 `trace_id` 回填到 `debug_view`
- 在 LangSmith 项目里观察检索命中、LLM 延迟、JSON 解析失败率、fallback 次数

### 17.13 常见问题排查

知识库没有命中：
- 先看 `GET /api/v1/knowledge-base/status`
- 确认 `document_count` 和 `chunk_count` 是否大于 0
- 确认导入文档的 domain 是否符合当前 Skill
- 只接 LLM 时把 `RAG_MODE` 改成 `lexical` 更容易定位问题

向量不可用：
- 确认 `EMBEDDING_ENABLED=true`
- 确认 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`EMBEDDING_MODEL`
- 确认 Qdrant 地址可访问
- 调用 `POST /api/v1/knowledge-base/reindex`

PDF/DOCX 导入失败：
- 先把内容转成 Markdown 或 HTML 验证 pipeline
- 再安装并验证 `docling` 或 `unstructured`
- 避免一次导入过大的文件，必要时提高 `KB_MAX_FILE_BYTES`

代码生成没有参考项目代码：
- 把示例代码导入为 `code_reference` 或 `examples`
- 在 metadata 里补 `language`、`module`
- 重新导入或重建索引

Agent Chat 总是检索：
- 确认当前问题是否明显包含项目、文件、模块、UE 术语
- 普通寒暄和开放聊天应走 `direct_answer`
- 如果仍异常，查看 `debug_view.route` 和 `trace_summary.route_type`

### 17.14 UE 官方文档补充到知识库的合规做法

推荐只补充公开可访问的 Epic / Unreal Engine 官方文档页面，并且把它们当作本地 RAG 检索资料，而不是训练数据。

当前可执行原则：

- 只抓取公开文档页，优先 `https://dev.epicgames.com/documentation/` 下的 Unreal Engine 文档。
- 不抓取登录、搜索、账户、过滤器、portal 一类页面；`https://dev.epicgames.com/robots.txt` 当前明确限制了这些路径，并提供了文档 sitemap。
- 不把抓取到的 Epic 内容用于模型训练、微调或任何“模型会从输入继续学习”的流程。保持在本地知识库检索、引用和摘要范围内即可。
- 控制抓取频率，保留原始来源 URL、标题和抓取时间，便于后续删除或更新。
- 对本地开源项目，优先使用“官方文档摘要 + 原始链接”方式入库；不要把整站镜像直接塞进仓库。

推荐先补这些官方主题：

- Unreal Engine Programming Quick Start
  - https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-cpp-quick-start
- Programming with C++
  - https://dev.epicgames.com/documentation/en-us/unreal-engine/programming-with-cplusplus-in-unreal-engine
- Blueprints Visual Scripting
  - https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprints-visual-scripting-in-unreal-engine
- Nanite Virtualized Geometry
  - https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
- Asset Registry
  - https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine

推荐落地方式：

1. 先把这些页面整理成你自己的 Markdown / HTML 摘要笔记，保留官方链接。
2. 存到例如 `knowledge/engine_notes/unreal_official/`。
3. 调用 `POST /api/v1/knowledge-base/refresh` 或把该路径加入 `KB_SOURCE_PATHS`。
4. domain 建议使用 `engine_notes`，metadata 里补 `source=epic_official_docs`、`captured_at`、`original_url`。

如果你后面要做“合法合规爬取脚本”，建议边界也保持简单：

- 输入：一组明确的官方 URL 白名单
- 输出：本地 `.html` 或 `.md` 文件
- 规则：限速、失败重试、记录 `original_url`
- 禁止：全站镜像、登录态抓取、搜索页抓取、训练数据导出

## 18. 2026-04-23 联调字段补充

### 18.1 Project Inventory Snapshot 响应

UE 插件提交项目快照时，后端会保存资产和代码索引，并返回稳定摘要。请求体建议包含：

- `project_id` / `project_name`
- `snapshot_time`
- `source`
- `plugin_version`
- `assets`
- `code_files`
- `scan_diagnostics`

代码文件时间字段可传 `last_modified` 或 `modified_at`，后端会同时保留这两个别名，方便前端列表和 Debug View 复用。

`freshness` 是运行时计算字段，不要求 UE 前端改变提交格式：

- `status=fresh`：快照仍在 `PROJECT_INVENTORY_STALE_AFTER_SECONDS` 阈值内。
- `status=stale`：快照已超过阈值，回答仍可用但应提示用户重新同步。
- `status=missing`：当前 project 没有快照。
- `status=unknown`：快照时间无法解析，建议重新同步。

成功响应示例：

```json
{
  "success": true,
  "snapshot": {
    "status": "saved",
    "snapshot_id": "rushba_2026-04-23T100000Z",
    "project_id": "rushba",
    "asset_count": 2,
    "code_file_count": 1,
    "summary": {
      "asset_count": 2,
      "code_file_count": 1,
      "asset_type_counts": {"StaticMesh": 1, "Blueprint": 1},
      "code_file_type_counts": {"cpp": 1},
      "freshness": {
        "status": "fresh",
        "should_refresh": false,
        "stale_after_seconds": 300
      }
    },
    "freshness": {
      "status": "fresh",
      "should_refresh": false,
      "stale_after_seconds": 300
    },
    "scan_diagnostics": {
      "asset_count_from_editor": 2,
      "code_file_count_from_scanner": 1
    }
  }
}
```

### 18.2 LLM Analysis 字段含义

Code Review 和 Assets Inspect 都会返回 `llm_analysis`。它是给用户看的“综合解释卡片”，不是替代规则结果。

字段含义：

- `status`：`completed` 表示 LLM 已综合解释；`skipped` 表示未执行在线 LLM。
- `reason`：本地化自然语言原因，适合直接展示给用户。
- `reason_code`：稳定机器可读原因码，适合前端调试和条件样式。
- `text`：卡片正文。
- `key_points` / `recommendations`：可选要点。
- `priority`：`low` / `medium` / `high`。

常见 `reason_code`：

- `missing_openai_api_key`
- `missing_chat_model`
- `json_parse_failed`
- `request_failed`
- `file_read_failed_or_empty_source`
- `empty_asset_selection`
- `not_attempted`

如果只配置了 LLM，Code Review / Assets Inspect 会尝试在线综合解释；如果未配置或调用失败，仍会返回确定性规则扫描、知识库引用和建议。前端不应把 `status=skipped` 展示成任务失败。

### 18.3 Session History 恢复顺序

后端现在会把每次 `assistant_message` 也写入 session history，`GET /api/v1/sessions/{session_id}/history` 返回的消息顺序以数据库为准，稳定按 `created_at + message_id` 排序。

这意味着：

- 会话恢复后，历史通常应呈现为 `user -> assistant -> user -> assistant`
- 前端恢复历史时不需要再按本地“发送时间”二次重排
- 同一次会话的后续请求，直接把后端返回的 history 当作权威历史，再在末尾追加新的 user 消息即可
- 工具型任务（Code Review、Code Generate、Logs Analyze、Assets Inspect）不会写入 Agent Chat session history；它们只进入 task 列表和 Debug/Trace 数据，避免污染后续自由聊天上下文

### 18.4 Agent Chat 项目级 Inventory 工具选择

用户在自由聊天里问项目事实时，后端会像判断是否需要知识库一样判断是否需要 Project Inventory。例如：

- “当前项目有哪些蓝图资产？”
- “项目里哪些 StaticMesh 开启了 Nanite？”
- “这个工程里有哪些材质资产？”
- “Gameplay 模块下有哪些 C++ 文件？”

这类请求仍然调用：

```http
POST /api/v1/chat/runs
```

后端会返回：

- `intent.route_type = "project_qa"`
- `debug_view.route.selected_tool_id = "query_project_inventory"`
- `data.inventory`
- `debug_view.inventory`
- `data.tool_plan`
- `debug_view.tool_plan`

如果是纯项目事实查询，后端可以跳过知识库检索，只查询 Project Inventory。如果问题还包含“为什么、怎么做、规范、风险、建议”等解释性需求，后端会组合 `query_project_inventory` 和 `retrieve_project_knowledge`。

Assets Inspect 的边界保持不变：它只分析 Content Browser 里当前选中的资产和该面板提交的 inspection 要求，不负责项目级资产盘点。

### 18.5 Code Review / Assets Inspect 的 LLM 超时优化

如果你已经配置了 LLM，但之前经常看到：

- `data.llm_analysis.status = "skipped"`
- `data.llm_analysis.reason_code = "request_failed"`

这轮后端已经做了两类优化：

- 压缩 Code Review / Assets Inspect 的 LLM prompt 负载
- 对这两类任务单独放宽 timeout，并收紧 `max_tokens`

如果后续仍频繁出现 `request_failed`，优先检查：

- `OPENAI_BASE_URL`
- `CHAT_MODEL`
- 当前模型供应商的响应延迟
- 本机到模型服务的网络连通性

### 18.6 Inventory 空结果与 Code Review LLM 排查

Agent Chat 的项目事实问题现在会优先走 Project Inventory。常见中文问法，例如“我当前项目的蓝图资产有哪些，你列一下”和“当前项目蓝图资产有哪些”，都会进入 `project_qa`，并在 `debug_view.route.selected_tool_id` 中标记为 `query_project_inventory`。

如果回答提示没有 Project Inventory 快照，请先在 UE 插件 Debug View 点击 `Submit Inventory`。后端会在 `data.inventory.summary.empty_reason` 给出稳定原因：

- `no_project_inventory_snapshot`：当前项目还没有提交快照。
- `no_matching_inventory_items`：快照存在，但没有匹配到本次查询。

Code Review 判断是否真的读到了 cpp/h/cs 文件，优先看 `data.review_scope`：

- `read_status = "ok"` 且 `content_length > 0`：后端已经读取到选中文件内容。
- `read_status = "inline"` 且 `content_length > 0`：前端直接传了源码文本，后端已用该文本审查。
- `source_kind = "query_only"` 或 `llm_analysis.reason_code = "missing_selected_code_content"`：请求缺少可解析的选中文件内容，通常需要前端补齐 `payload.project_root + payload.file_path`。
- `source_field`：本次后端实际识别到的字段，例如 `file_path`、`relative_path`、`content`，可用于排查 UE 端传参。
- `llm_review.reason = "completed_text_fallback"`：LLM 已返回内容但未严格按 JSON schema 返回，后端会尽量修复常见 JSON-like 格式；如果仍不合法，也会尝试从原文提取 summary / issue / suggestion 放入 `llm_analysis.text`，状态仍是 `completed`。
- `llm_review.fallback_mode = "compact_text_retry"`：首轮结构化 Code Review LLM 请求失败后，后端使用更短的自然语言复核 prompt 再请求一次 LLM。该路径用于解决长文件、JSON-only 输出不稳定或模型端拒绝结构化响应时“LLM 已连接但 Code Review 显示 skipped”的问题。
- 如果 `llm_analysis.status = "skipped"`，优先查看 `llm_review.reason/error/fallback_result`。`request_failed` 通常表示模型接口、代理、超时或模型上下文长度问题；`missing_selected_code_content` 则表示前端没有给到可读源码。

### 18.7 Code Review 高亮展示与 raw JSON 边界

Code Review 是工具面板，不是聊天面板。前端的高亮按钮应展示 `user_view.blocks` 中的自然语言字段：

- `summary.text`：审查概要
- `llm_analysis.text`：LLM 综合解释
- `llm_analysis.data.key_points`：LLM 要点
- `issues.data.items`：问题列表
- `recommendations.data.items`：建议列表
- `references.data.items`：依据
- `next_steps.data.items`：下一步

不要把 `data.llm_review`、`debug_view.raw_result`、artifact 原始内容或 `analysis_input.source_excerpt` 放进普通用户高亮弹窗。这些属于 Debug View，可能包含原始 JSON、源码片段和模型诊断。

后端现在会尽量保证 `user_view.blocks[].text` 和 `data.llm_analysis.text` 是自然语言。如果 LLM 返回 JSON-like 文本但没有严格符合 schema，后端会先尝试修复常见格式问题，例如 Markdown 代码块、尾逗号、未加引号的 key、单引号字典；如果修复失败，会继续从原文提取 summary / title / reason / suggestion，原始内容只保留在 `data.llm_review.text` 供 Debug 使用。

### 18.8 输出语言偏好

后端当前支持 `zh-CN` 和 `en-US` 两种用户可见输出语言，默认是 `zh-CN`。推荐 UE 插件前端提供 `中文 / English` 切换按钮，并把选择写入每次请求的 `runtime_options.preferred_output_language`。

最小请求示例：

```json
{
  "runtime_options": {
    "preferred_output_language": "zh-CN"
  }
}
```

英文模式：

```json
{
  "runtime_options": {
    "preferred_output_language": "en-US"
  }
}
```

后端语言优先级如下：

- 用户消息里显式说“用英文回答 / 用中文回答”或 `reply in English / reply in Chinese`
- `runtime_options.preferred_output_language`
- session 保存的语言偏好
- `context.editor_state.locale`、`culture`、`editor_locale` 等编辑器语言字段
- 默认 `zh-CN`

`auto` 仍然兼容，但不再表示“跟随用户输入语言”。如果用户用英文提问但前端没有传 `en-US`，后端仍会默认用中文回答。这是为了让插件体验和用户选择保持一致，而不是让模型根据每句话自行漂移。

会被本地化的内容包括：

- `assistant_message`
- `user_view.text`
- `user_view.blocks[].title/text`
- `data.llm_analysis.text`
- 面向用户的 `reason`、`suggestion`、`summary`、`recommendations`

不会被强制本地化的内容包括：

- Debug View
- API 字段名
- 枚举值和 `reason_code`
- 文件路径、代码符号、类名、函数名
- raw JSON 和 artifact 原文

如果希望在创建或恢复 session 时先保存语言偏好，可以调用：

```http
POST /api/v1/sessions
```

```json
{
  "session_id": "rushba_agent_chat",
  "project_name": "RushBa",
  "preferred_output_language": "zh-CN",
  "profile_id": "default"
}
```

响应里的 `locale` 可用于调试：

- `detected_input_language`：检测到的输入语言
- `preferred_output_language`：本轮偏好语言
- `final_output_language`：最终输出语言
- `language_source`：`explicit_override`、`message_override`、`session_preference`、`editor_locale` 或 `default`

### 18.9 Context Bundle v1

后端现在有一层统一的 `Context Manager`，每次任务会先生成 `context_bundle_v1`，再交给 Agent Chat、Project QA 或工具型 Skill 使用。它的目标不是把所有历史都塞进 prompt，而是把“本轮为什么带了这些上下文”讲清楚。

主要字段：

- `debug_view.context_bundle.version`：当前为 `context_bundle_v1`。
- `debug_view.context_bundle.input_summary`：本轮 session、请求类型、实际任务类型、route type、latest user message。
- `debug_view.context_bundle.recent_messages`：最近的 Agent Chat / Project QA 对话，已经去重和截断。
- `debug_view.context_bundle.editor_context`：当前 UE project、panel、file、module、selected assets 等摘要。
- `debug_view.context_bundle.tool_context`：最近工具型任务摘要，例如 Code Review，不会污染聊天历史。
- `debug_view.context_bundle.session_summary`：阶段 B 之前主要读取 session metadata 中已有摘要；没有则显示 `not_available`。
- `debug_view.context_bundle.long_term_memory`：项目/会话长期记忆，字段保持旧版本兼容。
- `debug_view.context_bundle.web_memory`：当 `WEB_MEMORY_ENABLED=true` 时注入的 Web Search 摘要缓存，用于复用近期高质量外部资料。
- `debug_view.context_bundle.memory.sources`：统一记忆来源诊断，当前包含 `session_long_term_memory`、可选 `local_file_memory` 和可选 `web_memory`。
- `debug_view.context_bundle.budget`：字符预算、估算字符数、裁剪策略和 warnings。
- `debug_view.memory_summary.context_budget`：Debug View 中更短的预算摘要，方便快速判断是否接近上下文限制。

当前边界：

- 工具型任务不会写入 `/sessions/{session_id}/history`，只写入 task 列表和 tool context 摘要。
- 第一版不做自动长期记忆总结，不做复杂 graph，也不做多 agent 上下文共享。
- Web Memory 注入上下文时仍保持独立来源，不视为正式知识库证据；如果回答需要严格引用项目文档，仍优先看 RAG/local grep/project inventory。
- 如果需要看某次请求到底带了哪些上下文，优先打开 `debug_view.context_bundle`，不要从 raw prompt 反推。

### 18.9.1 Context Pack v1

2026-06-02 update: the backend now builds `context_pack_v1` on top of the
existing `context_bundle_v1`.

Purpose:

- `context_bundle_v1` remains the full compact context contract for backward compatibility.
- `context_pack_v1` is the structured prompt/debug projection used by the Agent layer.
- It separates context into `system_layer`, `project_layer`, `active_layer`,
  `conversation_layer`, `knowledge_layer`, `memory_layer`, `tool_layer`, and
  `budget_layer`.
- It does not change public APIs, Proposal safety, or UEAgentTool execution.

Where to inspect:

- `debug_view.context_pack`
- `data.context_pack`
- `debug_view.context_bundle.context_pack`
- `debug_view.agent_decision_trace.decisions.context_decision.details.context_pack_version`

Current behavior:

- Memory selection is deterministic and non-LLM: the backend ranks compact
  memory/cached evidence snippets by lexical overlap and existing provider score.
- `tool_layer.tool_observation_summary` keeps recent tool task summaries
  separate from chat history.
- `tool_layer.recent_editor_operations` keeps recent confirmed UE operations
  available as active context without injecting full raw result JSON into the prompt.
- `active_layer.blueprint` and `active_layer.editor_focus` keep the current
  Blueprint path, graph name, selected node id/name, and focused editor panel
  when the UE frontend or payload provides them.
- `system_layer` records the important Agent boundary: LLMs can reason and
  propose, but confirmed UE writes still require Proposal confirmation.

Why this matters:

- It gives ReAct Lite, future LangGraph-compatible orchestration, and
  Multi-Agent Lite a clean input object.
- It makes context compression explainable in Debug View.
- It keeps the frontend stable while improving backend Agent architecture.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_context_pack.py tests\unit\test_memory_providers.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_system_and_tasks.py::test_project_qa_returns_confidence_and_citations tests\integration\test_system_and_tasks.py::test_direct_chat_with_project_context_still_skips_kb_when_query_is_generic -q
```

### 18.10 Memory Summary v1

后端现在会为较长的 Agent Chat / Project QA 会话生成轻量 memory summary。它不是用户画像，也不是跨项目长期记忆，只是当前 session 内的上下文压缩。

触发方式：

- 仅 `agent_chat` / `project_qa` 这类聊天历史任务会触发。
- 工具型任务仍然不会写入聊天历史，也不会直接进入 memory summary。
- 当前阈值是聊天历史达到 8 条消息后生成或刷新摘要。
- 摘要使用确定性压缩策略，不依赖 LLM，因此本地调试时没有额外模型成本。

查看位置：

- `GET /api/v1/sessions/{session_id}` 的 `item.memory_summary`
- `debug_view.memory_summary.updated_session_memory`
- 下一轮请求中的 `debug_view.context_bundle.session_summary`

关键字段：

- `version = "memory_summary_v1"`
- `strategy = "deterministic_recent_compaction_v1"`
- `summary_text`：压缩后的旧对话摘要。
- `message_count`：当前 session 消息总数。
- `summarized_message_count`：被压进摘要的旧消息数量。
- `recent_message_count`：仍保留为 recent messages 的消息数量。

边界：

- 清空 session 会同时清掉旧 `memory_summary`。
- 这版不做 LLM 自动总结、不保存跨项目用户偏好、不把代码全文或资产元数据写入 memory。
- 如果需要更聪明的摘要，后续可以在不改变前端主 UI 的前提下升级策略。

### 18.11 Agent Decision Trace v1

后端现在会在每次任务响应的 Debug View 中返回一条统一决策链：

```json
{
  "debug_view": {
    "agent_decision_trace": {
      "version": "agent_decision_trace_v1",
      "summary": {
        "route_type": "direct_answer",
        "skill_id": "ProjectQASkill",
        "retrieval_mode": "not_used",
        "memory_status": "not_triggered",
        "finish_reason": "completed"
      },
      "decisions": {}
    }
  }
}
```

`decisions` 固定包含这些分区：

- `input_summary`：本轮请求、最新用户消息和编辑器上下文摘要。
- `language_decision`：最终输出语言和语言来源。
- `intent_decision`：为什么走 direct answer、Project QA、Inventory 或某个 Skill。
- `context_decision`：Context Bundle 使用了多少 recent messages、tool context、session summary，以及是否超预算。
- `retrieval_decision`：本轮是否检索、检索模式、命中数量、是否降级。
- `tool_decision`：本轮映射到哪个固定内置 Skill。
- `memory_decision`：本轮 session memory 是 available、not_triggered 还是 not_available。
- `fallback_decision`：是否有 warnings/errors 导致降级。
- `final_response_plan`：最终如何投影到 user view、debug view、trace 和 artifacts。

边界：

- Decision Trace 不额外调用 LLM，只汇总后端已有判断。
- 普通用户界面不需要展示完整 trace。
- 调试展示或排查“为什么这次走 RAG / 为什么没走 RAG / 为什么 LLM skipped”时，优先看这里。

### 18.11.1 Multi-Agent Lite Role Trace

2026-06-02 update: every task response now includes a framework-neutral
`multi_agent_lite_trace_v1` diagnostic.

Where to inspect:

- `debug_view.multi_agent_lite`
- `data.multi_agent_lite`

Roles:

- `coordinator`: route the request and assemble context.
- `researcher`: collect evidence from RAG, local search, project inventory,
  session/file/web memory, or cached sources.
- `planner`: select a skill, read-only tool plan, or pending Proposal plan.
- `executor`: execute only confirmed write-side Proposals through UEAgentTool.
- `reviewer`: expose lightweight self-reflection / quality diagnostics.

Boundary:

- It does not launch multiple LLM calls.
- It does not run a parallel swarm.
- It does not bypass Proposal confirmation.
- It is a stable trace format for future LangGraph-compatible orchestration or
  real Multi-Agent services.

### 18.11.2 ReAct v2 Display Trace

2026-06-02 update: every task response now includes `react_v2_trace_v1`.

Where to inspect:

- `debug_view.react_trace`
- `data.react_trace`

Flow:

```text
input
  -> thought_summary
  -> plan_summary
  -> observation_summary
  -> reflection_summary
  -> validation_summary
  -> final
```

Boundary:

- `react_trace` is display-safe and does not expose raw chain-of-thought.
- It is a diagnostic projection of the current deterministic/LLM-assisted
  execution, not a permission to auto-run write tools.
- Existing `react_loop` remains backward compatible for Project QA / workflow
  traces. Prefer `react_trace` for the new full-task Debug View summary.
- Write operations still create at most one pending Proposal per turn and still
  require UEAgentTool confirmation.
- `validation_summary` records display-safe contract diagnostics only:
  tool input/result contract counts, failed contract counts, warning count,
  output completion marker, Proposal count, and whether the final projection
  passed these lightweight checks.
- UEAgentTool does not need a UI change for this stage. The field is already
  available in `debug_view.react_trace` and `data.react_trace` for optional
  inspection.

### 18.12 RAG Readiness 与本地评测

`GET /api/v1/knowledge-base/status` 现在会返回 `rag_readiness`，用于判断知识库当前到底能不能服务 Project QA。

关键字段：

- `status`：`empty`、`ready` 或 `degraded`。
- `lexical_ready`：本地词法检索是否可用。
- `embedding_ready`：embedding 模型是否可用。
- `vector_store_ready`：向量数据库是否可用。
- `usable_for_project_qa`：Project QA 是否至少可以用词法检索工作。
- `degraded_reasons`：为什么降级，例如 embedding 不可用或 Qdrant 不可用。
- `domain_counts`：当前知识库每个 domain 有多少文档。
- `indexed_documents` / `indexed_chunks`：当前入库规模。
- `eval_command`：推荐本地评测命令。

只配置 LLM、没有配置 embedding / Qdrant 时，常见状态是：

```json
{
  "status": "degraded",
  "lexical_ready": true,
  "embedding_ready": false,
  "vector_store_ready": false,
  "usable_for_project_qa": true
}
```

这不是错误，表示 RAG 会降级到本地词法检索。

本地 RAG 评测命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --dataset tests\eval\rag_project_qa_dataset.jsonl --markdown-output storage\artifacts\evals\local-rag-eval-smoke.md
```

评测 summary 会包含：

- `recall_at_k`
- `precision_at_k`
- `precision_at_retrieved`
- `labeled_precision_ceiling`
- `normalized_precision_at_k`
- `hit_at_k`
- `top1_accuracy`
- `mrr`
- `ndcg_at_k`
- `route_accuracy`
- `language_accuracy`
- `citation_coverage`
- `low_confidence_ratio`
- `no_result_ratio`

如果加上 `--markdown-output`，脚本会额外生成本地 Markdown 报告，方便查看每条 case 的路由、语言、命中来源和核心指标。

### 18.13 Skill Protocol v1

后端现在把 5 个核心能力收敛成固定内置 Skill，而不是动态插件市场：

- `ProjectQASkill`：Agent Chat / Project QA，自由聊天、项目问答、知识库检索、Project Inventory 查询都从这里进入。
- `CodeReviewSkill`：代码审查，负责 UE 工程源码扫描、选中文件读取、规则检查、KB 证据和可选 LLM 分析。
- `CodeGenerateSkill`：代码生成，负责根据需求和 `code_reference/examples/engine_notes` 生成代码草案。
- `LogsAnalyzeSkill`：日志分析，负责日志文本 / 文件窗口提取、严重性归类、签名识别和建议生成。
- `AssetsInspectSkill`：资产检查，负责选中资产的命名、类型、依赖关系、常用设置和可选 LLM 分析。

查看 Skill catalog：

```http
GET /api/v1/system/capabilities
```

重点字段：

- `capabilities.skill_architecture.protocol_version = "skill_protocol_v1"`
- `capabilities.skill_architecture.protocol_components = ["collector", "rules", "retrieval", "llm_analyzer", "projector"]`
- `capabilities.skill_architecture.runtime_lifecycle_field = "debug_view.skill.lifecycle"`
- `capabilities.skill_catalog[]`：每个 Skill 的 manifest。

一次任务执行后，可以在 Debug View 里查看运行态：

```json
{
  "debug_view": {
    "skill": {
      "protocol_version": "skill_protocol_v1",
      "skill_id": "CodeReviewSkill",
      "lifecycle": {
        "collector": {"status": "completed"},
        "rules": {"status": "completed"},
        "retrieval": {"status": "completed"},
        "llm": {"status": "skipped", "reason": "missing_openai_api_key"},
        "projector": {"status": "completed"}
      }
    }
  }
}
```

五段生命周期的含义：

- `collector`：收集输入，例如聊天消息、UE 选中文件、资产 metadata、日志文本。
- `rules`：确定性规则，例如 C++ 生命周期检查、命名规范、日志严重性分组。
- `retrieval`：知识库或项目快照检索，例如 KB chunks、Project Inventory、代码参考。
- `llm`：在线 LLM 综合分析；没有 API Key、缺少选中文件内容或模型不可用时会 `skipped/degraded`。
- `projector`：把内部结果投影成 `user_view`、`debug_view`、`data`、`artifacts` 等前端可消费结构。

后续优化功能时的推荐边界：

- 优先扩展现有 Skill，不轻易新增一个用户可见功能入口。
- 新增“扫描 UE 工程 cpp/h/cs 文件并读取内容”这类能力，应归入 `CodeReviewSkill.collector`。
- 新增“代码审查规则”应归入 `CodeReviewSkill.rules`。
- 新增“把审查结果交给 LLM 解释成人话”应归入 `CodeReviewSkill.llm_analyzer`。
- 新增“高亮按钮、摘要卡片、建议列表字段”应归入 `CodeReviewSkill.projector`。
- 不做动态安装 Skill、不做 marketplace、不做复杂沙箱；这是本地开源 Agent 项目，目标是稳定、清晰、可讲。

### 18.14 本地学习文档入口

如果要系统复习这个后端，可以在本地另建私有学习目录保存开发过程文档。它们不随公开仓库发布：

- 本地私有学习文档：不随公开仓库发布，可用于理解整体 Agent loop、模块边界和项目讲解方式。
- 请求生命周期复盘：用真实请求复盘 Agent Chat、Project QA、Code Review 等路径。
- RAG 与记忆复盘：理解知识库、检索、向量模型、Qdrant 和上下文压缩。
- Skill 扩展复盘：记录后续如何扩展固定内置 Skill。

这些文档不要求 UE 前端实现新 UI，主要用于后端学习、复盘和本地项目总结。

### 18.15 Local Grep Retrieval v1

后端现在支持本地 markdown/code grep 检索，作为向量 RAG 之外的稳定补强。它不依赖 embedding、不依赖 Qdrant，也不依赖系统 `grep` 或 `rg`，而是用 Python 在 `KB_SOURCE_PATHS` 指向的文件中检索。

适用场景：

- `Code Generate`：优先检索 `code_reference`、`examples`、`engine_notes`，把命中的代码/笔记片段交给 LLM 或模板兜底。
- `Project QA`：当现有 RAG 没有命中文档时，fallback 到本地 markdown/code grep。
- `Code Review`：通过知识检索补充 `team_rules`、`engine_notes`、`project_docs`、`examples`。

默认知识路径现在包含：

```env
KB_SOURCE_PATHS=./knowledge
```

这意味着 `backend.md`、`forward.md`、`docs/improveplan.md`、`docs/frontend-unified-handoff.md` 这类后端开发/交接文档默认不再进入用户可见知识库。它们仍然是开发资料，但不应该被 Agent Chat 当作 UE 项目知识来引用。

如果你之前用旧默认路径启动过后端，数据库里可能已经保存了旧文档索引。修改 `.env` 后需要重启后端并重建知识库：

```http
POST /api/v1/knowledge-base/reindex
```

也可以在 Debug View / Monitor 里调用同等的重建入口。完成后再查看：

```http
GET /api/v1/knowledge-base/documents
```

确认来源路径只剩 `knowledge/` 或你手动导入的 UE 项目资料。

推荐目录：

```text
knowledge/
  engine-notes/
  project-docs/
  code-reference/
  examples/
  asset-rules/
  team-rules/
```

目录会映射为 domain：

- `engine-notes` -> `engine_notes`
- `project-docs` -> `project_docs`
- `code-reference` -> `code_reference`
- `examples` -> `examples`
- `asset-rules` -> `asset_rules`
- `team-rules` -> `team_rules`

状态查看：

```http
GET /api/v1/knowledge-base/status
```

重点字段：

- `summary.local_search_readiness.status`
- `summary.local_search_readiness.searchable_files`
- `summary.local_search_readiness.domain_counts`
- `summary.local_search_readiness.source_paths`

任务响应里的 Debug 字段：

- `debug_view.local_search`
- `debug_view.retrieval.local_search`
- `data.local_search`
- `data.reference_lookup.local_reference_count`

本地 UE 知识种子已经放在 `knowledge/` 目录下，包括 Actor 生命周期、软引用/异步加载、StaticMesh/Nanite/LOD/Collision、模块与 Build.cs、Enhanced Input Character、交互组件、射线交互、GameInstanceSubsystem、DataAsset/GameplayTag 笔记、代码审查规则、资产检查规则、Actor/Component 代码参考示例和 Enhanced Input Character 示例。

### 18.16 常用 UE 代码知识库补充

Code Generate 的质量很依赖 `knowledge/code-reference` 和 `knowledge/examples` 的覆盖度。当前第一批补强主题是常见 UE gameplay / framework 代码：

- `knowledge/engine-notes/ue-enhanced-input-character.md`：说明 Enhanced Input 的常见结构、Mapping Context、Input Action、`SetupPlayerInputComponent` 和 Build.cs 依赖。
- `knowledge/code-reference/enhanced-input-character-example.h`：角色增强输入头文件参考。
- `knowledge/code-reference/enhanced-input-character-example.cpp`：角色增强输入绑定和移动/视角逻辑参考。
- `knowledge/examples/enhanced-input-buildcs-note.md`：`EnhancedInput` 模块依赖示例。
- `knowledge/engine-notes/ue-common-code-generation-patterns.md`：交互组件、射线交互、Subsystem、DataAsset、Gameplay Tags 的生成边界。
- `knowledge/code-reference/interaction-component-example.h/.cpp`：Overlap 交互组件参考。
- `knowledge/code-reference/line-trace-interaction-component-example.h/.cpp`：LineTrace 交互组件参考。
- `knowledge/code-reference/game-instance-subsystem-example.h/.cpp`：GameInstanceSubsystem 管理器参考。
- `knowledge/examples/dataasset-gameplaytag-note.md`：DataAsset + GameplayTag 配置驱动说明。

当前 Code Generate 基于内置模板和知识库，已经比较适合这些提问：

- “角色增强输入代码怎么写”
- “交互组件 overlap 怎么写”
- “射线交互组件怎么写”
- “GameInstanceSubsystem / 全局管理器子系统怎么写”
- “DataAsset 和 GameplayTag 配置驱动怎么组织”（当前主要返回知识参考和通用草稿，专用模板后续按测试反馈补）

使用方式：

1. 保持 `.env` 中 `KB_SOURCE_PATHS=./knowledge`。
2. 新增或修改 knowledge 文件后，调用 `POST /api/v1/knowledge-base/reindex`。
3. 在 Code Generate 中输入类似“角色增强输入代码怎么写”。
4. 前端应展示 `generated_items[].code`，而不是只展示文件名。

后续如果某类代码生成结果太空，优先补同类 `engine_notes` 和 `code_reference`，再考虑是否增强兜底模板。这样范围保持小而稳，不会变成复杂模板市场。

### 18.16.1 Code Generate Preflight

Code Generate 现在会在生成 `.h/.cpp` 草稿后自动运行轻量预检，输出：

- `data.preflight_report.status`：`passed`、`warning` 或 `failed`。
- `data.preflight_report.quality_score`：0-1 之间的启发式质量分。
- `data.preflight_report.summary`：检查文件数量、C++ 文件数量、warning/error 数量、是否存在 `.h/.cpp` 配对。
- `data.preflight_report.findings[]`：结构、路径、UE 反射、include、Enhanced Input 等问题提示。
- `debug_view.tools[].tool_id="preflight_generated_code"`：本轮是否执行预检。
- `step_results[].step_id="preflight_generated_code"`：预检步骤详情。

当前预检边界：

- 不调用 clang、UnrealHeaderTool 或 UE 编辑器。
- 不解析完整 C++ AST。
- 不证明代码一定能编译通过。
- 只作为复制代码前的静态烟测，帮助发现 `draft.txt`、路径不规范、缺少 `.generated.h`、缺少 `GENERATED_BODY()`、Enhanced Input 要素缺失等低级问题。

官方文档整理边界：

- 保留 `source_url`，但不整站爬取。
- markdown 内容以自己的总结和短笔记为主，不大段复制官方原文。
- 代码示例尽量使用自己改写的最小示例。
- 后续补充 UE 文档时，优先补到 `knowledge/engine-notes`、`knowledge/examples`、`knowledge/team-rules`。

### 18.17 UE C++ 蒸馏知识包 v1

后端现在新增了一批 UE C++ 蒸馏知识，来源是本地参考项目 `XG-UE-Cpp-Course-Skill-main` 的主题结构，但内容已经改写为本项目自己的知识笔记和最小代码参考，不直接复制课程原文。

新增内容覆盖：

- 反射宏、UObject、CDO、GC、UPROPERTY/UFUNCTION 选择。
- TArray / TMap / TSet 容器选择。
- 委托、字符串、定时器、GameplayTag。
- 多线程、AsyncTask、FRunnable、TaskGraph。
- HTTP、WebSocket、TCP 选型和模块依赖。
- Replication、RPC、GAS 基础架构。
- DeveloperSettings + Subsystem 配置模式。
- Code Review 可用的线程、网络、GAS、配置、委托规则。

这些文件统一放在：

```text
knowledge/
  engine-notes/
  examples/
  code-reference/
  team-rules/
  prompt-packs/
```

它们同时服务两种检索：

- 没有 embedding / Qdrant 时：本地 grep 和 lexical RAG 会读取 `KB_SOURCE_PATHS=./knowledge`。
- 配置 embedding / Qdrant 后：执行 reindex 后同一批文档会进入向量库。

常用命令：

```http
POST /api/v1/knowledge-base/reindex
GET /api/v1/knowledge-base/status
GET /api/v1/knowledge-base/documents
```

如果只是重启后端，且数据库还是空的，后端会自动 seed 一次默认知识库；如果数据库里已有旧索引，建议手动 reindex，确保新增 UE C++ 文档进入 chunks 和向量索引。

代码生成新增兜底场景：

- “HTTP 请求怎么写”：返回 `UBlueprintAsyncActionBase` 风格 HTTP 请求草稿，并提示 `HTTP/Json/JsonUtilities` 依赖。
- “WebSocket 长连接怎么写”：返回 `UGameInstanceSubsystem + IWebSocket` 草稿，并提示 `WebSockets` 依赖。
- “项目设置配置怎么写”：返回 `UDeveloperSettings` 草稿。
- “GAS 技能系统属性集怎么写”：返回 `UAttributeSet` 草稿，并提示 `GameplayAbilities/GameplayTags/GameplayTasks` 依赖。

边界：

- 这些仍然是非破坏性代码草稿，不会写入 UE 工程。
- 代码是否能直接编译仍需用户根据项目模块名、API 宏、include 路径和 Build.cs 依赖做确认。
- `prompt-packs/ue-cpp-practices.md` 是给 LLM 的领域行为指导，不是前端新菜单，也不是 ReAct Tool。

### 18.18 Agent Chat 的 UE 技术知识路由

当前内置知识库是蒸馏版，不是 `XG-UE-Cpp-Course-Skill-main` 的完整复刻。当前 `knowledge/` 约 29 个文件，外部参考仓库 `knowledge/` 约 283 个文件，所以覆盖量明显更少；这是为了保持开源项目的合规边界和可维护性。

后端已经补充 Agent Chat 的 UE 技术知识识别。用户在自由聊天中问以下类型问题时，会优先进入 `project_qa` 并选择 `retrieve_project_knowledge`：

- “GAS 技能系统是什么”
- “UE 多线程怎么做”
- “HTTP 请求怎么写”
- “反射宏怎么选”
- “TArray / TMap / TSet 怎么选”
- “网络同步 / RPC / 属性同步怎么做”

不配置 embedding / Qdrant 时，检索行为如下：

- `Agent Chat / Project QA`：先走数据库里的 lexical RAG；如果没有命中或显式要求本地搜索，再 fallback 到本地 markdown/code grep。
- `Code Generate`：优先使用本地 markdown/code grep 搜索 `code_reference / examples / engine_notes / prompt_packs`，再把证据交给模板或 LLM。
- `Code Review`：读取前端选中的真实代码文件，同时检索 `team_rules / engine_notes / project_docs / examples` 作为审查依据。

因此，如果 Debug View 中看到 `route.decision_source=heuristic_ue_knowledge_signal` 且 `route.selected_tool_id=retrieve_project_knowledge`，说明 Agent Chat 已经把 UE 技术问题路由到知识库，而不是纯 LLM 自由回答。

仍然需要注意：

- 知识库没覆盖的 UE 主题，LLM 可能会用自身通用知识补充回答。
- 如果 `retrieved_docs` / `citations` 为空，说明本轮没有找到可靠本地证据。
- 后续扩充知识库时，优先补 `engine_notes`、`examples`、`code_reference`，并给 RAG eval 增加对应 case。

### 18.19 本地私有全量知识源接入

本项目支持“公开原创蒸馏库 + 本地私有全量参考库”双轨模式：

- 公开仓库：只提交 `./knowledge` 下本项目自己整理的 UE 知识、规则和最小代码参考。
- 本地私有：使用者可在自己的 `.env` 中追加合法拥有的课程资料、团队文档或个人笔记路径。
- 后端机制：`KB_SOURCE_PATHS` 支持多个目录或文件，local grep、lexical RAG、后续 embedding + Qdrant 都会读取这些路径。
- 合规边界：不要把外部课程原文、私有团队资料或 `.env` 提交到 GitHub。

示例 `.env`：

```env
KB_SOURCE_PATHS=./knowledge,../XG-UE-Cpp-Course-Skill-main/knowledge,../XG-UE-Cpp-Course-Skill-main/.trae/skills/xg-uecpp-course/references
```

也可以使用 JSON 数组，适合路径里包含逗号的极端情况：

```env
KB_SOURCE_PATHS=["./knowledge","D:/PrivateKnowledge/uecpp/knowledge","D:/PrivateKnowledge/uecpp/references"]
```

接入步骤：

1. 把外部资料放在本机任意目录，不要放进本仓库并提交。
2. 在本地 `.env` 中追加路径到 `KB_SOURCE_PATHS`。
3. 重启后端。
4. 调用 `POST /api/v1/knowledge-base/reindex`。
5. 调用 `GET /api/v1/knowledge-base/status` 查看 `rag_readiness.domain_counts` 和 `local_search_readiness.searchable_files`。

可选扫描命令：

```powershell
.\.venv\Scripts\python.exe scripts\scan_knowledge_sources.py --markdown-output storage\artifacts\private-kb-scan.md
```

如果想临时扫描指定路径，不依赖 `.env`：

```powershell
.\.venv\Scripts\python.exe scripts\scan_knowledge_sources.py --source-path .\knowledge --source-path ..\XG-UE-Cpp-Course-Skill-main\knowledge --source-path ..\XG-UE-Cpp-Course-Skill-main\.trae\skills\xg-uecpp-course\references --markdown-output storage\artifacts\private-kb-scan.md
```

脚本输出说明：

- `file_count`：符合大小限制并可参与索引的文件数。
- `discovered_supported_files`：发现的受支持格式文件数。
- `domain_counts`：按 `engine_notes / examples / code_reference / team_rules / prompt_packs` 等 domain 统计。
- `suffix_counts`：按 `.md / .cpp / .h / .json` 等格式统计。
- `missing_sources`：路径不存在或不受支持时会列出。

这个扫描脚本不读取正文、不生成摘要、不复制私有资料，只帮助确认本地全量资料是否被后端看到。生成的报告建议放在 `storage/artifacts/`，该目录默认不提交。

## 19. 项目级 Benchmark 与量化结果

后端现在提供项目级 benchmark，用于本地质量评估和后续性能优化对比。它把 RAG、Agent 路由、工具型任务和接口耗时放到同一份报告中。

运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output storage\artifacts\evals\project-benchmark-latest.md
```

默认模式：

- `offline_fallback`：不调用 live LLM，适合可复现本地评估。
- `RAG_MODE=lexical`：benchmark 中关闭向量依赖，确保没有 embedding / Qdrant 也能跑。
- `source_paths=./README.md, ./docs, ./knowledge`：同时评估公开项目文档问答和 UE 知识库问答。
- benchmark 会把 `--source-path` 同步写入隔离运行时的 `KB_SOURCE_PATHS`，保证 RAG 主索引和 local grep fallback 搜同一批资料。
- 目录扫描默认跳过本地过程文档，例如 `docs/improveplan.md`、`docs/frontend-unified-handoff.md`、`docs/backend-dev-log.md`。如果确实要导入这些文件，需要显式把文件路径写进 `source_paths`。

如果要评估真实 LLM 链路：

```powershell
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --use-live-llm --markdown-output storage\artifacts\evals\project-benchmark-live.md
```

当前报告位置：

- `storage/artifacts/evals/project-benchmark-latest.md`
- `storage/artifacts/evals/hallucination-guard-latest.md`
- `storage/artifacts/evals/project-benchmark-latest.json`

当前 Hallucination Guard 报告重点：

- `cases=15`：覆盖证据不足拒答、通用 UE 知识命中、知识库目录回答三类问题。
- `grounding_accuracy=1.0`：离线 fallback 模式下，所有样例都符合预期 grounding 行为。
- `unsupported_answer_rate=0.0`：没有 Project Inventory 或没有专名证据时，不编造当前项目事实。
- `knowledge_catalog_accuracy=1.0`：用户问“知识库有哪些内容”时，只返回目录和用途，不把源码正文整段展开。

Project QA 的 grounding 边界：

- 当前项目事实类问题，例如“当前项目有哪些蓝图资产”“选中的 StaticMesh 是否开启 Nanite”，必须依赖 Project Inventory 快照。
- 如果没有快照或快照没有命中，后端会降低置信度并提示补充快照，不再把通用 UE 文档当成当前项目证据。
- 通用 UE 知识类问题，例如 Actor 生命周期、Enhanced Input、HTTP 模块依赖、软引用异步加载，仍然走知识库 / local grep / RAG，不会被 Inventory fallback 覆盖。
- 离线 fallback 回答会补充 `证据关键词`，便于用户和评测看到本轮命中的核心知识点；live LLM 可在这些证据基础上生成更自然的表达。

核心指标：

- `recall_at_k`：召回率，期望来源中有多少被 top-k 检索找回。
- `precision_at_k`：严格 top-k 精确率，相关命中数除以配置的 `top_k`。当数据集每条只标 1 个期望来源且 `top_k=4` 时，即使命中第一名，上限也只有 `0.25`。
- `precision_at_retrieved`：相关命中数除以实际去重后的检索来源数，更适合观察本地 lexical RAG 是否混入过多无关文档。
- `labeled_precision_ceiling`：当前标注密度下 `precision_at_k` 的理论上限。
- `normalized_precision_at_k`：`precision_at_k / labeled_precision_ceiling`，用于把“标签稀疏导致的天然低分”归一化。
- `hit_at_k`：每条 case 是否至少命中一个期望来源。
- `top1_accuracy`：第一条检索结果是否就是期望来源。
- `mrr`：第一个正确来源出现得越靠前越高。
- `ndcg_at_k`：考虑排序位置的检索质量。
- `route_accuracy`：Agent 是否选对 direct / project_qa / workflow / single_tool。
- `citation_coverage`：回答是否带引用。
- `field_coverage`：任务响应是否包含前端需要的结构化字段。
- `semantic_accuracy`：规则命中、issue family、expected value 等语义检查是否通过。
- `p50_ms / p95_ms`：接口耗时中位数和 95 分位。

当前基线结果：

- RAG cases：8
- `recall_at_k=0.9375`
- `precision_at_k=0.2500`
- `precision_at_retrieved=0.6250`
- `labeled_precision_ceiling=0.2812`
- `normalized_precision_at_k=0.9375`
- `hit_at_k=1.0000`
- `top1_accuracy=0.8750`
- `mrr=0.9375`
- `ndcg_at_k=0.9234`
- `route_accuracy=1.0000`
- `citation_coverage=1.0000`
- `no_result_ratio=0.0000`
- Task cases：12
- `success_rate=1.0000`
- `field_coverage=1.0000`
- `semantic_accuracy=1.0000`
- Hallucination Guard：15 cases，`grounding_accuracy=1.0000`，`unsupported_answer_rate=0.0000`
- Performance：35 requests，`p50_ms≈39`，`p95_ms≈108`

如何解读：

- `route_accuracy / field_coverage / semantic_accuracy` 已经适合项目质量展示，说明后端功能链路稳定。
- `precision_at_k=0.25` 不是单独的失败信号，因为当前多数 case 只标一个期望文件，`top_k=4` 时单标签 case 的精确率上限就是 0.25；应结合 `normalized_precision_at_k=0.9375`、`top1_accuracy=0.8750`、`mrr=0.9375` 一起看。
- `recall_at_k / hit_at_k / no_result_ratio` 已经恢复到稳定展示水平；后续如果继续优化，重点看没命中的那条 UE 知识样例、Top1 排序和更细的 domain 过滤。
- 离线 benchmark 的 `p95_ms` 已降到百毫秒内；live LLM benchmark 会受模型、代理和供应商延迟影响，不能和离线基线直接比较。

后续性能优化建议：

- 给 `LocalSearchService` 增加文件列表和文本内容缓存，避免每次请求重复遍历 `KB_SOURCE_PATHS`。
- benchmark 离线模式完全跳过 Qdrant 可用性探测，避免无向量库时的连接等待。
- 为 Project QA 的 lexical chunks 做进程内预热索引。
- 按任务类型裁剪不必要的 Debug View 深层字段，降低序列化成本。
- 对 Code Generate / Code Review 的知识参考检索做 domain 预过滤和 top-k 限制。

## 20. Tool Protocol v2 与 ActiveContext

后端现在把 Tool Registry 从“工具列表”升级为更接近 Agent 工具协议的 v2 结构。它不会改变 UE 前端现有 HTTP 调用方式，而是让后端更清楚地描述每个工具的用途、权限、上下文依赖和是否允许自由聊天自动调用。

查看入口：

```http
GET /api/v1/system/capabilities
```

关键字段：

- `capabilities.tool_registry.protocol_version = "tool_protocol_v2"`
- `capabilities.tool_registry.protocol.categories`：`context / sensing / retrieval / analysis / generation / write`
- `capabilities.tool_registry.protocol.transports`：`local_python / http / mcp_stdio / mcp_tcp / mcp_http`
- `capabilities.tool_registry.protocol.side_effect_levels`：`read_only / plan_only / confirmed_write / reversible_write / destructive_write`
- `capabilities.tool_registry.protocol.execution_policy`：自由聊天、草稿工具和确认写入工具的统一执行边界。
- `capabilities.tool_registry.tools[].category`：工具类别。
- `capabilities.tool_registry.tools[].transport`：当前工具执行通道。
- `capabilities.tool_registry.tools[].requires_confirmation`：是否必须用户确认。
- `capabilities.tool_registry.tools[].active_context_keys`：工具依赖哪些上下文。
- `capabilities.tool_registry.tools[].allowed_in_free_chat`：是否允许 Agent Chat 自动选择。
- `capabilities.tool_registry.tools[].enabled`：运行时配置后该工具是否启用。
- `capabilities.tool_registry.tools[].tier`：工具分层，当前支持 `core / extended / experimental`。
- `capabilities.tool_registry.tools[].config_source`：`builtin` 或 `tool_config_overlay`。
- `capabilities.tool_registry.tools[].config_warnings`：配置覆盖时被忽略的字段，例如危险权限降级字段。

### Tool Registry JSON Overlay

后端支持一个轻量工具配置覆盖层，用来借鉴 UMGMCP 的 `prompts.json` 控制平面。它不是新的插件系统，也不会改变工具真实能力边界，只允许覆盖低风险展示/选择字段。

默认读取路径：

```text
storage/tools_config.json
```

也可以用环境变量指定：

```env
TOOL_CONFIG_PATH=D:/path/to/tools_config.json
```

示例文件：

```text
config/tools_config.example.json
```

允许覆盖的字段：

- `enabled`
- `title`
- `description`
- `category`
- `trigger_keywords`
- `allowed_in_free_chat`
- `context_cost`
- `tier`

明确不允许覆盖的字段：

- `side_effect_level`
- `permission_gate`
- `requires_confirmation`
- `transport`
- `executor`
- `input_schema`
- `output_schema`
- `required_payload_fields`
- `optional_payload_fields`

原因很简单：JSON 配置可以让工具临时下线、调整描述或触发词，但不能把写操作伪装成只读工具，也不能绕过 Proposal 确认。

热重载接口：

```http
POST /api/v1/system/tool-registry/reload
```

返回中会包含：

- `tool_config_overlay.status`
- `tool_config_overlay.path`
- `tool_config_overlay.warnings`
- `capabilities.tools[]`

常见用法：

- 暂时关闭 `web_search_knowledge`，避免自由聊天误触发联网检索。
- 调整 `query_project_inventory` 的描述，让 Debug View 更容易看懂。
- 给某些工具标记 `tier=experimental`，前端 Debug View 可选展示。

当前执行策略：

- Agent Chat 只能自动调用 `read_only` 且 `allowed_in_free_chat=true` 的工具。
- `plan_only` 工具只生成草稿、建议、计划或 preview，不写入项目。
- `confirmed_write` 工具必须经过前端确认和后端安全校验。
- `reversible_write` / `destructive_write` 是未来扩展的危险等级标签，仍然必须经过前端确认和后端安全校验；当前不会让后端直接写 UE 项目。
- 显式功能面板仍优先使用固定 Skill 流程，避免 LLM 自由选错工具。

Debug View 新增：

- `debug_view.active_context`
- `debug_view.tool_registry_protocol`
- `debug_view.tool_execution_policy`
- `debug_view.tools[].category`
- `debug_view.tools[].transport`
- `debug_view.tools[].side_effect_level`
- `debug_view.tools[].approval_state`
- `debug_view.tools[].metadata.preflight`：如果工具走 `ToolContext executor`，这里会显示参数预检结果。

`ActiveContext` 用于解释本轮 Agent 到底看到了什么上下文：

- `project`：项目名、项目根目录、当前模块、UE 版本、插件版本。
- `asset`：选中资产、资产数量、资产类型过滤、inventory snapshot。
- `code`：当前文件、选中文件、最近打开文件、是否有 inline code。
- `log`：日志来源、日志文件路径、是否有日志文本。
- `kb`：知识库 domain hint、选中工具、是否需要 RAG。
- `mcp`：当前 MCP 状态。现阶段默认 `disabled`，因为 MCP 只作为后续可选工具层，不是 UE 前端与后端的主协议。

指标解释口径：

这个项目不是“把 LLM 聊天窗口塞进 UE 编辑器”，而是一个可观测的 Agent 后端。UE 插件负责采集编辑器上下文和展示结果，后端负责意图判断、上下文压缩、知识检索、工具调用、权限分级、LLM 综合和评估指标。LLM 自己可能知道 UE 通用知识，但它不知道当前项目资产、源码、日志、团队规则和用户本地私有知识库，所以知识库和工具调用提供的是可追溯、可更新、可验证的项目事实。

## 21. Code Generate 确认写入闭环

默认情况下，代码生成功能仍然只返回虚拟代码草稿，不会写入 UE 工程。只有请求明确开启写入提案，并且提供 `project_root` 时，后端才会生成 `write_code_files` proposal。

请求示例：

```json
{
  "task_type": "code_generate",
  "session": {
    "session_id": "demo-code-write",
    "messages": [
      {
        "role": "user",
        "content": "生成一个简单 UE Actor 并准备写入提案",
        "language": "auto"
      }
    ]
  },
  "context": {
    "project_name": "RushBa",
    "project_root": "F:/Epic Games/project/RushBa",
    "active_panel": "CodeGenerator",
    "current_module": "RushBa"
  },
  "payload": {
    "user_query": "生成一个简单 UE Actor 并准备写入提案",
    "requirement_description": "spawn helper actor",
    "target_type": "ue_cpp_class",
    "create_write_proposal": true
  },
  "ui_state": {
    "active_view": "user",
    "selected_panel": "CodeGenerator"
  }
}
```

也可以使用：

```json
{
  "write_mode": "proposal"
}
```

响应变化：

- `task.status = "waiting_confirmation"`：说明存在待确认写入提案。
- `action_proposals[].proposal_type = "write_code_files"`：代码写入提案。
- `action_proposals[].dry_run_preview.write_plan.status = "ready"`：写入计划已通过安全预校验。
- `data.write_policy.proposal_requested = true`
- `data.write_policy.proposal_status = "ready"`
- `data.write_plan.files[]`：每个待写文件的相对路径、目标路径、hash、字节数和状态。

确认写入：

```http
POST /api/v1/proposals/{proposal_id}/decision
```

```json
{
  "decision": "confirmed",
  "actor": "user",
  "comment": "确认写入这些生成代码文件"
}
```

拒绝写入：

```json
{
  "decision": "rejected",
  "actor": "user",
  "comment": "暂不写入"
}
```

安全边界：

- 必须提供 `project_root`。
- 只允许相对路径，禁止绝对路径和 `..`。
- 默认只允许写入 `Source/` 或 `Plugins/`。
- 默认只允许 `.h / .hpp / .hh / .inl / .c / .cc / .cpp / .cxx / .cs / .txt / .md`。
- 默认不覆盖已有文件；如果文件已存在，写入计划会被阻止。
- 确认后仍会二次校验路径；如果校验失败，不会写入任何文件。

确认成功后：

- `data.approval_result.execution_state = "files_written"`
- `data.code_write_result.written_to_disk = true`
- `data.code_write_result.written_files[]`：实际写入文件。
- `debug_view.side_effects[]`：记录 confirmed_write 副作用。
- 任务 artifacts 会新增 `code_write_report`。

如果写入被阻止：

- `data.approval_result.execution_state = "blocked"`
- `data.code_write_result.written_to_disk = false`
- `debug_view.side_effects[].blocked_files[]` 会说明原因。

这个能力仍然不是“LLM 自动改工程”。LLM 只生成草稿，后端只生成写入计划，真正写入必须由用户通过 Proposal 明确确认。

## 22. MCP Tool Adapter 可选工具层

后端现在有轻量 MCP Tool Adapter 骨架。它默认关闭，不影响 UE 前端通过 HTTP 调用后端，也不会自动启动任何外部 MCP server。

配置项：

```env
MCP_TOOL_ADAPTER_ENABLED=false
MCP_TRANSPORT=stdio
MCP_STDIO_COMMAND=
MCP_STDIO_ARGS=
MCP_TCP_HOST=127.0.0.1
MCP_TCP_PORT=8765
MCP_ALLOWED_TOOLS=
MCP_STDIO_TIMEOUT_MS=3000
MCP_TCP_TIMEOUT_MS=3000
```

设计边界：

- HTTP 仍然是 UE 前端和后端之间的主协议。
- MCP 只作为后端 Tool Registry 未来的一种可选 transport。
- 默认不启用，不依赖 UMG-MCP 或其他外部 MCP 项目。
- 即使启用，第一阶段也只允许只读验证工具。
- 写入类 MCP 工具未来也必须走 Proposal，不允许 LLM 直接执行。

查看状态：

```http
GET /api/v1/system/health
```

重点字段：

- `mcp_adapter.status`
- `mcp_adapter.enabled`
- `mcp_adapter.stdio.command`
- `startup_checks.checks[check_id="mcp_tool_adapter"]`

查看能力：

```http
GET /api/v1/system/capabilities
```

重点字段：

- `capabilities.mcp_adapter.mode = "optional_tool_transport"`
- `capabilities.mcp_adapter.frontend_protocol = "http"`
- `capabilities.mcp_adapter.tool_layer_only = true`
- `capabilities.mcp_adapter.safety_policy`

如果本机确实有一个 MCP stdio server，可以本地试配：

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_TRANSPORT=stdio
MCP_STDIO_COMMAND=uv
MCP_STDIO_ARGS=run,--directory,D:/Path/To/McpServer,Server.py
MCP_ALLOWED_TOOLS=get_target_umg_asset,get_widget_tree
```

如果要试配 UEAgentTool 内置 TCP 工具服务，则改用：

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_TRANSPORT=tcp
MCP_TCP_HOST=127.0.0.1
MCP_TCP_PORT=8765
MCP_ALLOWED_TOOLS=ue_agent_tools_list
```

当前阶段后端只做 readiness、allow-list 和 Debug/Health 契约，不把 MCP 工具自动注册进 Agent Chat，也不把 UMG-MCP 项目作为依赖提交。后续如果要接真实 MCP 工具，会从 `MCPToolAdapter` 继续扩展。

## 23. Eval Report API 评测结果读取

后端现在把本地评测产物也暴露成只读 API。它不会在线触发 benchmark，也不会调用 LLM，只读取 `storage/artifacts/evals/` 下已有的 `*.json` 和同名 `*.md` 报告，适合本地查看“RAG / 路由 / 任务结构 / 性能”如何被量化。

生成报告：

```powershell
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output storage\artifacts\evals\project-benchmark-latest.md
```

查看报告列表：

```http
GET /api/v1/knowledge-base/eval/reports
```

可选参数：

- `limit`：返回最近 N 份报告，默认 `20`，最大 `100`。

列表响应重点字段：

- `summary.evals_dir`：后端读取的本地 eval 目录。
- `summary.report_count`：当前目录下 JSON 报告数量。
- `items[].report_id`：报告文件名，用于详情接口。
- `items[].report_type`：`project_benchmark` / `rag_eval` / `task_eval` / `unknown`。
- `items[].summary`：压缩后的核心指标，例如 `hit_at_k`、`precision_at_k`、`task_summary.pass_rate`、`performance.p95_latency_ms` 等。
- `items[].markdown_path`：如果存在同名 Markdown 报告，会返回本地路径。

查看单份详情：

```http
GET /api/v1/knowledge-base/eval/reports/project-benchmark-latest.json
```

详情响应重点字段：

- `item`：与列表里的报告卡片一致。
- `report`：完整 JSON 报告内容。
- `markdown_preview`：同名 `.md` 文件前 8000 字符预览，便于 Debug View 或轻量页面直接展示。

安全边界：

- 只允许读取 `storage/artifacts/evals/` 下的 `.json` 文件。
- 不允许路径穿越，例如 `../secret.json` 会返回 404。
- API 只读，不删除、不写入、不重新运行评测。
- 这不是企业级评测平台，只是本地项目级的可复现量化展示入口。

## 24. UE Editor Operation Bridge / MCP-like 编辑器操作提案

后端现在提供第一版 `Editor Operation Bridge` 后端契约。它和 UMG-MCP 属于同一类设计思想：把 UE 编辑器能力抽象成工具，让 Agent 能规划编辑器操作。但本项目不直接依赖 UMG-MCP，也不让 LLM 直接操作编辑器。

核心原则：

- HTTP 仍然是 UE 插件和后端之间的主协议。
- MCP 是可选工具传输层；当前这版先用 HTTP proposal 契约表达 MCP-like 编辑器工具。
- 后端只生成 `EditorOperationProposal`。
- UE 插件必须让用户确认后才执行真实 Editor API。
- 执行结果必须回传后端，进入 proposal 的 `dry_run_preview.operation_result` 和 audit log。

当前编辑器操作已经按能力域分组：

- `asset`：资产重命名、批量重命名、移动资产、Static Mesh 白名单设置。
- `blueprint`：创建 Blueprint、添加变量/组件/Event Stub、模板化节点写入、显式 pin 连接、编译 Blueprint。
- `umg`：添加基础 Widget、设置 TextBlock 文本、CanvasPanelSlot 布局、Visibility。
- `level`：放置 Actor、设置 Actor Transform。
- `material`：设置 Material Instance scalar/vector/texture 参数。

查看能力：

```http
GET /api/v1/editor-operations/capabilities
```

能力响应适合前端和公开文档生成使用，重点字段：

- `summary.operation_count`：当前后端声明的编辑器操作数量。
- `summary.group_counts`：按 `asset / blueprint / umg / level / material` 分组统计。
- `summary.risk_flag_counts`：当前操作风险等级分布。
- `groups[]`：每个能力域的标题、说明和 operation 列表。
- `items[].group`：单个操作所属能力域。
- `items[].risk_flags`：风险等级，当前写操作仍需用户确认。
- `items[].result_contract_fields`：UE 插件执行后建议回传的结果字段。
- `read_only_items[]`：后端已可直接执行的只读检查操作，不创建 Proposal，不要求用户确认。
- `safety_policy.auto_execute_follow_ups=false`：后端不会自动执行 follow-up。
- `roadmap_items[]`：后续 P3/P4/P5 计划能力，只用于展示路线图，不会被当成可执行 proposal。
- `roadmap_items[].proposal_enabled=false`：明确表示当前后端不会创建这些计划项的写操作。

公开工具目录可以从同一个后端声明生成：

```powershell
.\.venv\Scripts\python.exe scripts\export_editor_operation_catalog.py --output docs\editor-operation-catalog.md
```

这样新增工具时，维护顺序是：更新后端 `OPERATION_SPECS` / result contract -> 运行导出脚本 -> 检查 `docs/editor-operation-catalog.md` -> 补测试和交接说明。

创建提案：

```http
POST /api/v1/editor-operations/proposals
```

重命名资产示例：

```json
{
  "operation_type": "rename_selected_asset",
  "payload": {
    "asset_path": "/Game/Maps/NewMap",
    "new_name": "L_TestCombatArena"
  },
  "reason": "资产命名仍是默认名，建议改成语义化地图名。"
}
```

Static Mesh 设置示例：

```json
{
  "operation_type": "apply_static_mesh_basic_settings",
  "payload": {
    "asset_path": "/Game/Props/SM_Crate",
    "settings": {
      "nanite_enabled": true,
      "collision_complexity": "simple_and_complex",
      "lod_group": "SmallProp",
      "generate_lightmap_uv": true,
      "lightmap_resolution": 64
    }
  }
}
```

Blueprint 创建示例：

```json
{
  "operation_type": "create_blueprint_asset",
  "payload": {
    "parent_class": "/Script/Engine.Character",
    "target_folder": "/Game/Blueprints",
    "asset_name": "BP_PlayerCharacter"
  }
}
```

确认或拒绝：

```http
POST /api/v1/editor-operations/proposals/{proposal_id}/confirm
POST /api/v1/editor-operations/proposals/{proposal_id}/reject
```

UE 插件执行后回传：

```http
POST /api/v1/editor-operations/results
```

```json
{
  "proposal_id": "proposal_xxx",
  "operation_type": "rename_selected_asset",
  "execution_state": "completed",
  "success": true,
  "executed_by": "ue_plugin",
  "transaction_id": "ue_transaction_id_or_empty",
  "undo_hint": "可使用编辑器 Undo 或手动改回原名。",
  "result": {
    "final_asset_path": "/Game/Maps/L_TestCombatArena",
    "dirty": true
  },
  "errors": []
}
```

安全边界：

- 未确认的 proposal 不能回传成功执行结果，后端会返回 `proposal_must_be_confirmed_before_execution_result`。
- `apply_static_mesh_basic_settings` 只允许 `nanite_enabled / collision_complexity / lod_group / generate_lightmap_uv / lightmap_resolution`。
- `create_blueprint_asset` 的目标目录必须在 `/Game` 下。
- 后端不自动保存 UE 资产包，不直接调用 UE Editor API。
- 后续“自动写蓝图图表”也应归入同一类 Editor Tool Bridge，但必须先做节点预览、白名单和用户确认。

当前已接入的自动提案入口：

- `Assets Inspect`：当只检查一个资产且后端产生合法重命名建议时，会自动附带 `proposal_type=editor_operation`、`operation_type=rename_selected_asset`。
- `Agent Chat / Project QA`：当用户明确提出创建蓝图、重命名选中资产、或修改 Static Mesh 基础设置时，后端会生成 `editor_operation` proposal，而不是直接执行。
- 直接调试接口仍可使用 `POST /api/v1/editor-operations/proposals` 手动创建提案。

执行结果回传后的读取位置：

- `GET /api/v1/editor-operations/proposals/{proposal_id}`：查看 proposal 的 `dry_run_preview.operation_result`。
- `GET /api/v1/tasks/{task_id}`：如果 proposal 来源于某个任务，结果会同步进入 `data.editor_operation_results[]`。
- `debug_view.side_effects[].operation_result`：用于 Debug View 展示执行状态、transaction、dirty package、错误原因等。

推荐 UE 插件回传的 `result` 字段：

- 通用：`asset_path`、`object_path`、`package_name`、`dirty`、`dirty_packages`。
- 重命名资产：`final_asset_path`、`old_asset_path`、`redirector_hint`。
- Static Mesh 设置：`applied_fields`、`failed_fields`、`field_results`。
- Blueprint 创建：`asset_path`、`parent_class`、`opened_editor=false`。

## 25. Active Context / Project Inventory v2

本轮后端把 Project Inventory 从“资产/代码清单”深化为 Agent 可使用的项目上下文底座。UE 前端仍然通过：

```http
POST /api/v1/project-inventory/snapshot
```

提交快照。后端现在会尽量保留并归一化这些字段：

- 资产基础：`asset_path`、`asset_name`、`asset_type`、`package_path`、`dependencies`、`referencers`。
- Static Mesh：`settings.nanite_enabled`、`lod_count`、`collision_complexity`、`lightmap_resolution`。
- Blueprint：`blueprint.parent_class`、`components`、`variables`、`functions`、`graphs`、`interfaces`、`editor_flags`。
- 代码文件：`file_path`、`module_name`、`file_type`、`classes`、`symbols`、`modified_at`。
- 关卡 Actor：`level_actors[].actor_label`、`actor_class`、`level_name`、`blueprint_path`、`transform`、`components`。
- 材质实例：`material_instances[].material_instance_path`、`parent_material`、`scalar_parameters`、`vector_parameters`、`texture_parameters`、`static_switch_parameters`。

提交后，`GET /api/v1/project-inventory/summary` 会额外返回：

- `blueprint_count`
- `static_mesh_count`
- `map_count`
- `blueprint_parent_class_counts`
- `level_actor_count`
- `level_actor_class_counts`
- `level_actor_level_counts`
- `material_instance_count`
- `material_instance_parent_counts`
- `material_parameter_count`
- `freshness`：当前快照是否 `fresh/stale/missing/unknown`，以及 `should_refresh`、`age_seconds`、`stale_after_seconds`

Agent Chat / Project QA 会把最近项目快照注入：

- `debug_view.context_bundle.project_inventory_context`
- `debug_view.active_context.inventory`
- `debug_view.active_context.asset.selected_asset_details`
- `debug_view.active_context.level_actor.current_actor_inventory`
- `debug_view.active_context.material.current_material_instance_inventory`
- `debug_view.active_context.code.current_file_inventory`
- `debug_view.active_context.blueprint`
- `debug_view.active_context.editor_focus`
- `debug_view.context_bundle.project_inventory_context.top_level_actors`
- `debug_view.context_bundle.project_inventory_context.top_material_instances`

`freshness` 同时会进入：

- `data.inventory.summary.freshness`
- `debug_view.context_bundle.project_inventory_context.freshness`
- `debug_view.context_pack.project_layer.inventory.freshness`
- `debug_view.active_context.inventory.freshness`

当 `freshness.status=stale` 时，Agent Chat 的 Inventory fallback 回答会在正文开头提示该结果来自最近一次同步快照，并建议用户点击 `Sync Inventory Now` 后再做最终判断。UEAgentTool 如果要做用户体验增强，只需要在普通用户视图里显示一个轻量提示，不需要增加 Debug 面板。

因此用户问“当前项目有哪些蓝图资产”“这个蓝图有哪些组件/变量”“当前文件属于哪个模块”“当前关卡有哪些 Actor”“某个材质实例有哪些参数”时，后端可以优先用项目快照回答；如果问题包含“为什么、怎么做、建议、风险”，再组合知识库和 LLM 综合。

2026-06-02 update: Active Context now includes a lightweight Blueprint focus
projection. The backend can infer `current_blueprint_path` from
`payload.blueprint_path`, `payload.current_blueprint_path`,
`payload.widget_blueprint_path`, `context.editor_state.current_blueprint_path`,
or selected assets whose names look like `BP_`, `WBP_`, or `ABP_`. If the UE
frontend provides `context.editor_state.current_graph_name`,
`context.editor_state.selected_node_id`, or the equivalent payload fields, the
backend exposes them in `debug_view.active_context.blueprint` and
`debug_view.context_bundle.context_pack.active_layer.blueprint`.

This is optional and backward-compatible. Existing UEAgentTool builds can keep
sending only `selected_assets`; newer builds may send graph/node focus when the
user is actively editing a Blueprint graph.

2026-06-02 update: Context Pack prompt excerpts now surface
`active_layer.blueprint` and `active_layer.editor_focus` explicitly. This helps
Agent Chat and workflow handlers reason about the current Blueprint focus
without requiring a new frontend contract. When a plan-only Blueprint workflow
does not receive an explicit `blueprint_path` or `graph_name`, the workflow
planner can use this Active Context focus as the default target. If the user
explicitly says `EventGraph` or `ConstructionScript`, the user request still
wins over the inferred focus.

The same focus rule also applies to single-step Agent Chat editor-operation
routing for `add_blueprint_node_template`: when the user asks to add a
Blueprint Print String node but omits the graph name, the backend can use
`context.editor_state.current_graph_name`. If that graph is `ConstructionScript`,
the Proposal leaves `entry_event` empty so UEAgentTool can create an unlinked
Construction Script node instead of trying to connect from `BeginPlay`.

如果 UI 或调试脚本需要直接展示蓝图结构列表，可以使用：

```http
GET /api/v1/project-inventory/blueprints
GET /api/v1/project-inventory/blueprints?query=Player
GET /api/v1/project-inventory/blueprints?parent_class=ACharacter
GET /api/v1/project-inventory/blueprint-graphs?blueprint_query=Player&graph_name=EventGraph
```

返回项会把 UEAgentTool 快照中的 `blueprint.parent_class`、`components`、`variables`、`functions`、`graphs`、`graph_summaries`、`interfaces`、`editor_flags` 投影为轻量列表，并附带依赖/引用数量预览。`graph_summaries[]` 由 UE 插件自动采集，包含 graph 名称、类型、节点数、pin 数、link 数，以及少量节点/pin 摘要，用于回答“这个蓝图图表里有哪些节点”这类只读项目事实问题。它是只读查询，不经过 Proposal，也不会修改 UE 工程。

如果 UI 或调试脚本只关心图表节点，可以直接使用 `/project-inventory/blueprint-graphs`。它会返回 `kind=blueprint_graph`、`asset_name`、`asset_path`、`graph_name`、`graph_type`、`node_count`、`pin_count`、`link_count` 和可选 `nodes[]`。设置 `include_nodes=false` 可以只拿 graph 级摘要，减少 Debug View 噪声。

UEAgentTool 的 Agent Chat / Project QA 工作区已经提供九个只读辅助按钮：`Sync Inventory Now` 会重新提交 Project Inventory，`Show Assets` 会调用 `/api/v1/editor-operations/inspect/assets?limit=30` 并在聊天区列出最近快照中的项目资产，`Show Selected Asset` 会读取内容浏览器当前选中资产并调用 `/api/v1/editor-operations/inspect/asset-detail` 显示类型、路径、依赖、引用、常用设置和属性摘要，`Show Blueprint Graphs` 会优先按内容浏览器当前选中的 Blueprint 查询；如果没有选中 Blueprint，则调用 `/api/v1/project-inventory/blueprint-graphs?include_nodes=true&limit=20` 并在聊天区显示全项目图表摘要，`Show Level Actors` 会调用 `/api/v1/editor-operations/inspect/level-actors?limit=40` 并显示当前快照里的关卡 Actor、Class、Level、位置、Folder、Tags 和组件摘要，`Show Materials` 会调用 `/api/v1/editor-operations/inspect/material-instance-parameters?limit=40` 并显示材质实例、父材质和参数预览，`Show Tools` 会读取 `/api/v1/editor-operations/capabilities` 并显示支持的 confirmed-write 工具、read-only inspection、分组、风险/状态计数和确认策略，`Show Activity` 会读取 `/api/v1/editor-operations/diagnostics` 与 `/api/v1/editor-operations/history` 并显示最近 Proposal、执行状态和诊断计数，`Show Inventory Summary` 会调用 `/api/v1/project-inventory/summary` 并在聊天区显示当前快照的资产、Blueprint、代码文件、关卡 Actor、材质实例和常见类型计数。它们只读取/提交快照，不创建 Proposal，也不会修改蓝图、关卡、材质或资产。

Agent Chat 路由也会把英文图表节点问题识别为 Project Inventory 查询，例如 `In the current project, what nodes are in BP_PlayerCharacter EventGraph?`。这类问题会优先使用 `graph_summaries` 中的节点标题、节点数、pin 数和连线数，而不是让 LLM 根据通用 UE 知识猜测当前工程内容。

自然语言问法现在会尽量兼容更口语的项目事实查询，例如：

- `当前关卡摆了哪些物体？`
- `当前场景里有什么对象？`
- `当前项目 MI_Rock 的 Roughness 是多少？`
- `这个材质实例有哪些贴图参数？`

这些问题会进入 `query_project_inventory`，而不是普通知识库检索。LLM 未配置或调用失败时，后端也会用 Inventory 兜底生成摘要，Actor 会包含 class、level、location、blueprint、components；Material Instance 会包含 parent material 和参数名/参数值预览。

`POST /api/v1/project-inventory/query` 也支持可选 `selected_assets`：

```json
{
  "project_id": "RushBa",
  "query": "What components does this asset have?",
  "selected_assets": ["/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter"]
}
```

也可以请求更聚焦的字段视图：

```json
{
  "project_id": "RushBa",
  "query": "Show material instance parameters",
  "fields": ["parent_material", "parameters"]
}
```

当问题包含 `this asset / selected asset / components / variables / functions / graphs` 这类上下文词时，后端会优先返回选中资产，而不是列出全项目资产。关卡 Actor 和材质实例字段来自 UEAgentTool 的 Inventory 采集；旧前端不提交时，summary 会显示数量为 0，问答不会编造缺失信息。

2026-06-04 update: Active Context v3 can also project selected Level Actor and
Material Instance focus from existing request fields:

- `context.editor_state.selected_actors`
- `payload.selected_actors`
- `payload.selected_actor_references`
- `payload.actor_reference`
- `payload.selected_material_instances`
- `payload.material_instance_path`
- `context.selected_assets` entries that look like `MI_...`

When the latest Project Inventory snapshot contains matching
`level_actors[]` or `material_instances[]`, the backend injects compact details
into `debug_view.active_context.level_actor.current_actor_inventory` and
`debug_view.active_context.material.current_material_instance_inventory`. This is
read-only grounding for Agent Chat and tool planning; it does not create
Proposals or execute editor writes.

The same focus is also projected into
`debug_view.context_bundle.context_pack.active_layer.level_actor` and
`debug_view.context_bundle.context_pack.active_layer.material`. This keeps the
Agent prompt compact: the active layer carries the focused actor/material path,
label, class, parent material, and parameter/component counts, while detailed
parameter values should still be answered through Project Inventory query
results.

`POST /api/v1/project-inventory/query` also accepts the same read-only focus
hints:

- `selected_actor_references`
- `current_actor_reference`
- `selected_material_instance_paths`
- `current_material_instance_path`

Agent Chat fills these from Active Context automatically. Questions such as
`当前选中的 Actor 和材质是什么？`, `这个对象有哪些组件？`, or
`这个材质的 Roughness 是多少？` can therefore use Project Inventory grounding
instead of falling back to generic knowledge-base retrieval.

Editor Operation Bridge 也提供了两个只读检查入口，方便前端或调试脚本按“编辑器操作能力”的命名方式读取同一份 Inventory：

```http
GET /api/v1/editor-operations/inspect/level-actors
GET /api/v1/editor-operations/inspect/level-actor-detail
GET /api/v1/editor-operations/inspect/material-instance-parameters
GET /api/v1/editor-operations/inspect/material-instance-detail
```

它们返回 `inspection.side_effect_level=read_only`，不会创建 Proposal，也不会要求 UE 前端执行 Editor API。数据来源仍是最近一次 Project Inventory 快照。

边界：

- 后端不解析 `.uasset`，只消费 UE 前端提交的结构化摘要。
- 快照是本地 JSON 存储，不做企业级索引服务。
- Active Context 只保留摘要，不把大段源码或完整资产元数据塞进 prompt。

### 25.6 MCP / SSE 稳定版边界

当前稳定版的编辑器集成主链路仍然是 HTTP Proposal Bridge：

```text
Agent Chat -> Tool/Operation routing -> pending Proposal -> 用户确认 -> UEAgentTool 执行 -> 回传结果
```

MCP 在本项目中当前定位为 Tool Registry 兼容层和未来 transport 预留：

- `GET /api/v1/mcp/tool-registry/manifest` 可以导出 MCP-compatible ToolSpec 元数据。
- confirmed-write 工具不会被 MCP 直接执行，必须转换为 Proposal。
- UEAgentTool 目前不需要作为 MCP client/server 才能使用核心功能。
- 如果未来工具数量大幅增加，才考虑把 read-only 工具开放为直接 MCP call，把写工具继续映射到 Proposal。

SSE / streaming 当前也是可选增强：

- 非流式 HTTP 仍是默认路径，UE 插件可以保持现有请求方式。
- SSE 适合长 LLM 回复或长 workflow 进度提示，不改变 Proposal 的安全语义。
- 即使启用流式输出，写入类操作仍然必须等待用户确认，不能在流中自动执行。

## 26. Blueprint Graph Automation v1 Proposal 契约

后端已经把蓝图图表自动化纳入 `Editor Operation Bridge`。写操作仍然只生成 proposal，不直接绕过 UE 前端执行 Editor API。UE 前端回传确认：以下 operation 已在 UE 侧接入真实执行路径，`GET /api/v1/editor-operations/capabilities` 中的 `frontend_status` 已标记为 `implemented_v1`。另外，默认关闭的 TCP 工具层提供 `get_blueprint_graph` 只读图谱摘要，供未来 Agent 感知蓝图结构。

新增 operation：

```text
add_blueprint_variable
add_blueprint_component
create_blueprint_event_stub
add_blueprint_node_template
connect_blueprint_nodes
compile_blueprint
```

添加变量示例：

```json
{
  "operation_type": "add_blueprint_variable",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "variable_name": "Health",
    "variable_type": "float",
    "category": "Combat",
    "default_value": "100.0"
  }
}
```

`variable_type` 支持 UE 前端常用短别名和后端规范名：`bool`、`byte`、`int`/`int32`、`int64`、`float`、`double`、`name`/`FName`、`string`/`FString`、`text`/`FText`、`vector`/`FVector`、`rotator`/`FRotator`、`transform`/`FTransform`、`object`/`UObject`、`actor`/`AActor`。自定义类型可传 `/Script/` 或 `/Game/` 开头的路径；后端不强制为 `/Game/` Blueprint 变量生成 `_C`，由 UE 前端按 Blueprint asset path 或 generated class path 自行解析。

添加组件示例：

```json
{
  "operation_type": "add_blueprint_component",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "component_name": "SpringArm",
    "component_class": "/Script/Engine.SpringArmComponent",
    "attach_to": "RootComponent"
  }
}
```

创建基础事件 stub 示例：

```json
{
  "operation_type": "create_blueprint_event_stub",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "event_name": "BeginPlay",
    "graph_name": "EventGraph",
    "node_comment": "Created by UE Agent proposal."
  }
}
```

添加模板化节点示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "print_string",
    "graph_name": "EventGraph",
    "message": "Hello from UEAgent",
    "duration": 2.0,
    "print_to_screen": true,
    "print_to_log": true,
    "entry_event": "BeginPlay",
    "node_position": {"x": 320, "y": 160},
    "compile_after_edit": true
  }
}
```

Blueprint Graph policy v1:

- Backend now adds `dry_run_preview.blueprint_graph_policy` for
  `add_blueprint_node_template` proposals.
- This block is diagnostic-only and does not change the UEAgentTool execution
  payload. Existing Proposal cards can ignore it.
- It records selected `graph_name`, selected `entry_event`, whether the user
  asked for an unconnected node, selection reasons, template capability, and
  expected connection behavior.
- `EventGraph` templates may default to `BeginPlay` when a connected exec chain
  is expected. `ConstructionScript` and other non-event graphs do not get a
  forced `BeginPlay`; if no entry event exists, the preview marks
  `expected_behavior.connects_exec_pins=false`.
- If the user asks for `unconnected`, `standalone`, `no connection`, or their
  Chinese equivalents for "do not connect" / "create only", the backend clears
  the default entry event and the proposal is expected to create an isolated
  node/template.
- This policy layer is the backend-side bridge between natural-language
  requests and future HTTP/MCP graph tools. It keeps graph selection
  explainable without letting the LLM directly edit arbitrary Blueprint graphs.
- 2026-06-03 update: Blueprint graph detector rules are now exposed through
  `app/services/editor_operations/blueprint_detectors.py`. `EditorOperationService`
  keeps backward-compatible wrapper methods, while graph-name, active-graph,
  entry-event, and unconnected-node intent rules live in the smaller detector
  module. This is the first backend detector-split slice for Improv5 and does
  not change public API payloads.
- 2026-06-03 update: shared editor-operation path/name normalizers are now
  exposed through `app/services/editor_operations/normalizers.py`. The service
  keeps its existing wrapper methods, while common `/Game` path, folder,
  redirector-folder, asset-name, class-path, and optional-string validation live
  in the smaller module. This does not change Proposal payloads or frontend
  behavior.
- 2026-06-03 update: editor-operation result summary normalization now lives in
  `app/services/editor_operations/results.py`. The service still owns Blueprint
  graph diagnostics for now, but common result summary fields such as dirty
  packages, applied/failed field counts, error codes, repair advice, and
  `needs_user_attention` are covered by the smaller result module. Public result
  payloads stay unchanged.
- 2026-06-03 update: small follow-up helpers now live in
  `app/services/editor_operations/followups.py`. Redirector follow-up folder
  extraction, safe quick-action projection, and follow-up folder slugs are
  isolated while the service keeps the existing follow-up endpoints and
  Proposal materialization behavior.
- 2026-06-03 update: Blueprint graph result diagnostics and repair-advice rules
  now live in `app/services/editor_operations/blueprint_result_diagnostics.py`.
  The service keeps compatibility wrappers, while diagnostic flags such as
  `expected_linked_pins_missing`, `compile_failed`, and
  `dirty_packages_missing` are covered by direct unit tests.

`add_blueprint_node_template` 当前开放十个白名单模板：

- `template_id=print_string`：UE 插件会在指定 graph 中创建 `UKismetSystemLibrary::PrintString` CallFunction 节点。若传入 `entry_event=BeginPlay / ActorBeginOverlap / ActorEndOverlap`，插件会创建或复用对应事件节点，并尝试连接 `Event.Then -> PrintString.Execute`。
- `template_id=branch_print_string`：UE 插件会创建或复用 `Event BeginPlay`，创建 `Branch` 节点和 `PrintString` 节点，并连接 `BeginPlay -> Branch -> PrintString`。可传 `condition_default=true/false` 设置 Branch 条件默认值，可传 `branch_path=true/false` 指定把 PrintString 接到 True 分支还是 False 分支。
- `template_id=sequence_print_strings`：UE 插件会创建或复用 `Event BeginPlay`，创建 `Sequence` 节点和两个 `PrintString` 节点，并连接 `BeginPlay -> Sequence -> PrintString(1/2)`。可传 `messages` 字符串数组，当前固定两条输出，避免开放任意数量节点。
- `template_id=delay_print_string`：UE 插件会创建或复用 `Event BeginPlay`，创建 `Delay` 节点和一个 `PrintString` 节点，并连接 `BeginPlay -> Delay -> PrintString`。可传 `delay_seconds`，范围 `0-60` 秒。
- `template_id=get_variable`：UE 插件会为已有 Blueprint member variable 创建一个 `Variable Get` 节点。当前只支持 `variable_scope=self`，不会自动连线。
- `template_id=set_variable`：UE 插件会为已有 Blueprint member variable 创建一个 `Variable Set` 节点，默认创建或复用 `Event BeginPlay` 并连接 `BeginPlay -> SetVariable`。可传 `variable_value` 写入 Set 节点值 Pin 的默认值。
- `template_id=call_function`：UE 插件会调用当前 Blueprint / 父类上已存在的无输入参数、非 Pure 函数，创建 `CallFunction` 节点；默认创建或复用 `Event BeginPlay` 并连接 `BeginPlay -> CallFunction`。当前只支持 `function_target=self`。
- `template_id=custom_event_print_string`：UE 插件会创建一个无参数 `Custom Event` 节点和一个 `PrintString` 节点，并连接 `CustomEvent.Then -> PrintString.Execute`。事件名来自 `custom_event_name`，若同名事件已存在，UE 会使用唯一化后的 Kismet 名称返回到结果里。
- `template_id=enhanced_input_action_event`：UE 插件会根据已有 `UInputAction` 资产创建 `Enhanced Input Action` 事件节点。该模板只创建事件源节点，不自动连线；后续可通过 `get_blueprint_graph` 读取 `Triggered / Started / Completed` 等 pin，再用 `connect_blueprint_nodes` 显式连接。
- `template_id=enhanced_input_print_string`：UE 插件会根据已有 `UInputAction` 资产创建 `Enhanced Input Action` 事件节点和一个 `PrintString` 节点，并尝试连接 `EnhancedInput.Triggered -> PrintString.Execute`。如果 `Triggered` pin 不存在，会回退到第一个可用 exec output；如果任一 pin 已被占用，则本次执行会失败并回传诊断，不会断开已有连线。

执行后可选编译一次 Blueprint，并把 `created_nodes`、`linked_nodes`、`linked_pins`、`branch_path`、`condition_default`、`sequence_output_count`、`messages`、`delay_seconds`、`variable_name`、`variable_scope`、`variable_value`、`function_name`、`function_target`、`custom_event_name`、`input_action_path`、`input_action_name`、`compile_status`、`dirty_packages`、`applied_fields` 回传后端。后续模板会继续按白名单扩展，不开放任意节点类名。

后端契约 smoke：

```powershell
.\.venv\Scripts\python.exe scripts\run_blueprint_graph_operation_smoke.py
```

这个命令不启动 UE，不执行编辑器写入，也不调用 LLM；它用于检查后端 Proposal 契约、白名单模板、显式 Pin 连接和拒绝用例是否仍然稳定。真正的节点生成、连线、编译和 Undo 行为仍需要在 UEAgentTool 侧实机验证。

UE 插件回传 Blueprint Graph 执行结果后，后端会在 `result_summary.operation_diagnostics` 中补充诊断摘要：

- `created_node_count`：本次创建的节点数量。
- `linked_pin_count`：本次真实连接的 pin 数量。
- `compile_requested / compile_status`：是否请求编译以及 UE 插件回传的编译状态。
- `execution_error_codes`：UEAgentTool 回传的错误码摘要，例如 `graph_not_found`、`entry_event_not_found`、`pin_resolution_failed`。
- `diagnostic_flags`：例如 `expected_linked_pins_missing`、`compile_status_missing`、`compile_failed`、`created_nodes_missing`、`blueprint_graph_unresolved`、`entry_event_unresolved`、`pin_resolution_failed`。
- `failed_fields[] / errors[]`：UEAgentTool 会尽量把缺少 node/pin、pin 已占用、graph/schema 不可用、Blueprint 编译失败等原因整理成可读文本，后端会把这些信息同步到 User View 的 `Blueprint Graph Details` block 中。

这些字段主要给 Debug View、操作历史和排查使用，不要求前端立刻新增 UI；旧版 Proposal 卡片可以继续只显示原有结果。

操作历史可以按诊断状态筛选：

```http
GET /api/v1/editor-operations/history?needs_user_attention=true
GET /api/v1/editor-operations/history?operation_type=add_blueprint_node_template&diagnostic_flag=expected_linked_pins_missing
```

如果你想在一次实机测试后快速看整体健康度，可以直接请求汇总接口：

```http
GET /api/v1/editor-operations/diagnostics
GET /api/v1/editor-operations/diagnostics?operation_type=add_blueprint_node_template
```

返回的 `summary` 会包含：
- `executed_count` / `pending_count`：最近 proposal 里已经回传执行结果和仍未回传的数量。
- `success_count` / `failed_count`：UE 侧执行成功与失败数量。
- `needs_user_attention_count` / `attention_rate`：需要人工关注的比例。
- `diagnostic_flag_counts`：例如 `expected_linked_pins_missing`、`compile_failed`、`dirty_packages_missing`、`blueprint_graph_unresolved`、`entry_event_unresolved` 的分布。
- `repair_status_counts` / `repair_action_counts`：后端基于诊断 flag 生成的固定修复建议分布。
- `recent_attention_items`：最近最多 10 条需要关注的 proposal，便于直接跳回 history 或 Debug View 排查。

这个接口不改变旧版 history 行为，也不要求 UE 前端立刻修改；它主要服务后端调试、实机 smoke 后巡检，以及未来前端想做“最近编辑器操作健康概览”时接入。

每条 Blueprint Graph 执行结果的 `result_summary.operation_diagnostics.repair_advice` 也会给出轻量建议：

```json
{
  "schema_version": "blueprint_graph_repair_advice_v1",
  "status": "suggested",
  "severity": "warning",
  "can_auto_retry": false,
  "safe_next_step": "manual_review",
  "actions": [
    {
      "action_id": "connect_expected_exec_pins",
      "title": "Connect expected execution pins"
    }
  ]
}
```

当前建议仍然是“诊断辅助”，不是自动修复系统。`can_auto_retry=false` 表示后端不会擅自重试写操作；用户仍需在 UE 前端确认新的 proposal，或在编辑器里手动检查图表、编译结果、dirty package。

如果需要把诊断建议转换成下一步候选，可以查看：

```http
GET /api/v1/editor-operations/proposals/{proposal_id}/follow-ups
```

返回的 `follow_up.candidates[]` 只包含“候选 proposal 请求体”，例如：

- `connect_expected_exec_pins`：为上一次未连线的 Blueprint 节点生成 `connect_blueprint_nodes` 候选。
- `retry_compile_blueprint`：为上一次编译失败或缺少编译状态的 Blueprint 生成 `compile_blueprint` 候选。

重要边界：

- 后端不会自动执行 follow-up。
- 后端也不会自动创建新的 proposal；接口只返回 `create_request_hint`，调用方仍需显式 `POST /api/v1/editor-operations/proposals`。
- 所有 follow-up 写操作仍然必须走用户确认和 UEAgentTool 执行。
- 如果缺少 node id / Blueprint path 等必要信息，`proposal_ready=false` 且 `missing_inputs` 会说明还需要什么。

这两个查询参数都是可选的；旧版 `GET /api/v1/editor-operations/history` 行为不变。

Branch + PrintString 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "branch_print_string",
    "graph_name": "EventGraph",
    "message": "Branch reached",
    "entry_event": "BeginPlay",
    "condition_default": true,
    "branch_path": "true",
    "compile_after_edit": true
  }
}
```

Sequence + PrintString 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "sequence_print_strings",
    "graph_name": "EventGraph",
    "messages": ["Sequence step A", "Sequence step B"],
    "entry_event": "BeginPlay",
    "compile_after_edit": true
  }
}
```

Set Variable 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "set_variable",
    "graph_name": "EventGraph",
    "variable_name": "Health",
    "variable_value": "100.0",
    "entry_event": "BeginPlay",
    "compile_after_edit": true
  }
}
```

Get Variable 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "get_variable",
    "graph_name": "EventGraph",
    "variable_name": "Health",
    "compile_after_edit": true
  }
}
```

Call Function 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "call_function",
    "graph_name": "EventGraph",
    "function_name": "RefreshHud",
    "entry_event": "BeginPlay",
    "compile_after_edit": true
  }
}
```

Enhanced Input Action Event 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "enhanced_input_action_event",
    "graph_name": "EventGraph",
    "input_action_path": "/Game/Input/IA_Jump",
    "compile_after_edit": true
  }
}
```

Enhanced Input Triggered -> PrintString 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "enhanced_input_print_string",
    "graph_name": "EventGraph",
    "input_action_path": "/Game/Input/IA_Jump",
    "message": "IA_Jump triggered",
    "compile_after_edit": true
  }
}
```

Custom Event -> PrintString 示例：

```json
{
  "operation_type": "add_blueprint_node_template",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "template_id": "custom_event_print_string",
    "graph_name": "EventGraph",
    "custom_event_name": "OnAgentTriggered",
    "message": "OnAgentTriggered from UEAgent",
    "compile_after_edit": true
  }
}
```

显式连接 Blueprint Pin 示例：

```json
{
  "operation_type": "connect_blueprint_nodes",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "graph_name": "EventGraph",
    "source_node_id": "6C7D8E9F-0000-1111-2222-333344445555",
    "source_pin_name": "then",
    "target_node_id": "8E9F0001-2222-3333-4444-555566667777",
    "target_pin_name": "execute",
    "compile_after_edit": true
  }
}
```

`connect_blueprint_nodes` 必须使用 `get_blueprint_graph` 返回的 `node_id` 或 UE 生成的 `node_name`，并使用节点上的准确 `pin_name`。UE 插件只允许同一 Blueprint graph 内的 `Output -> Input` 连接；如果任一 pin 已经连接到其他 pin，v1 会直接 blocked，不会自动断开或重写已有蓝图逻辑。

Agent Chat 自然语言桥接会做一层轻量图谱语义识别：

- 文本包含 `EventBeginPlay`、`BeginPlay`、`开始播放` 时，会把 `entry_event` 规范化为 `BeginPlay`，而不是把它误当成 graph 名。
- 文本包含 `ConstructionScript`、`construction script`、`构造脚本` 时，会把 `graph_name` 设为 `ConstructionScript`。
- 文本包含 `EventGraph`、`event graph`、`事件图表` 时，会把 `graph_name` 设为 `EventGraph`。
- Agent Chat 中普通 `Print String` 请求如果明确目标是 `EventGraph`，后端会默认补 `entry_event=BeginPlay`，让 UEAgentTool 创建或复用 `Event BeginPlay` 并尝试连接执行线；如果用户明确说 `unconnected / no connection / 只创建 / 不连接`，则保持 `entry_event=""`，只创建节点不连线。
- 文本同时包含 `Enhanced Input / Input Action / IA_*` 和 `Print String`，且能从 payload、选中资产、Project Inventory 或文本中的 `IA_*` 名称解析到 Input Action 时，会生成 `enhanced_input_print_string` Proposal。
- 文本同时包含 `Overlap / ActorBeginOverlap / ActorEndOverlap / 重叠 / 碰撞` 和 `Print String`，会生成 `print_string` Proposal，并把 `entry_event` 设置为 `ActorBeginOverlap` 或 `ActorEndOverlap`；没有明确结束重叠时默认使用 `ActorBeginOverlap`。
- 文本同时包含 `Custom Event / 自定义事件` 和 `Print String`，会生成 `custom_event_print_string` Proposal；如果没有解析到事件名，则使用 `UEAgentCustomEvent` 作为安全默认名。
- 文本包含 `compile / recompile / 编译 / 重新编译` 且能从 payload、Project Inventory、选中资产或最近操作中解析到 Blueprint 时，会生成 `compile_blueprint` Proposal。
- 文本包含 `BeginPlay / Tick / ActorBeginOverlap / ActorEndOverlap` 这类白名单事件，且是“添加事件节点”语义时，会生成 `create_blueprint_event_stub` Proposal。

这仍然不是“自动猜整张蓝图怎么连”的能力；它只是把常见口语表达转成更稳定的 Proposal payload。Graph 是否真实存在、Pin 是否可连接，仍由 UEAgentTool 执行时验证并回传结果。

编译 Blueprint 示例：

```json
{
  "operation_type": "compile_blueprint",
  "payload": {
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "compile_mode": "default"
  }
}
```

可选 TCP 只读图谱工具：

```text
tool_id: mcp_get_blueprint_graph
mcp_tool_name: get_blueprint_graph
transport: mcp_tcp
required_payload_fields: blueprint_path
```

开启 UE 插件 TCP 服务并在后端设置 `MCP_TOOL_ADAPTER_ENABLED=true`、`MCP_TRANSPORT=tcp` 后，可以通过 `/api/v1/mcp/tools/get_blueprint_graph/call` 读取蓝图摘要。返回内容包含 `blueprint_path`、`status`、`parent_class`、`graphs`、`variables`、`components` 等字段；这是只读能力，不需要用户确认，也不会修改资产。

安全边界：

- 仍然必须走 `confirm -> UE 前端执行 -> results 回传`。
- v1 不做复杂节点连线、不生成大段蓝图逻辑、不自动放入关卡、不自动保存包。
- `create_blueprint_event_stub` 仅允许 `BeginPlay / Tick / ActorBeginOverlap / ActorEndOverlap`。
- `add_blueprint_node_template` 当前只允许 `print_string`、`branch_print_string`、`sequence_print_strings`、`delay_print_string`、`get_variable`、`set_variable`、`call_function`、`custom_event_print_string`、`enhanced_input_action_event` 与 `enhanced_input_print_string`；自动连线只支持 `entry_event=BeginPlay / ActorBeginOverlap / ActorEndOverlap`、`Custom Event -> PrintString` 或 `Enhanced Input Triggered -> PrintString` 这类固定模板；Custom Event 模板只创建无参数事件并连接到 PrintString；变量模板只支持已有 member variable，不会自动创建变量；函数调用模板只支持当前 Blueprint / 父类上已有的无输入参数、非 Pure 函数；Enhanced Input 模板只支持已有 `UInputAction` 资产；不支持任意节点、删除节点、批量替换节点或任意 pin 连线。
- `connect_blueprint_nodes` 只允许明确 source/target node id 和 pin name 的单次连接；不支持跨 Blueprint、跨 graph、断开已有连接、批量连线或自动猜 pin。
- `compile_blueprint` 只触发一次 UE 编译并返回状态，不自动保存 package，不做循环修复。
- `get_blueprint_graph` 只读，不经过 Proposal；建议仅在本地 TCP 白名单中开放。
- 变量类型只允许常见内置类型、短别名，或 `/Script/`、`/Game/` 开头的项目/引擎类型。
- `/api/v1/editor-operations/results` 的 `result` 是开放对象，后端接受 `applied_fields`、`failed_fields`、`dirty_packages`、`graph_name`、`created_nodes`、`save_policy` 等 UE 侧回传字段；`dirty_packages` 建议传字符串数组，当前不强制固定为某一种 package path 格式。

### 26.1 UMG / Asset 批量操作 v1

I4-4 第一版只补低风险能力：批量资产重命名 Proposal、批量移动资产 Proposal、UMG Widget Tree 只读感知、添加基础 UMG Widget Proposal、复制一个已有非 Panel Widget 的 Proposal，以及删除一个非 root 非 Panel Widget 的 Proposal。不做删除资产、不做自动修复 Redirectors、不做复杂 Widget 生成器或批量重写布局。

批量重命名资产：

```json
{
  "operation_type": "batch_rename_assets",
  "payload": {
    "renames": [
      {
        "asset_path": "/Game/Props/Chair",
        "new_name": "SM_Chair_A"
      },
      {
        "asset_path": "/Game/Props/Table",
        "new_name": "SM_Table_A"
      }
    ]
  }
}
```

后端校验规则：

- `renames` 必须是非空数组，最多 20 项。
- 每项必须包含 `/Game` 下的 `asset_path` 和合法 `new_name`。
- 拒绝重复源资产、重复目标路径和新旧名称相同的项目。
- 后端只生成 preview/proposal；UE 插件确认后才调用 `AssetTools.RenameAssets`。
- 执行器会先校验全量源资产和目标路径，任何一项失败都会整批 blocked，避免半途改名。

批量移动资产：

```json
{
  "operation_type": "move_assets",
  "payload": {
    "asset_paths": [
      "/Game/Props/SM_Chair_A",
      "/Game/Props/SM_Table_A"
    ],
    "target_folder": "/Game/Environment/Props"
  }
}
```

移动资产边界：

- `asset_paths` 必须是非空数组，最多 20 项。
- `target_folder` 必须在 `/Game` 下，且不能与源资产当前目录相同。
- 后端会预览每个 `asset_path -> target_path`，UE 插件确认后使用 `AssetTools.RenameAssets` 移动。
- 和批量重命名一样，任意一项校验失败则整批 blocked；不会自动保存，也不会自动修复 Redirectors。

可选 TCP 只读 UMG Widget Tree 工具：

```text
tool_id: mcp_get_widget_tree
mcp_tool_name: get_widget_tree
transport: mcp_tcp
required_payload_fields: widget_blueprint_path
```

调用参数：

```json
{
  "widget_blueprint_path": "/Game/UI/WBP_MainHUD"
}
```

返回摘要包含 `widget_blueprint_path`、`status`、`parent_class`、`root_widget`、`widgets` 等字段。每个 widget 会尽量返回 `widget_name`、`widget_class`、`is_variable` 和 `slot_class`。这是 read-only 感知能力，不需要用户确认，也不会修改 Widget Blueprint。

添加基础 UMG Widget：

```json
{
  "operation_type": "add_umg_widget",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "TitleText",
    "widget_class": "TextBlock",
    "parent_widget_name": "RootCanvas",
    "text": "Ready",
    "is_variable": true
  }
}
```

Agent Chat 也可以从自然语言生成同一个 Proposal，例如：

```text
Add TextBlock TitleText to WBP_MainHUD under RootCanvas with text 'Mission Ready'
```

设置已有 TextBlock 文本：

```json
{
  "operation_type": "set_umg_widget_text",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "TitleText",
    "text": "Mission Ready"
  }
}
```

设置 CanvasPanelSlot 布局：

```json
{
  "operation_type": "set_umg_widget_layout",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "TitleText",
    "layout": {
      "position": {"x": 20, "y": 30},
      "size": {"x": 300, "y": 48},
      "alignment": {"x": 0.5, "y": 0},
      "anchors": {
        "minimum": {"x": 0, "y": 0},
        "maximum": {"x": 0, "y": 0}
      }
    }
  }
}
```

UMG 写操作边界：

- v1 只支持基础控件：`TextBlock`、`Button`、`Image`、`Border`、`CanvasPanel`、`HorizontalBox`、`VerticalBox`。
- `parent_widget_name` 为空时，若 Widget Blueprint 还没有 root widget，则新控件会成为 root；若已有 root，则默认挂到 root 下。
- 父控件必须是 `PanelWidget`；如果 root 不是 panel，或指定父控件不存在，则执行器 blocked。
- `text` 只对 `TextBlock` 生效；传给其他控件时不会失败整个操作，但会在 `failed_fields` 中说明没有应用。
- `set_umg_widget_text` 只修改已有 `TextBlock` 的文本；如果目标控件不存在或不是 `TextBlock`，UE 执行器会 blocked。
- `set_umg_widget_layout` 只修改挂在 `CanvasPanel` 下的控件，也就是目标控件必须拥有 `CanvasPanelSlot`；v1 只支持 `position`、`size`、`alignment`、`anchors`。
- `set_umg_slot_layout_v2` 只修改 `HorizontalBoxSlot`、`VerticalBoxSlot` 或 `OverlaySlot` 的安全字段；v2 支持 `padding`、`horizontal_alignment`、`vertical_alignment`，Box Slot 额外支持 `size`。
- `set_umg_widget_visibility` 只修改已有控件的 `Visibility`，白名单为 `visible`、`collapsed`、`hidden`、`hit_test_invisible`、`self_hit_test_invisible`。
- `set_umg_widget_appearance` 支持单控件安全外观字段：`render_opacity`、`is_enabled`，以及 TextBlock 专属 `color_and_opacity` 和 `font_size`。
- `set_umg_widget_brush` 支持给单个 `Image` 或 `Border` 控件设置 Brush 资源，资源类型限定为 `texture` 或 `material`。
- `duplicate_umg_widget` 支持复制一个已有非 Panel 子控件到同一父 Panel 下，并尽量复制常见 slot 布局字段。
- `delete_umg_widget` 支持删除一个已有非 root、非 Panel 子控件；v1 不允许删除根控件或 Panel 控件，避免误删整棵子树。
- 不设置动画、绑定、复杂 style 继承和复杂 slot 参数；这些仍放到后续 UMG v2+。

### 26.2 Level / Material 低风险编辑器操作 v1

I4-5 先补两类可控写操作：Level Actor 放置，以及 Material Instance 参数设置。它们都仍然走 `Editor Operation Proposal -> 用户确认 -> UE 插件执行 -> 回传结果`，后端不直接调用 UE Editor API。

放置 Actor 到当前 Level：

```json
{
  "operation_type": "place_actor_in_level",
  "payload": {
    "actor_class": "/Script/Engine.PointLight",
    "actor_label": "KeyLight_A",
    "transform": {
      "location": {"x": 120.0, "y": 50.0, "z": 300.0},
      "rotation": {"pitch": -25.0, "yaw": 45.0, "roll": 0.0},
      "scale": {"x": 1.0, "y": 1.0, "z": 1.0}
    }
  }
}
```

边界：

- `actor_class` 必填，允许 `/Script/...`、`/Game/...` 或 UE 插件可解析的基础类名。
- `actor_label` 可选，只作为编辑器内显示 label。
- `transform` 可选，默认 location/rotation 为 0，scale 为 1。
- v1 不做批量摆放、不删除 Actor、不修改已存在 Actor、不触发导航重建/灯光烘焙等派生流程。

移动已有 Level Actor 时，Agent Chat 可以从 `Project Inventory.level_actors[]`
解析明确的 Actor label/name。示例：`Move BP_EnemySpawner_1 right 200` 会生成
`set_actor_transform`，payload 中包含 `actor_reference=BP_EnemySpawner_1` 和
`transform_delta.location.y=200`。如果没有明确 transform 数值或方向，后端不会编造
移动量，会转为普通回答或 blocked。

2026-06-04 update: Agent Chat can also resolve `this actor` / `selected
actors` from Active Context. If the UE plugin or payload provides
`context.editor_state.current_actor_reference`,
`context.editor_state.selected_actors`, or `payload.selected_actor_references`,
requests such as `Move this actor right 200` and `Arrange selected actors in a
line` can produce pending `set_actor_transform` / `arrange_actors_pattern`
Proposals without repeating the Actor labels in the text.

2026-06-08 update: Agent Chat can also prepare `select_level_actors` for
requests such as `Select actors tagged Enemy` or `Highlight BP_EnemySpawner_1`.
This changes the editor selection only after user confirmation; it does not
move, rename, dirty, or save the level.

For read-only inspection, `GET
/api/v1/editor-operations/inspect/level-actor-detail?actor_reference=...`
returns one Actor record from Project Inventory, including captured transform,
folder, tags, class, blueprint path, and component summaries when the UE plugin
submitted them. It does not create a Proposal or mutate the level.

设置 Material Instance 参数：

```json
{
  "operation_type": "set_material_instance_parameter",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "Roughness",
    "parameter_type": "scalar",
    "value": 0.35
  }
}
```

vector 参数：

```json
{
  "operation_type": "set_material_instance_parameter",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "Tint Color",
    "parameter_type": "vector",
    "value": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0}
  }
}
```

texture 参数使用独立 operation，避免和 scalar/vector 的 `value` 结构混在一起：

```json
{
  "operation_type": "set_material_instance_texture_parameter",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "BaseTexture",
    "texture_path": "/Game/Textures/T_Player_D"
  }
}
```

static switch 参数也使用独立 operation，`value` 必须是布尔值：

```json
{
  "operation_type": "set_material_instance_static_switch",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "UseDetail",
    "value": true
  }
}
```

边界：

- 只支持 Material Instance Constant。
- `set_material_instance_parameter` 的 `parameter_type` 只支持 `scalar` 和 `vector`。
- vector 使用 `r/g/b/a`，也可由后端接受数组、`x/y/z/w`、`rgb(...)` 或 `#RRGGBB` 并归一成 `r/g/b/a`。
- texture 参数走 `set_material_instance_texture_parameter`，只接受明确的 `texture_path`。
- static switch 参数走 `set_material_instance_static_switch`，只接受明确的 `true/false`。
- v1 不编辑材质图谱、不创建 Material Function、不自动保存资产。

建议验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py tests\unit\test_tool_registry.py tests\unit\test_mcp_tool_adapter.py -q
```

### 26.3 Agent Chat 自然语言触发编辑器 Proposal

后端现在会在 Agent Chat 中优先识别明确的编辑器写操作意图。命中后不会让 LLM 返回 Python 脚本或纯文本方案，而是生成可确认的 Editor Operation Proposal。

示例：

```text
把 BP_TestActor 放到当前关卡，位置 0 0 100
```

如果当前上下文或 `selected_assets` 中包含 `/Game/Blueprints/BP_TestActor`，后端会生成：

```json
{
  "operation_type": "place_actor_in_level",
  "payload": {
    "actor_class": "/Game/Blueprints/BP_TestActor.BP_TestActor_C",
    "transform": {
      "location": {"x": 0.0, "y": 0.0, "z": 100.0}
    }
  }
}
```

材质示例：

```text
把 MI_Player 的 Roughness 调到 0.35
```

如果当前上下文或 `selected_assets` 中包含 `/Game/Materials/MI_Player`，后端会生成：

```json
{
  "operation_type": "set_material_instance_parameter",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "Roughness",
    "parameter_type": "scalar",
    "value": 0.35
  }
}
```

材质颜色示例：

2026-06-04 update: Agent Chat can also resolve `this material` / `selected
material` from Active Context. If the UE plugin or payload provides
`selected_material_instances` or `current_material_instance_path`, a request
such as `Set this material Roughness to 0.42` can produce the same pending
`set_material_instance_parameter` Proposal without naming `MI_Player` in the
text.

For read-only inspection, `GET
/api/v1/editor-operations/inspect/material-instance-detail?material_instance_path=...`
returns one Material Instance record from Project Inventory, including parent
material and captured scalar/vector/texture/static-switch parameter values when
the UE plugin submitted them. It does not create a Proposal or save packages.

```text
Set MI_Player material BaseColor to #FF8040
```

如果 Project Inventory 中能解析 `MI_Player`，后端会把 `#RRGGBB` 转成 vector 参数：

```json
{
  "operation_type": "set_material_instance_parameter",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "BaseColor",
    "parameter_type": "vector",
    "value": {"r": 1.0, "g": 0.5019607843, "b": 0.2509803922, "a": 1.0}
  }
}
```

材质贴图示例：

```text
Set MI_Player material BaseTexture to T_Player_D texture
```

如果 Project Inventory 中能解析 `MI_Player` 和 `T_Player_D`，后端会生成：

```json
{
  "operation_type": "set_material_instance_texture_parameter",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "BaseTexture",
    "texture_path": "/Game/Textures/T_Player_D"
  }
}
```

材质静态开关示例：

```text
Enable MI_Player material UseDetail static switch
```

如果 Project Inventory 中能解析 `MI_Player`，后端会生成：

```json
{
  "operation_type": "set_material_instance_static_switch",
  "payload": {
    "material_instance_path": "/Game/Materials/MI_Player",
    "parameter_name": "UseDetail",
    "value": true
  }
}
```

当前边界：

- 如果用户只写 `BP_TestActor` 或 `MI_Player`，但前端没有传 `selected_assets` 或明确 `/Game/...` 路径，后端不会编造资产路径。
- 缺少关键参数时，本轮优先 blocked / clarification，不退回到 Python 脚本。
- UEAgentTool 也兼容直接把 `/Game/.../BP_X` Blueprint 资产路径作为 Actor class 输入，执行时会解析 GeneratedClass。
## 27. Multi-Agent Code Review Chain v1

后端现在在默认 Code Review 之外，新增了一条轻量 Multi-Agent 链：`review_fix_validate`。它用于展示链式审查流程和真实辅助审查，不替代默认 Code Review，也不新增主菜单。

### 触发方式

仍然调用原接口：

```http
POST /api/v1/tasks/code-review
```

在 `payload` 中增加任意一个触发字段：

```json
{
  "user_query": "review and fix this code",
  "enable_multi_agent": true,
  "workflow_mode": "review_fix_validate"
}
```

如果不传这些字段，Code Review 仍走原来的单阶段审查。

### 链路阶段

- `Review`：复用现有 `CodeReviewSkill`，读取选中文件或 inline code，执行规则扫描、KB 检索和可选 LLM 综合审查。
- `Decision Gate`：只有 `high > 0` 或 `medium >= 3` 时进入修复草案阶段；低风险文件会跳过 Generate。
- `Fix Draft`：复用 `CodeGenerateSkill`，根据审查问题生成非破坏式 `generated_items`。
- `Validate`：对生成草案再做一次轻量规则校验，形成 `validate_phase`。

### 返回字段

关键字段：

- `data.multi_agent`：链路摘要、phase 列表、decision gate。
- `data.review_phase`：原代码审查结构化结果。
- `data.generate_phase`：生成草案结果；跳过时为空对象。
- `data.validate_phase`：草案校验结果。
- `data.generated_items`：生成的虚拟代码草案。
- `debug_view.multi_agent`：用于 Debug View 展示完整链路。
- `user_view.blocks[block_type="phase_result"]`：前端可用通用块渲染阶段结果。

### 安全边界

Multi-Agent 链不会写入 UE 工程，也不会绕过 Proposal：

- Generate 阶段强制 `write_mode="draft"`。
- `data.write_policy.written_to_disk=false`。
- `action_proposals=[]`，不创建写入提案。
- 如果未来要让用户把修复草案写入项目，必须单独走 `write_code_files` proposal，并让用户二次确认。

### 前端说明

当前 UE 前端不必强制修改。若前端已有通用 `user_view.blocks` 渲染能力，可以直接显示新增的 `phase_result` 和 `generated_items`。如果想做得更清楚，可在 Code Review 高亮弹窗里新增一个“Multi-Agent Chain”折叠区，读取 `data.multi_agent` 或 `debug_view.multi_agent`。

## 28. Code Review 专项 Benchmark

后端补充了一个离线代码审查专项 benchmark，用于量化 `CodeReviewSkill` 和 `Review -> Generate -> Validate` 多阶段链路的基础效果。它默认关闭 LLM、Embedding 和 Qdrant，因此不需要代理、不需要 API Key，适合本地稳定版留存、回归测试和质量展示。

运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_code_review_benchmark.py --min-recall 0.85 --min-precision 0.85
```

输入数据集：

```text
tests/eval/code_review_benchmark_dataset.jsonl
```

输出结果：

```text
storage/artifacts/evals/code-review-benchmark-latest.json
storage/artifacts/evals/code-review-benchmark-latest.md
```

当前报告指标：

- `recall`：预期规则命中是否被检测到。
- `precision`：检测到的规则命中中，有多少属于预期命中。
- `false_positive_rate`：额外规则命中的比例，用于观察规则是否过宽。
- `clean_case_accuracy`：干净样例是否没有被误报。
- `generated_draft_case_rate`：多阶段链路中触发修复草稿的样例比例。
- `validation_issue_per_generated_file`：生成草稿后验证阶段发现的新风险密度。
- `latency_ms`：单阶段审查和多阶段链路的平均/最大耗时。

当前数据集规模与规则边界：

- 数据集已有 `26` 个原创 UE C++ 短样例，其中包含 `9` 个干净 / 噪声样例、`2` 个仍保留的已知局限样例。
- 干净样例覆盖注释中的风险词、`UPROPERTY` 保护的 UE raw pointer、`TObjectPtr`、`TSoftObjectPtr`、`AsyncTask(ENamedThreads::GameThread)`、轻量 includes、DataTable row 等常见误报来源。
- 规则层现在会跳过纯注释行，不再把 `UPROPERTY` 保护的 UE 指针当成裸指针风险，也不会把回到 GameThread 的 `AsyncTask` 当成后台线程风险。
- 规则层已覆盖常见真实风险：后台线程访问 UObject、同步加载、硬编码资源路径、`ConstructorHelpers::FObjectFinder/FClassFinder`、`LoadClass`、Tick 热路径、Blueprint API surface 过宽、生命周期函数缺少 `Super::` 调用、委托绑定缺少清理路径。
- 当前已知局限保留为量化样例：`FStreamableManager::RequestSyncLoad` 和 Replication lifetime 校验暂未进入默认轻量规则层。
- 最新离线结果：`recall=0.9355`，`precision=1.0`，`false_positive_rate=0.0`，`clean_case_accuracy=1.0`。

当前离线 benchmark 不测 LLM 幻觉率，因为 LLM 调用被显式关闭。后续如果要测 live LLM，可以单独新增一个小型人工标注数据集，检查 LLM 的解释是否引入了“源码中不存在的事实”。不要把 live LLM 评测放进默认 pytest 或默认 benchmark，避免受代理、额度、模型波动影响。

设计边界：

- 这是本地回归 benchmark，不是企业级大规模评测平台。
- 数据集使用原创短代码片段，不依赖外部项目源码。
- Multi-Agent 的 review phase 复用同一套规则检测，因此检出率预期与单阶段 Code Review 一致；多阶段价值主要体现在修复草稿和验证阶段是否被正确触发、是否保持 no-write guarantee。

## 29. Optional MCP Tool Client v2

后端现在有最小 MCP tool client，支持 `stdio` 和 `tcp` 两种本地 transport。它仍是可选工具层，不是 UE 前端主通信协议，也不会替代现有 HTTP API。

### 默认行为

- `MCP_TOOL_ADAPTER_ENABLED=false` 时完全关闭。
- 后端启动和健康检查不会自动拉起外部 MCP server，也不会主动连接 UE 插件 TCP 服务。
- `MCP_AUTO_DISCOVER_ON_STARTUP=false` 默认关闭，避免启动时产生不可控外部进程。
- 只有显式调用 `/api/v1/mcp/tools` 或 `/api/v1/mcp/tools/{tool_name}/call` 时才会尝试连接配置的 transport。

### 配置

连接 stdio server：

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_TRANSPORT=stdio
MCP_STDIO_COMMAND=python
MCP_STDIO_ARGS=D:/Path/To/your_mcp_server.py
MCP_ALLOWED_TOOLS=get_widget_tree,get_target_umg_asset
MCP_STDIO_TIMEOUT_MS=5000
MCP_AUTO_DISCOVER_ON_STARTUP=false
```

连接 UEAgentTool 可选 TCP 工具服务：

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_TRANSPORT=tcp
MCP_TCP_HOST=127.0.0.1
MCP_TCP_PORT=8765
MCP_ALLOWED_TOOLS=ue_agent_tools_list
MCP_TCP_TIMEOUT_MS=3000
```

`MCP_ALLOWED_TOOLS` 是强制安全边界。未在白名单内的工具会在后端调用 MCP server 前被拦截。

UEAgentTool 的 TCP 服务默认关闭，需要在 UE 项目的 `Config/DefaultEngine.ini` 中显式开启：

```ini
[UEAgentTool.EditorToolServer]
bEnabled=true
Host=127.0.0.1
Port=8765
```

当前 TCP 服务只用于工具发现和只读诊断。`tools/list` 会列出 UE 插件已声明的编辑器工具；`tools/call` 只允许 `ue_agent_tools_list` 返回工具目录。资产改名、Static Mesh 设置、创建 Blueprint、添加变量/组件/事件等 confirmed-write 工具即使出现在 tools/list 中，也不能通过 raw TCP 执行，仍必须走 Editor Operation Proposal。

### 调试接口

发现工具：

```http
GET /api/v1/mcp/tools
```

调用白名单内只读工具：

```http
POST /api/v1/mcp/tools/{tool_name}/call
Content-Type: application/json

{
  "arguments": {
    "example": "value"
  }
}
```

返回结果会包含：

- `success / ok`
- `status / reason`
- `tools[]` 或 `result`
- `debug.adapter`
- `debug.initialize`

### 当前边界

- 后端不实现 MCP server；UE 插件可选暴露本地 TCP JSON-RPC 工具服务。
- 不打包或依赖 UMG-MCP。
- Agent Chat 不会自动执行未知 MCP 工具；当前只允许已路由、已 allow-list 的只读
  `get_blueprint_graph` / `get_widget_tree` 尝试走 TCP live sensing，并在失败时回落到
  Project Inventory / 普通 placeholder。
- 不允许 LLM 自动调用未知 MCP 写入工具。
- 写入类 MCP 工具未来也必须先转成 Editor Operation Proposal，由用户确认后再由 UE 前端执行。

### 项目表达

可以这样说明：项目主体是自研 HTTP Agent backend，MCP 是可选工具 transport。这样既能保持当前 UE 前端简单稳定，又为后续接入外部工具生态留下接口，而不是把整个项目绑定到某个 MCP 实现。
## 2026-05-10 后端连通性与 smoke test 补充

当前后端增加了几项内部可维护性补强：RAG 统一 facade、Workflow 可复用节点、轻量 ingestion job queue，以及 LLM fallback 的结构化标记。这些改动不改变 UE 前端已有主接口，也不要求前端 UI 立即调整。

本地验证建议优先查看：

- 本地 smoke test：可直接使用 `README.md` 和本指南中的 HTTP 示例运行。
- `debug_view.tools`：确认本轮用了哪些工具。
- `debug_view.memory_summary`：确认 session summary / long-term memory 是否参与上下文。
- `data.llm_analysis`、`data.llm_review` 或相关 LLM 字段：如果没有配置 LLM key，会以 fallback 方式标记。

边界说明：

- `app/rag/__init__.py` 现在提供统一检索 facade，但旧调用方不会被一次性强制迁移，避免引入回归。
- `app/rag/ingestion/jobs.py` 是本地 in-process job queue，不是 Redis/Celery，不承担企业级后台任务语义。
- UE 前端当前无需修改；如果后续 N2 阶段新增 `debug_view.react_loop` 或更细的 `tool_call_sequence`，再通过交接文档通知前端适配。

## 2026-05-10 轻量 Agent 工具规划补充

阶段 N2 已把 Project QA 的 ReAct Lite 规划逻辑抽出到 `app/agent/tool_planner.py`。这不是把项目改成新的 Agent 框架，而是把原来散在 `TaskService` 里的工具选择、输入清洗和工具调用序列整理成可测试模块。

本阶段新增或强化的调试字段：

- `data.tool_plan.tool_call_sequence`：本次 Project QA 计划调用的工具 ID 顺序。
- `data.react_loop.tool_call_sequence`：Project QA 的 thought/action/observation 调试轨迹中的工具顺序。
- `data.react_loop.mode = "react_lite"`：自由聊天 / Project QA 的受控 ReAct Lite 模式。
- `logs_analyze.data.workflow_trace.mode = "fixed_log_workflow_v1"`：日志分析内部的固定工作流调试轨迹；`react_loop` 暂时作为兼容字段保留。
- `project_inventory.items[].field_view`：当用户询问变量、组件、父类、Nanite、LOD、依赖等字段时，后端会在命中项里附带一个更聚焦的字段视图。

前端兼容性：

- 这些字段都是新增可选字段，旧前端可以忽略，不影响现有 `user_view.blocks`。
- 如果 UE 前端后续想增强 Debug View，Project QA 优先展示 `react_loop.tool_call_sequence` 和 `react_loop.steps`；Logs Analyze 优先展示 `workflow_trace.tool_call_sequence` 和 `workflow_trace.steps`。
- Assets Inspect 面板不变；自由聊天询问“当前项目某个资产有哪些变量/组件/依赖”时，仍走 Project Inventory。

## 2026-05-11 后端稳定版收口清理

本次清理目标是消除源码中的“占位感”，让公开仓库更像一个稳定可维护的本地 Agent 后端，而不是只为展示准备的半成品。

已完成：

- `app/rag/ingestion/__init__.py` 改为真实导出 ingestion pipeline 能力、chunker、loader、parser 和轻量 ingestion job queue。
- `app/rag/indexing/__init__.py` 改为真实导出 lexical tokenizer、embedding helper 和 Qdrant adapter 边界。
- `app/rag/retrieval/__init__.py` 改为真实导出 hybrid retrieval、agentic refinement、citation builder 和 rerank helper。
- 删除未被主链路引用的 `app/services/file_service.py` 占位文件。
- 新增 RAG 子包导入契约测试，确认公开导出不会引入循环依赖。

对使用者的影响：

- HTTP API 没有变化。
- UE 前端不需要修改。
- `user_view`、`debug_view`、`data` 的结构没有变化。
- RAG、local grep、Project Inventory、Code Review、Code Generate、Logs Analyze、Assets Inspect 的使用方式不变。

验证建议：

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q
```

如果要做完整本地回归，可以额外运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\eval -q
.\.venv\Scripts\python.exe -m pytest tests\integration -q
```

当前仍然合理保留的非完成态标记：

- `deferred_task_types` 表示已从当前产品范围隐藏的兼容任务，不代表核心功能缺失。
- `langsmith_stub / local_stub` 表示 LangSmith 和 OpenTelemetry 只保留本地契约，不作为强依赖。
- `tool_placeholder` 只会出现在未纳入当前 5 个核心 Skill 的旧任务路由中。

## 2026-05-11 Project QA Grounding 回归测试

本次补充了 `tests/unit/test_project_qa_grounding.py`，用于把 Project QA 的关键防幻觉边界从大型集成测试中抽成更小的单元测试。

覆盖点：

- 当前项目事实类问题必须依赖 Project Inventory，例如“当前项目有哪些资产”“选中的 StaticMesh 是否开启 Nanite”。
- 通用 UE 知识问题不能被误判成当前项目事实，例如 Actor 生命周期、Enhanced Input 绑定、TArray/TMap 区别。
- 当 Project Inventory 没有快照时，后端应明确拒绝列出当前项目资产，而不是用知识库或 LLM 常识编造答案。
- 当 Project Inventory 命中蓝图资产时，fallback 摘要应只使用快照里的字段，例如 `parent_class`、`components`、`variables`。

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_project_qa_grounding.py -q
```

这组测试不依赖 LLM、Qdrant、UE 编辑器或代理，适合放在默认 CI 中长期守护。

## 2026-05-11 Code Review LLM Fallback 回归测试

本次补充了 `tests/unit/test_code_review_llm_fallback.py`，用于保护代码审查面板里的 LLM 分析卡片，避免模型返回伪 JSON、不完整 JSON 或无法解析的结构化文本时，前端高亮区直接显示原始 JSON。

覆盖点：

- LLM 返回类似 `{summary: "...", issue: ...}` 的不标准 JSON 时，后端会尽量提取可读的 summary、issue 和 recommendation。
- LLM 返回无法可靠解析的 JSON-like 文本时，后端只在 Debug View 保留原始内容，用户卡片改用安全的 fallback 文案。
- `data.llm_analysis.text`、`key_points`、`priority` 会保持面向 UI 的稳定结构，不要求 UE 前端额外解析原始模型文本。

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_code_review_llm_fallback.py -q
```

这组测试不依赖 live LLM，主要用于防止“代码审查结果从摘要卡片退化成完整 JSON”的回归。

## 2026-05-11 Code Review Rules 回归测试扩充

本次扩充了 `tests/unit/test_code_review_rules.py`，把 Code Review 规则层从“主要测误报抑制”扩展到“核心规则触发 + 误报抑制”并存。

新增覆盖的 `rule_id`：

- `raw_pointer_ownership`
- `sync_load_usage`
- `hardcoded_asset_path`
- `tick_hot_path`
- `include_pollution`
- `blueprint_surface`
- `lifecycle_super_call`
- `delegate_lifetime`

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_code_review_rules.py -q
```

这组测试不依赖 LLM，适合作为 Code Review 规则层的长期质量门。

## 2026-05-13 Code Review Rules v2

本次把上一轮 benchmark 中的 4 个已知缺口升级为正式回归样例：

- `ConstructorHelpers::FObjectFinder/FClassFinder` 会归类为 `sync_load_usage`。
- `LoadClass` / `StaticLoadClass` 会归类为 `sync_load_usage`。
- `BeginPlay`、`EndPlay`、`NativeConstruct`、`NativeDestruct`、`NativeOnInitialized`、`BeginDestroy` 等生命周期函数定义如果没有匹配的 `Super::` 调用，会返回 `lifecycle_super_call`。
- `.AddDynamic`、`.AddUObject`、`.AddLambda`、`.AddRaw`、`.AddSP` 等委托绑定如果当前片段没有 `RemoveDynamic`、`RemoveAll`、`Clear`、`Unbind` 等清理线索，会返回 `delegate_lifetime`。

为了避免 benchmark 变成“全绿但不诚实”的展示，数据集中仍保留 2 个真实已知局限：`RequestSyncLoad` 和 Replication lifetime。当前离线结果为 `recall=0.9355`、`precision=1.0`，更适合展示“可量化、可解释、持续改进”的规则边界。

## 2026-05-11 Project QA Local Grep Fallback 回归测试

本次补充了 `tests/unit/test_kb_service_local_fallback.py`，用于确认没有向量模型、没有 Qdrant，甚至当前 DB lexical index 没有命中时，Project QA 仍然可以用 `KB_SOURCE_PATHS` 指向的本地 markdown/code 文件做可解释 fallback。

覆盖点：

- `RAG_MODE=hybrid` 且 `EMBEDDING_ENABLED=false` 时，检索会稳定降级到 `lexical_only`，不会探测 Qdrant。
- 当 DB 中没有可用 chunk，但本地文件命中时，`retrieval_quality_gate.local_retrieved_count` 会记录 local grep 证据数。
- local grep 命中会进入 `retrieved_docs`，并带上 `retrieval_source = "local_grep"`。
- 如果请求显式传入 `disable_local_search=true`，`local_search.reason` 会返回 `disabled_by_payload`，而不是误写成 `rag_hits_available`。

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_kb_service_local_fallback.py -q
```

这组测试强化的是“无向量也可用、降级原因可解释”的边界。UE 前端无需修改；如果 Debug View 展示 `data.retrieval_trace.local_search`，可以直接读取其中的 `status/reason/summary/items`。

## 2026-05-11 Function Calling Adapter 小步实现

后端新增 `app/agent/function_calling_adapter.py`。它不是新的主 Agent 框架，也不会替换当前 ReAct Lite / deterministic planner，而是给未来接入模型原生 tool calling 留出一个很薄的适配层。

当前能力：

- 把 Tool Registry 中允许自由聊天使用的只读工具转换成 provider-style function schema。
- 默认只导出 `read_only` 工具，例如 `retrieve_project_knowledge`、`query_project_inventory`、`read_project_file`。
- 不默认导出 `confirmed_write` 工具，例如资产重命名、写入代码、调整 Static Mesh 设置等。
- 把模型返回的 function/tool call 归一化为现有 planner contract：`requested_tool_ids` 与 `tool_inputs_by_id`。
- 对参数做最小白名单清洗，只保留 ToolSpec 中声明的 schema / payload 字段。

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_function_calling_adapter.py -q
```

这一步的意义是“为后续框架化留接口”，不是要求 UE 前端修改。现阶段 UE 前端仍然调用原有 HTTP API；后端也仍然通过 Tool Registry、Proposal 和 Skill Executor 控制工具执行边界。

## 2026-05-11 Graph Adapter 蓝图

后端新增 `app/agent/graph_adapter.py`，用于把现有轻量 Multi-Agent 链 `review -> fix_draft -> validate` 表达成可序列化的图蓝图。它不是 LangGraph 运行时，也不会引入新依赖；当前真正执行仍然由 `ReviewFixValidateChain` 完成。

当前能力：

- `review_fix_validate_graph_spec()` 返回当前链路的节点、边、入口、终止节点。
- `langgraph_adapter_blueprint()` 返回一个不依赖 LangGraph 的 adapter blueprint，方便后续替换或对接。
- `review` 和 `validate` 是 `read_only`，`fix_draft` 是 `plan_only`。
- 图蓝图不允许绕过 Proposal 流程写入项目文件。

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_graph_adapter.py -q
```

这一步主要服务于架构表达和后续扩展，不要求 UE 前端修改。

2026-06-02 更新：Graph Adapter 现在增加了可选框架 readiness 诊断。

- 新配置：`AGENT_GRAPH_FRAMEWORK=framework_neutral | langgraph_optional | langgraph_active`。
- 默认值：`framework_neutral`，即继续使用当前自研轻量图，不引入额外依赖。
- `langgraph_optional`：不改变运行时，只在 Debug View 中标记 LangGraph 是否可作为迁移候选。
- `langgraph_active`：声明希望 LangGraph 接管图编排；如果没有安装 `ue-agent-backend[agent]`，Debug View 会显示 `blocked_missing_dependency`，不会破坏当前自研运行路径。
- 新 Debug 字段：`debug_view.graph_framework`。
- 新函数：`graph_framework_readiness_report()`，用于说明图 ID、候选框架、依赖状态、迁移边界和推荐动作。

重要边界：

- LangGraph 只允许未来接管“图编排 / 条件边 / checkpointable workflow”。
- Tool Registry、Proposal 确认、安全策略、UEAgentTool 真正执行 Editor API 的边界不变。
- 当前 UE 前端无需修改。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_graph_adapter.py tests\unit\test_settings.py -q
```

## 2026-05-11 Assembly Sprint N8 小收口

N8 目标是把已经存在的 facade / workflow node / trace 组件接到主链路，减少“看起来有模块但生产链路没使用”的割裂感。本次仍不新增 UE 前端必改接口。

已完成：

- Logs Analyze 的调试轨迹从 `bounded_log_react_v1` 改为更诚实的 `fixed_log_workflow_v1`。
- Logs Analyze 现在在 `data.workflow_trace` 和 `debug_view.workflow_trace` 暴露固定工作流轨迹。
- 为前端兼容，`data.react_loop` 和 `debug_view.react_loop` 暂时仍保留，并指向同一份 workflow trace。
- `KnowledgeBaseService.project_qa()` 已改用 `app.rag.retrieve_knowledge()` facade，而不是直接拼接底层 `retrieve()` 与 `refine_retrieval_if_needed()`。
- Code Review workflow 已小步复用 `append_step_result_node`、`record_tool_output_node`、`retrieve_support_notes_node`、`aggregate_step_results_node`。
- Code Review 核心规则测试已扩充。

运行建议：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_logs_workflow_trace.py tests\unit\test_code_review_rules.py tests\unit\test_kb_service_local_fallback.py -q
```

前端影响：

- 普通 UI 无需修改。
- 如果 Debug View 想更准确展示日志分析链路，优先读取 `debug_view.workflow_trace`。
- 旧的 `debug_view.react_loop` 暂时可继续读取，但它现在是兼容字段，不代表 LLM 自主多轮 ReAct。

## 2026-05-11 MCP Transport Boundary 回归测试

后端已有 MCP stdio client、MCPToolAdapter、`/api/v1/mcp/tools` 调试接口，以及 fixture server 级测试。本次补充一条更明确的边界测试：MCP 只是可选工具 transport，不是 UE 前端主协议，也不能绕过 Proposal 写入流程。

覆盖点：

- `build_mcp_capability()` 的 `mode = optional_tool_transport`。
- `frontend_protocol = http`，UE 前端仍然走现有 HTTP API。
- `tool_layer_only = true`，MCP 不接管 TaskService 主链路。
- `free_chat_auto_execute = false`，自由聊天不会自动执行 MCP 工具。
- `write_tools_require_proposal = true`，写入类工具未来即使来自 MCP，也必须先转成 Proposal。

2026-05-16 更新：

- 编辑器操作意图检测已经迁入 `EditorOperationService.detect_request()`。
- Proposal 构建统一走 `EditorOperationService.build_action_proposal()` / `try_build_action_proposal()`。
- 资产检查生成的重命名 Proposal 统一走 `EditorOperationService.build_asset_inspect_rename_proposal()`。
- `TaskService` 不再保存编辑器操作检测和 Proposal 拼接私有 helper。

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_mcp_tool_adapter.py -q
```

UE 前端无需修改。只有未来要让 MCP 工具参与实际编辑器写操作时，才需要新增“操作提案 -> 用户确认 -> UE Editor API 执行”的前端链路适配。
## 30. Controlled Web Search v1

后端现在补充了受控 Web Search 证据层，用来解决“本地知识库没有覆盖，但用户明确要查官方/最新资料”这类问题。它不是通用联网聊天，也不会默认开启，更不会把网页全文自动写入知识库。

### 默认边界

- 默认 `WEB_SEARCH_ENABLED=false`，所有现有功能保持原行为。
- 当前 provider 只建议使用 `mock` 做离线验证；真实联网 provider 以后只作为本地 smoke 接入，不进入默认 CI。
- Web Search 只作为 Project QA 的补充证据。Local KB、Project Inventory、团队规则、选中文件内容优先级更高。
- Web Search 结果不会自动污染 `knowledge/` 或向量库。
- 所有结果都会进入 `data.web_search`、`debug_view.web_search` 和 `retrieval_trace.web_search`，方便排查为什么触发、返回了什么、为什么跳过。

### 配置示例

```env
WEB_SEARCH_ENABLED=false
WEB_SEARCH_PROVIDER=disabled
WEB_SEARCH_MAX_QUERIES=1
WEB_SEARCH_MAX_RESULTS=5
WEB_SEARCH_TIMEOUT_MS=5000
WEB_SEARCH_MAX_CONTENT_CHARS=1200
WEB_SEARCH_ALLOWED_DOMAINS=dev.epicgames.com,docs.unrealengine.com,unrealengine.com
WEB_SEARCH_DOMAIN_BOOSTS=dev.epicgames.com:0.25,docs.unrealengine.com:0.25,unrealengine.com:0.15
WEB_SEARCH_MOCK_RESULTS_PATH=
```

离线 mock 示例：

```env
WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=mock
WEB_SEARCH_MOCK_RESULTS_PATH=./storage/artifacts/mock-web-results.json
```

mock 文件格式：

```json
{
  "results": [
    {
      "title": "Enhanced Input in Unreal Engine",
      "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input-in-unreal-engine",
      "snippet": "Enhanced Input uses Input Actions and Mapping Contexts.",
      "source_type": "official"
    }
  ]
}
```

### 触发方式

- 显式触发：用户问“联网查一下”“搜一下官方文档”“latest docs”等，且 `WEB_SEARCH_ENABLED=true`。
- 隐式触发：本地 RAG/local grep 没有足够证据，且问题明显是 UE/C++/编辑器研发相关主题。
- 跳过：本地 KB 已经有证据、普通闲聊、非 UE 技术问题、`disable_web_search=true`、provider 关闭、预算为 0。

### 前端读取字段

当前不强制 UE 前端修改。若前端想增强 Debug View，可以读取：

- `data.web_search.status/reason/summary/items`
- `debug_view.web_search`
- `retrieval_trace.web_search`
- `data.source_arbitration`
- `data.retrieval_quality_gate.web_retrieved_count`

如果前端不读取这些字段，原有 User View 和 citations 渲染仍可继续工作。

## 2026-05-15 Retrieval Pipeline + Web Search Eval

本轮把 Project QA 的检索增强链路收拢到 `app/rag/pipeline.py`。服务层不再直接拼接 RAG、local grep 和 Web Search 的细节，而是读取一个稳定的 evidence package，再继续生成兼容旧接口的回答结构。

当前 Project QA 证据顺序：

```text
RAG / lexical retrieval
-> local grep fallback
-> optional controlled Web Search
-> source_arbitration
-> retrieval_quality_gate
```

保留的前端兼容字段：

- `data.retrieval_trace`
- `data.retrieval_quality_gate`
- `data.local_search`
- `data.web_search`
- `data.source_arbitration`
- `data.citations`
- `debug_view.web_search`

新增离线评测：

```powershell
.\.venv\Scripts\python.exe scripts\run_web_search_eval.py --min-success-rate 1 --min-safety-pass-rate 1
```

该评测不联网，数据集在 `tests/eval/web_search_policy_dataset.jsonl`，主要覆盖：

- 本地 KB 证据足够时不触发 Web Search。
- 用户显式要求 official/latest/search 时触发 mock provider。
- KB 证据不足且问题属于 UE 技术主题时触发 mock provider。
- 普通闲聊和非 UE 问题不触发。
- `localhost` / `127.0.0.1` 等不安全 URL 会被过滤。
- 不在 allow-list 中的社区域名不会进入最终证据。
- mock provider 路径缺失时任务降级但不崩溃。

UE 前端本轮仍无需强制修改。若要增强 Debug View，可显示 `source_arbitration.source_counts`、`web_search.summary.skipped_domain_count` 和 `retrieval_quality_gate.web_retrieved_count`。

## 2026-05-15 Web Memory v1

Web Memory 是 Controlled Web Search 的轻量本地缓存层，用来避免同类 UE 官方资料问题每次都重新触发 Web Search。它默认关闭，且不属于知识库主索引。

边界：

- 默认 `WEB_MEMORY_ENABLED=false`。
- 只保存 `URL/domain/title/snippet/score/source_type/provider/TTL/feedback`。
- 不保存网页全文，不爬取网页正文，不写入 `knowledge/`，不写入向量库。
- 召回优先级低于 Local KB、Project Inventory、选中文件、团队规则。
- 用户反馈只影响后续排序，不会把内容自动标记为“事实真理”。

配置：

```env
WEB_MEMORY_ENABLED=false
WEB_MEMORY_TTL_DAYS=30
WEB_MEMORY_MAX_RESULTS=5
WEB_MEMORY_MAX_ENTRIES=200
WEB_MEMORY_MIN_SCORE=0.08
WEB_MEMORY_FTS_ENABLED=true
```

Project QA 证据顺序现在是：

```text
RAG / lexical retrieval
-> local grep fallback
-> optional Web Memory recall
-> optional Controlled Web Search
-> source_arbitration
-> retrieval_quality_gate
```

调试接口：

- `GET /api/v1/web-memory/status`
- `POST /api/v1/web-memory/search`
- `POST /api/v1/web-memory/entries/{entry_id}/feedback`
- `POST /api/v1/web-memory/prune`

前端可选字段：

- `data.web_memory`
- `data.web_memory_store`
- `data.context_bundle.web_memory`
- `data.context_bundle.memory.sources`
- `debug_view.web_memory`
- `debug_view.web_memory_store`
- `debug_view.context_bundle.web_memory`
- `debug_view.context_bundle.memory.sources`
- `data.retrieval_quality_gate.web_memory_retrieved_count`
- `data.source_arbitration.source_counts.web_memory`

Context Bundle 行为：

- `WEB_MEMORY_ENABLED=true` 时，每次任务构建 `context_bundle_v1` 会额外尝试召回最多 3 条 Web Memory。
- 命中内容会进入 `context_bundle_prompt_excerpt()`，让 Direct Answer / Project QA 的 LLM 合成可以复用缓存网页证据。
- `context_bundle.memory.sources` 会解释本轮有哪些记忆 provider 参与、状态是什么、命中几条。
- 这仍然是缓存证据，不是正式 KB；需要长期沉淀时，应走人工 curation，再写入 `knowledge/` 后 reindex。

### Web Memory FTS5 召回

`WEB_MEMORY_FTS_ENABLED=true` 时，SQLite 环境会尝试创建本地 FTS5 虚拟表，用于对已缓存的 Web Search 摘要做全文召回。它只索引 `entry_id/title/domain/snippet`，不保存网页全文，也不会写入正式知识库。

兼容边界：

- 如果当前 SQLite 不支持 FTS5，后端自动回退到原来的 Python token 召回。
- 如果 FTS5 对中文或特殊查询没有命中，后端也会回退到 Python token 召回。
- `data.web_memory.summary.search_mode` 会显示 `sqlite_fts5`、`python_token_fallback` 或 `python_token`。
- `data.web_memory.summary.fts5` 会显示是否启用、是否命中、同步/搜索诊断。
- `data.web_memory.summary.ranking_policy` 会显示 Web Memory 排序公式。
- `data.web_memory.items[].ranking` 会显示每条缓存证据的排序解释，例如 `matched_terms`、`lexical_score`、`quality_score`、`feedback_boost`、`fts_score`、`score_source`。
- UE 前端不需要修改；这些字段主要给 Debug View 和后端调试使用。

### Web Memory Ranking Diagnostics

Web Memory recall now returns additive ranking diagnostics.

New fields:

- `data.web_memory.summary.ranking_policy`
- `data.web_memory.items[].ranking`

Ranking breakdown includes:

- `score`：最终用于排序的分数。
- `score_source`：`python_token` 或 `fts5_blend`。
- `matched_terms` / `matched_term_count`：query 中哪些 token 命中标题、摘要或域名。
- `lexical_score`：词法命中比例。
- `quality_score` / `source_score`：来源质量与原始搜索分数。
- `helpful_count` / `unhelpful_count` / `feedback_boost`：用户反馈对排序的影响。
- `fts_score` / `fts_blended_score`：FTS5 命中时的辅助分数。

Boundary:

- 不写入正式知识库。
- 不抓取网页全文。
- 不改变 Web Memory API 旧字段。
- 不要求 UE 前端修改；Debug View 可选展示 ranking breakdown。

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_web_memory_service.py tests\unit\test_memory_providers.py -q
```

### Knowledge Curation 建议

Project QA 现在会返回 `knowledge_curation` 诊断字段，用于提示“哪些问答暴露了本地知识库缺口”。它只做建议，不会自动写入 `knowledge/`、SQLite 文档表或向量库。

触发场景：

- 本地 KB / local grep 没有足够证据。
- Web Memory 或 Controlled Web Search 找到了可参考证据。
- 或 retrieval quality gate 判断证据不足，需要人工补文档。

返回位置：

- `data.knowledge_curation`
- `retrieval_trace.knowledge_curation`
- `debug_view.knowledge_curation`

字段含义：

- `status`：`suggested` 或 `not_needed`。
- `writes_to_kb=false`：不会自动写知识库。
- `auto_apply=false`：必须人工审核、蒸馏、改写。
- `candidates[]`：候选标题、来源、建议 domain、证据摘要和安全说明。

推荐用法：

- 后端开发者定期查看 Debug View 中的 `knowledge_curation.candidates`。
- 只把确认正确、适配本项目边界的内容手动写入 `knowledge/`。
- 写入后重启或调用 reindex，让 KB / lexical retrieval / vector retrieval 重新索引。

## 2026-05-15 Retrieval Pipeline W5A 小重构

这一轮没有改变任何 UE 前端接口，只是把 Project QA 检索链路内部拆得更清楚：

- `app/rag/pipeline.py`：继续负责按顺序调度 `RAG -> local grep -> Web Memory -> Web Search`。
- `app/rag/evidence_normalizer.py`：负责把不同来源转成统一的 `retrieved_docs` / `citations` 形状。
- `app/rag/source_policy.py`：负责 `source_arbitration`、`retrieval_quality_gate` 和 warning 合并。

为什么这样拆：

- 后续如果新增真实 Web Search provider、更多本地记忆来源或更细的 domain policy，不需要继续堆到 `pipeline.py`。
- Debug View 字段保持稳定，前端仍读取原来的 `data.source_arbitration`、`data.retrieval_quality_gate`、`data.web_search`、`data.web_memory`。
- 单元测试可以直接覆盖来源优先级和质量门控，不必每次构造完整 Task 请求。

本轮新增验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_kb_service_local_fallback.py tests\unit\test_web_memory_service.py tests\unit\test_retrieval_source_policy.py -q
```

UE 前端不需要修改。

## 2026-05-15 Web Search Real Provider W6

后端现在补充了可选真实 Web Search provider：`brave`。它默认不启用，不进入 CI，也不会影响没有 API Key 的本地启动。

配置示例：

```env
WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=brave
WEB_SEARCH_API_KEY=your_brave_search_api_key
WEB_SEARCH_ENDPOINT=
WEB_SEARCH_ALLOWED_DOMAINS=dev.epicgames.com,docs.unrealengine.com,unrealengine.com
WEB_SEARCH_MAX_RESULTS=5
WEB_SEARCH_TIMEOUT_MS=5000
```

说明：

- `WEB_SEARCH_ENDPOINT` 留空时使用 Brave Search Web API 默认端点。
- `WEB_SEARCH_ALLOWED_DOMAINS` 仍然生效，建议继续限制在 Epic / Unreal 官方域名。
- provider 请求失败、没有 API Key、超时或没有命中时，会返回 `status=error` 或 `reason=no_matching_provider_results`，不会让 Project QA 整体崩溃。
- Web Search 结果仍然只是补充证据；本地 KB、Project Inventory、选中文件和团队规则优先级更高。

手动 smoke：

```powershell
.\.venv\Scripts\python.exe scripts\run_web_search_smoke.py --query "Unreal Engine Enhanced Input official docs"
```

如果只是确认“关闭状态下不会出错”，可运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_web_search_smoke.py --allow-disabled
```

UE 前端不需要修改；现有 `data.web_search` / `debug_view.web_search` 字段会继续承载 provider、status、reason、summary 和 items。

## 2026-05-16 Task Handler Adapter v1

后端开始推进 Improv1 中的 `TaskService Strategy 拆分`，但采用低风险分阶段迁移，不做一次性大爆炸重构。

当前完成的是第一阶段：

- 新增 `app/services/task_handlers/` 包。
- 新增 `TaskExecutionContext`，统一描述任务执行所需的 request、routing、task_id、run_id、trace_id、chat_config、context_bundle。
- 新增 `RouteExecutionDispatcher`，把 `_execute_route()` 中的任务分发逻辑移出 `TaskService`。
- 当前 handler 是 adapter：先调用现有 `TaskService._execute_*()` 方法，不改变具体业务输出。
- `debug_view.task_handler` 会记录 `handler_id` 和 `strategy=task_handler_adapter_v1`，方便 Debug View 或复盘时确认本轮由哪个 handler 处理。

为什么先这样做：

- 保持 UE 前端响应契约不变。
- 保持现有 5 个核心 Skill 行为不变。
- 先把“选择哪个执行器”的职责从 `TaskService` 拆走，再逐步把 Project QA、Direct Answer、Config Validate 等具体逻辑迁移到独立 handler。

当前不会做：

- 不把 `TaskService` 立刻缩到 200 行。
- 不改 Router 为 signal detector。
- 不把 ToolSpec 立即改成全量可执行接口。
- 不要求 UE 前端修改。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_task_route_dispatcher.py -q
```

本轮不要求 UE 前端修改；如果不显示这些字段，原有回答和引用渲染仍可继续工作。

## 2026-05-16 Direct Answer Handler migration

This is an internal backend refactor only. The `direct_answer` free-chat path now runs through `app/services/task_handlers/direct_answer.py` instead of a large method inside `TaskService`.

What changed:

- `RouteExecutionDispatcher` still selects the route handler.
- `DirectAnswerHandler` now owns live LLM direct-chat execution, fallback text, self-reflection, `retrieval_trace.mode=not_used`, and `llm_direct_answer` debug tool output.
- `TaskService` still owns task lifecycle, persistence, events, context helpers, runtime profile loading, and response composition.
- UE frontend request and response contracts are unchanged.

Why this matters:

- Free chat is now a real extracted handler rather than only an adapter call.
- Future handlers can be migrated one by one without a large risky rewrite.
- Debug View can continue to read `debug_view.task_handler.handler_id=direct_answer`.

Validation:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit\test_task_route_dispatcher.py tests\integration\test_system_and_tasks.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

UE frontend impact: no mandatory change.

## 2026-05-17 ToolContext Executor Runtime Trial

The backend now has a small executor runtime at `app/tools/executor_runtime.py`.

Purpose:

- Load the executor path declared by `ToolSpec.executor`.
- Execute the tool through `ToolContext`.
- Return a normalized `ToolResult`.
- Keep latency, error, and debug envelope generation consistent.

Migrated production paths:

- `ProjectQAHandler` uses `read_project_file` through `ToolContext -> executor -> ToolResult`.
- `ConfigValidateHandler` uses `validate_design_config` through `ToolContext -> executor -> ToolResult`.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_tool_executor_runtime.py tests\unit\test_tool_registry.py tests\integration\test_system_and_tasks.py::test_agent_chat_project_qa_can_read_current_project_file tests\integration\test_system_and_tasks.py::test_config_validate_returns_report_and_artifact -q
```

UE frontend impact: no mandatory change. Existing response fields are preserved.

## 2026-05-18 Active Context for editor operations

The backend now keeps a lightweight reference to recent confirmed Unreal Editor operations in the per-request Context Bundle. This is meant for follow-up instructions such as "set that material roughness to 0.55" after the user has already confirmed and executed a Material Instance proposal.

Where to inspect it:

- `debug_view.active_context.editor_operation.status`
- `debug_view.active_context.editor_operation.last_successful`
- `debug_view.active_context.editor_operation.recent_count`
- `debug_view.context_bundle.recent_editor_operations`

Current behavior:

- Only UE plugin execution results reported through `POST /api/v1/editor-operations/results` are reused.
- The stored summary is compact: proposal id, operation type, tool id, execution state, target asset/class/parameter, result summary, and undo hint.
- Agent Chat can reuse the recent target for low-risk follow-up proposal generation, for example a second Material Instance parameter change without requiring the frontend to resend `selected_assets`.
- The backend still only creates an Editor Operation Proposal. The UE frontend must still ask the user to confirm, execute with Editor API, and report the result.

Frontend impact:

- No mandatory UI/API change.
- Existing proposal rendering and confirmation flow remain valid.
- Debug View may optionally display `active_context.editor_operation.last_successful` to help users understand why "that material" or "previous actor" was resolved.

## 2026-05-18 Project Inventory candidates for editor operations

Agent Chat editor-operation planning can now use compact Project Inventory candidates when the user did not select an asset in the UE Content Browser.

Examples:

- If Project Inventory contains `BP_EnemySpawner`, a chat request like `Place BP_EnemySpawner in the current level at location 10 20 30` can produce a `place_actor_in_level` proposal.
- If Project Inventory contains `MI_Player`, a chat request like `Set MI_Player material Roughness to 0.25` can produce a `set_material_instance_parameter` proposal.

Debug fields:

- `debug_view.active_context.inventory.query_candidate_count`
- `debug_view.context_bundle.project_inventory_context.query_candidates`
- `debug_view.context_bundle.project_inventory_context.query_summary`

Boundary:

- The backend only trusts explicit asset names or paths from the user query, selected assets, recent confirmed operation context, or Project Inventory candidates.
- If no path can be resolved, the operation is blocked instead of fabricating a `/Game/...` path.
- UE frontend does not need to change for this backend behavior, but richer Project Inventory snapshots will improve resolution quality.

## 2026-05-18 Level Actor Transform Proposal

`Editor Operation Bridge` now includes `set_actor_transform`, a confirmed-write proposal for modifying one existing Actor in the current editor level.

Supported request forms:

- Explicit proposal API: `operation_type=set_actor_transform`.
- Agent Chat follow-up: after a successful `place_actor_in_level` result is reported, the user can say `Move that actor right 200`.
- Selected actor payloads can also be used if the UE frontend sends `context.editor_state.selected_actors` or `payload.selected_actors`.

Payload shape:

```json
{
  "actor_reference": "BP_TestActor_1",
  "transform_mode": "delta",
  "transform_delta": {
    "location": {"x": 0, "y": 200, "z": 0}
  }
}
```

For `transform_mode=absolute`, use `transform` instead of `transform_delta`. Supported fields are `location`, `rotation`, and `scale`.

Safety boundary:

- Backend creates a Proposal only.
- UE frontend executes only after user confirmation.
- UE frontend finds the Actor by exact actor label, object name, or object path.
- The operation uses editor transaction/undo and marks the level dirty, but does not auto-save.
- Deleting actors, batch transform, snapping, navigation/light rebuild, and procedural placement remain out of scope for this slice.

## 2026-05-22 Level Actor Metadata Proposal

`Editor Operation Bridge` now includes `set_actor_metadata`, a confirmed-write proposal for organizing one existing Actor in the current editor level.

Supported fields:

- `actor_label`: rename the editor label of one Actor.
- `folder_path`: move the Actor into an editor outliner folder path.
- `tags`: replace, append, or remove Actor tags with `tag_mode=replace|append|remove`.

Payload shape:

```json
{
  "actor_reference": "BP_EnemySpawner_1",
  "metadata": {
    "actor_label": "EnemySpawn_A",
    "folder_path": "Gameplay/Spawners",
    "tags": ["Spawner", "Enemy"],
    "tag_mode": "append"
  }
}
```

Agent Chat can also build the same Proposal from Project Inventory, for example:

```text
Rename actor BP_EnemySpawner_1 label to EnemySpawn_A
```

Safety boundary:

- Only one Actor is edited per Proposal.
- Actor lookup uses exact actor label, object name, or object path.
- The UE plugin uses an editor transaction and marks the level dirty, but does not auto-save.
- Actor deletion, asset rename/move, batch organization, World Partition operations, and procedural placement are out of scope for this operation.

## 2026-05-17 Knowledge Curation Artifact Export

Project QA already returns `knowledge_curation` diagnostics when local KB evidence is weak but controlled Web Search or Web Memory finds useful evidence. This stage adds a manual export path so backend maintainers can review those suggestions as files instead of digging through Debug View every time.

Command:

```powershell
.\.venv\Scripts\python.exe scripts\export_knowledge_curation.py --output-dir storage\curation
```

What it does:

- Reads high-value Web Memory entries by default.
- Scores candidates using confidence, source score, quality score, helpful feedback, recall count, and official-domain boost.
- Writes a Markdown review file and a JSON payload under `storage/curation`.
- Never writes into `knowledge/`, SQLite KB documents, or Qdrant automatically.

Export from a saved task/debug payload:

```powershell
.\.venv\Scripts\python.exe scripts\export_knowledge_curation.py --input path\to\task-response.json --output-dir storage\curation
```

Review workflow:

- Open the generated Markdown file.
- Keep only candidates that are clearly useful for UE or the current project.
- Rewrite the evidence into a short local note instead of copying web text verbatim.
- Place the distilled note in the correct `knowledge/` domain folder.
- Run `POST /api/v1/knowledge-base/reindex` or restart the backend if you rely on startup seeding.

UE frontend impact: no mandatory change. The existing Debug View can keep showing `knowledge_curation`; this exporter is a backend maintenance tool.

## 2026-05-17 I2-F6 Backend Validation Snapshot

This snapshot closes the Improv2 cleanup round. It does not add new frontend requirements; it records the backend checks used before handing the project back for optional UE plugin smoke testing.

Commands run locally:

```powershell
.\.venv\Scripts\python.exe scripts\run_regression_suite.py --output storage\artifacts\regression\i2-f6-regression-latest.json
.\.venv\Scripts\python.exe scripts\run_web_search_eval.py --min-success-rate 1 --min-safety-pass-rate 1
.\.venv\Scripts\python.exe scripts\run_code_review_benchmark.py --output storage\artifacts\evals\code-review-benchmark-latest.json --markdown-output storage\artifacts\evals\code-review-benchmark-latest.md
```

Observed results:

- Regression suite: `overall_ok=true`.
- Full pytest inside regression suite: passed.
- Ruff inside regression suite: passed.
- Router Signal eval: route/tool/shadow/recommendation accuracy all `1.0000`, override count `0`.
- Web Search offline eval: success/safety pass rate `1.0000`.
- Code Review benchmark: single-review recall `0.9355`, precision `1.0000`.

Remaining manual validation:

- UE frontend real-editor smoke still needs a human run: Agent Chat, Code Review, Code Generate, Logs Analyze, Assets Inspect, and Editor Operation Proposal.
- Live LLM behavior depends on the local runtime profile and network/proxy state, so offline tests intentionally keep deterministic fallback coverage.

UE frontend impact: no mandatory change. Optional debug-only fields added during I2-F1 to I2-F5 remain backward compatible.

## 2026-05-17 No-UE Live Smoke Modes

`scripts/run_no_ue_live_smoke.py` can now run in four modes:

```powershell
# Deterministic fallback + mock Web Search, best for regression.
.\.venv\Scripts\python.exe scripts\run_no_ue_live_smoke.py

# Real LLM from .env + mock Web Search.
.\.venv\Scripts\python.exe scripts\run_no_ue_live_smoke.py --live-llm --output storage\artifacts\smoke\no-ue-live-smoke-live-llm.json

# Deterministic LLM fallback + real Web Search from .env WEB_SEARCH_*.
.\.venv\Scripts\python.exe scripts\run_no_ue_live_smoke.py --live-web-search --output storage\artifacts\smoke\no-ue-live-smoke-live-web.json

# Real LLM + real Web Search from .env.
.\.venv\Scripts\python.exe scripts\run_no_ue_live_smoke.py --live-all --output storage\artifacts\smoke\no-ue-live-smoke-live-all.json
```

How to read the live report:

- `settings.llm.api_key_configured` only shows whether an LLM key was detected; it never prints the key.
- `checks[].llm_status=accepted` means the live LLM generated code and the backend accepted it.
- `checks[].llm_status=rejected_fallback` means the live LLM was called, but its Enhanced Input draft was incomplete, so the backend used the deterministic `ACharacter` fallback.
- `agent_chat_web_search_tool.llm_answer_synthesis_status=completed` means Project QA final answer synthesis used live LLM.
- `agent_chat_web_search_tool.live_web_search_provider_used=true` means Web Search used a non-mock provider.

Boundary: `--live-all` can consume paid API quota and depends on proxy/network state. Keep the default mode for repeatable regression; use live modes for manual local verification.

## 2026-05-16 Executor-backed Handler migration

Code Review, Logs Analyze, and Code Generate now have concrete task handlers:

- `app/services/task_handlers/code_review.py`
- `app/services/task_handlers/logs_analyze.py`
- `app/services/task_handlers/code_generate.py`

What changed:

- `CodeReviewHandler` owns the decision between the normal code-review skill executor and the `ReviewFixValidateChain` multi-agent workflow.
- `LogsAnalyzeHandler` owns log-analysis skill executor construction.
- `CodeGenerateHandler` owns code-generation skill executor construction.
- `TaskService` no longer keeps thin wrapper methods for these three paths.

What did not change:

- Existing skill executors still do the actual work.
- Multi-agent Code Review still uses the existing `Review -> FixDraft -> Validate` chain.
- Request and response contracts are unchanged.
- UE frontend does not need to change.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_system_and_tasks.py tests\integration\test_multi_agent_chain.py tests\unit\test_task_route_dispatcher.py -q
```

## 2026-05-16 Workflow-backed Handler migration

Config Generate and Performance Analyze now have concrete task handlers:

- `app/services/task_handlers/config_generate.py`
- `app/services/task_handlers/perf_analyze.py`
- `app/services/task_handlers/view_helpers.py`

What changed:

- `ConfigGenerateHandler` owns config-generation workflow response shaping.
- `PerfAnalyzeHandler` owns performance-analysis workflow response shaping.
- Both handlers still call the existing workflow graph functions.
- Shared citation preview shaping for task handlers lives in `view_helpers.py`.
- `TaskService` no longer keeps `_execute_config_generate()` or `_execute_perf_analyze()`.

What did not change:

- Request and response contracts are unchanged.
- Workflow graph implementations are unchanged.
- UE frontend does not need to change.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_system_and_tasks.py tests\unit\test_task_route_dispatcher.py -q
```

## 2026-05-16 Assets Inspect / Placeholder Handler migration

Assets Inspect and the generic task placeholder now have concrete task handlers:

- `app/services/task_handlers/assets_inspect.py`
- `app/services/task_handlers/placeholder.py`

What changed:

- `AssetsInspectHandler` owns asset-inspection skill executor construction and attaches safe rename editor-operation proposals when available.
- `PlaceholderTaskHandler` owns stable diagnostics for recognized tasks without concrete executors.
- `TaskService` no longer keeps `_execute_assets_inspect()` or `_execute_task_placeholder()`.

What did not change:

- The asset inspection skill executor is unchanged.
- Rename proposals still require confirmed-write user approval and UE plugin execution.
- Request and response contracts are unchanged.
- UE frontend does not need to change.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_system_and_tasks.py::test_assets_inspect_returns_violations tests\integration\test_system_and_tasks.py::test_assets_inspect_can_summarize_types_and_relationships tests\integration\test_system_and_tasks.py::test_assets_inspect_live_llm_uses_compact_timeout_config tests\integration\test_system_and_tasks.py::test_assets_inspect_flags_default_world_asset_name tests\integration\test_editor_operations.py::test_assets_inspect_emits_rename_editor_operation_proposal tests\unit\test_task_route_dispatcher.py -q
```

## 2026-05-16 Editor Operation Handler migration

Editor-operation proposal response shaping now lives in `app/services/task_handlers/editor_operation.py`.

What changed:

- `EditorOperationProposalHandler` owns the user/debug response for editor-operation proposals.
- The confirmed-write safety boundary is unchanged.
- `TaskService` still owns detection and proposal normalization helpers for now.
- Unused legacy placeholder methods `_execute_project_qa()` and `_execute_direct_answer()` were removed.

What did not change:

- The backend still does not directly execute UE editor writes.
- UE plugin confirmation and execution are still required.
- Request and response contracts are unchanged.
- UE frontend does not need to change.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py tests\unit\test_task_route_dispatcher.py -q
```

## 2026-05-16 Project QA Handler migration

Project QA live execution now lives in `app/services/task_handlers/project_qa.py`.

What changed:

- `ProjectQAHandler` owns Project QA orchestration and response shaping.
- `TaskService` no longer keeps `_execute_project_qa_live()`.
- `TaskService` now keeps lifecycle, persistence, routing dispatch, context helpers, stream events, Proposal persistence, and shared file/inventory helper methods.

What did not change:

- RAG / lexical retrieval / local grep behavior is unchanged.
- Web Memory and Controlled Web Search behavior is unchanged.
- Project Inventory and guarded project-file read behavior is unchanged.
- LLM answer synthesis and fallback behavior are unchanged.
- Request and response contracts are unchanged.
- UE frontend does not need to change.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_system_and_tasks.py tests\unit\test_task_route_dispatcher.py tests\unit\test_project_qa_grounding.py tests\unit\test_kb_service_local_fallback.py tests\unit\test_web_memory_service.py tests\unit\test_retrieval_source_policy.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

TaskService boundary after this migration:

- Owns task/session persistence and event generation.
- Owns common context, routing dispatch, stream events, persistence, and shared safety helper methods.
- Delegates concrete task execution to `RouteExecutionDispatcher` and `app/services/task_handlers/*`.
- No longer owns feature-specific execution methods except shared helper methods used by handlers.

## 2026-05-16 Project QA Tool Planner extraction

Project QA tool planning now lives in `app/agent/tool_planner.py`.

What changed:

- `build_project_qa_deterministic_tool_plan()` owns deterministic inventory / knowledge decisions.
- `build_react_lite_tool_plan()` owns the bounded read-only ReAct Lite planner and planner fallback.
- `build_react_lite_trace()` owns the Debug View `react_loop` trace.
- `build_project_qa_result_contracts()` owns tool result contract validation for Project QA.
- `ProjectQAHandler` calls these module functions directly instead of calling private `TaskService` helpers.

What did not change:

- No UE frontend request or response field changed.
- `data.tool_plan`, `data.react_loop`, `debug_view.tool_plan`, and `debug_view.react_loop` remain compatible.
- Confirmed-write editor operations are still Proposal-based and are not executed by ReAct Lite.
- Project QA still uses the same KB, local grep, Project Inventory, project-file read, and LLM synthesis paths.

Validation:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit\test_project_qa_grounding.py tests\unit\test_tool_planner_inventory_fields.py tests\unit\test_project_file_tool.py tests\integration\test_system_and_tasks.py::test_agent_chat_project_qa_can_read_current_project_file -q
.\.venv\Scripts\python.exe -m pytest -q
```

## 2026-05-16 Task Event helper extraction

Task stream and persisted event envelope construction now lives in `app/services/task_events.py`.

What changed:

- `StreamEventEmitter` owns live SSE event sequencing.
- `build_persisted_event_payloads()` owns the stored task event list used by trace/event APIs.
- `build_run_cancelled_event_payload()` owns cancellation event envelope construction.
- `TaskService` still decides when events happen, but no longer hand-builds every event envelope inline.

What did not change:

- SSE event shape is unchanged.
- Stored task event shape is unchanged.
- `GET /api/v1/chat/runs/{run_id}/events/stream` behavior is unchanged.
- `GET /api/v1/tasks/{task_id}/trace` / run trace event behavior is unchanged.
- UE frontend does not need to change.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_task_events.py tests\integration\test_system_and_tasks.py::test_code_review_workflow_persists_artifacts_and_events tests\integration\test_system_and_tasks.py::test_logs_analyze_workflow_returns_structured_events tests\integration\test_system_and_tasks.py::test_cancel_waiting_confirmation_run_updates_status_and_stream -q
```

## 2026-05-16 Router SignalDetector S1A

The backend now has a lightweight signal-detector registry at `app/agent/signal_detectors.py`.

Current mode: compatibility observer.

What changed:

- Router decisions are still made by the existing deterministic/heuristic logic.
- Signal detectors run beside the existing router and record scored observations.
- Agent Chat / Project QA route diagnostics can include:
  - `route.signal_detector_trace`
  - `route.top_signal_detector`
  - `route.signal_detector_mode=compatibility_observer`

What did not change:

- No route decision changed in this stage.
- No frontend request field changed.
- No LLM route judge behavior changed.
- No ToolSpec execution behavior changed.

Why this exists:

- It creates a safe regression baseline before replacing router if/elif logic with a scoring router.
- It makes future detector additions easier to test without immediately affecting production routing.
- It helps Debug View explain why Project Inventory, Project QA, or direct chat looked plausible.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_router.py tests\unit\test_signal_detectors.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

UE frontend impact: no mandatory change. Debug View may optionally display `top_signal_detector.detector` and the detector trace list.

## 2026-05-16 Router SignalDetector S1B scoring shadow

Router SignalDetector now supports an optional scoring shadow mode.

Configuration:

```env
ROUTER_SIGNAL_MODE=scoring_shadow
ROUTER_SIGNAL_MIN_CONFIDENCE=0.72
ROUTER_SIGNAL_MIN_MARGIN=8.0
```

Default:

```env
ROUTER_SIGNAL_MODE=compatibility_observer
```

Behavior:

- `compatibility_observer` keeps the previous behavior: detectors only expose `signal_detector_trace` and `top_signal_detector`.
- `scoring_shadow` also exposes `signal_router_recommendation`.
- Shadow recommendation does not override the existing heuristic router.
- `signal_router_override_applied` is always `false` in this stage.
- `scoring_active` is available as a guarded mode. It only overrides when the recommendation is eligible, above confidence/margin thresholds, and different from the heuristic result. The default remains `compatibility_observer`.

Debug fields:

- `route.signal_detector_mode`
- `route.signal_detector_trace`
- `route.top_signal_detector`
- `route.signal_router_recommendation`
- `route.signal_router_override_applied`

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_router.py tests\unit\test_signal_detectors.py tests\unit\test_settings.py -q
```

UE frontend impact: no mandatory change. If Debug View wants richer routing diagnostics, display `signal_router_recommendation.status`, `route_hint`, `selected_tool_id`, and `score_margin`.

Active mode note:

```env
ROUTER_SIGNAL_MODE=scoring_active
```

建议只在本地调试或评测通过后启用。当前 route-diff eval 仍以 shadow 稳定性为主，不建议把 active mode 作为默认配置。

## 2026-05-16 Router Signal route-diff eval

The backend now includes a small offline route-diff eval for the router SignalDetector shadow layer.

Command:

```powershell
.\.venv\Scripts\python.exe scripts\run_router_signal_eval.py --output storage\artifacts\evals\router-signal-eval-latest.json --markdown-output storage\artifacts\evals\router-signal-eval-latest.md
```

Dataset:

```text
tests/eval/router_signal_dataset.jsonl
```

Metrics:

- `route_accuracy`：旧 heuristic router 是否仍命中标注 route。
- `tool_accuracy`：旧 heuristic router 是否仍命中标注 tool。
- `shadow_stability`：开启 `scoring_shadow` 后，最终 route/tool 是否与旧模式一致。
- `recommendation_accuracy`：shadow recommendation 是否符合标注的推荐 route/tool。
- `override_applied_count`：当前阶段必须为 0，表示 shadow 不接管最终路由。

Latest local result:

```text
case_count=5
route_accuracy=1.0000
tool_accuracy=1.0000
shadow_stability=1.0000
recommendation_accuracy=1.0000
override_applied_count=0
```

Boundary: this is a compact regression/evidence dataset, not a large enterprise routing benchmark. Add cases whenever a real route bug appears.

## 2026-05-16 Config Validate Handler migration

This is another internal backend refactor. `config_validate` now runs through `app/services/task_handlers/config_validate.py`.

What changed:

- `ConfigValidateHandler` owns deterministic schema validation, user-facing summary, debug retrieval trace, and report artifact metadata.
- The handler still calls the same `validate_design_config` tool.
- `TaskService` no longer keeps a dedicated `_execute_config_validate()` method.
- UE frontend request and response contracts are unchanged.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_system_and_tasks.py::test_config_validate_returns_report_and_artifact tests\unit\test_task_route_dispatcher.py -q
```

UE frontend impact: no mandatory change.

## 2026-05-17 Handler Dependencies v1

This is an internal architecture cleanup for the Improv3 Bridge/MCP absorption stage.

What changed:

- `app/services/task_handlers/base.py` now defines `TaskHandlerDependencies`.
- `TaskExecutionContext` can carry explicit dependencies such as `db`, `settings`, `kb_service`, `llm_service`, `inventory_service`, `base_debug_builder`, and `stream_event_emitter`.
- `TaskService._execute_route()` injects this dependency object when dispatching handlers.
- `ConfigValidateHandler` and `EditorOperationProposalHandler` now use the explicit dependency entry point for low-risk host cleanup.

Why it matters:

- New handlers can be tested without constructing a full `TaskService`.
- Future MCP/Bridge-style transports can reuse the same handler boundary.
- Existing UE frontend request/response contracts are unchanged.

Boundary:

- This does not introduce a new UE Editor operation.
- This does not make MCP the default execution path.
- Existing handlers may still read the legacy `host` object until they are migrated safely.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_task_route_dispatcher.py tests\unit\test_tool_registry.py tests\unit\test_tool_executor_runtime.py -q
.\.venv\Scripts\python.exe -m ruff check app\services\task_handlers\base.py app\services\task_handlers\__init__.py app\services\task_handlers\config_validate.py app\services\task_handlers\editor_operation.py app\services\task_service.py tests\unit\test_task_route_dispatcher.py
```

## 2026-05-17 Improv3 P2 Completion

This stage finishes the reasonable P2 items from Improv3 without changing UE frontend contracts.

### WorkflowCursor

`app/tools/workflow_cursor.py` adds a small `WorkflowCursor` object for multi-step workflows.

It records:

- `workflow_id`
- `step_index`
- `active_target`
- `active_asset`
- `active_graph`
- `last_tool_id`
- `last_result_ref`
- `confirmed_until_step`

It is carried by `ToolContext.workflow_cursor` and appears in `ToolContext.input_summary()`. It is only a planning/debug hint. It does not authorize writes and does not replace Proposal confirmation.

### Read-only ToolSpec Executor Migration

These read-only tools now expose local executors:

- `preflight_generated_code -> app.tools.code_preflight:preflight_generated_code_executor`
- `analyze_ue_log -> app.tools.log_analysis:analyze_ue_log_executor`
- `inspect_asset_metadata -> app.tools.asset_inspect:inspect_asset_metadata_executor`
- `review_ue_cpp_files -> app.tools.code_review:review_ue_cpp_files_executor`

The existing skill/task handler paths are unchanged. This migration gives future callers a consistent `ToolContext -> executor -> ToolResult` path and keeps preflight diagnostics in one place.

### Curation Review API

New endpoints:

```text
GET  /api/v1/curation/candidates
GET  /api/v1/curation/candidates/{candidate_id}
POST /api/v1/curation/candidates/{candidate_id}/approve
POST /api/v1/curation/candidates/{candidate_id}/reject
```

Safety boundary:

- `approve` exports a suggestion-only Markdown/JSON artifact under `storage/curation`.
- `reject` writes a local rejection marker under `storage/curation/rejected`.
- Neither endpoint writes to `knowledge/`, SQLite KB documents, or Qdrant.
- Neither endpoint triggers reindex automatically.

Example:

```powershell
Invoke-RestMethod -Method Get http://127.0.0.1:8000/api/v1/curation/candidates
```

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_tool_context.py tests\unit\test_tool_executor_runtime.py tests\unit\test_tool_registry.py tests\integration\test_system_and_tasks.py::test_curation_candidates_can_be_exported_for_manual_review -q
.\.venv\Scripts\python.exe -m ruff check app tests docs config
```

UE frontend impact: no mandatory change. If a future frontend wants a KB maintenance panel, it can read these curation endpoints, but this is optional.

## 2026-05-18 Material Texture Parameter Proposal

`Editor Operation Bridge` now includes `set_material_instance_texture_parameter`, a confirmed-write proposal for assigning one texture asset to one Material Instance parameter.

Supported request forms:

- Explicit proposal API: `operation_type=set_material_instance_texture_parameter`.
- Agent Chat: `Set MI_Player material BaseTexture to T_Player_D texture`.
- Inventory-assisted resolution: when `selected_assets` is empty, Project Inventory can provide both the `MI_...` Material Instance and the `T_...` Texture2D path.

Payload shape:

```json
{
  "material_instance_path": "/Game/Materials/MI_Player",
  "parameter_name": "BaseTexture",
  "texture_path": "/Game/Textures/T_Player_D",
  "save_policy": "mark_dirty_only"
}
```

Execution boundary:

- Backend only creates the proposal and validates normalized paths.
- UEAgentTool executes `UMaterialInstanceConstant.SetTextureParameterValueEditorOnly` after user confirmation.
- The package is marked dirty, not auto-saved.
- This is separate from `set_material_instance_parameter`, which remains scalar/vector only.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py -q
```

UE frontend impact: add `set_material_instance_texture_parameter` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-18 UMG TextBlock Text Proposal

`Editor Operation Bridge` now includes `set_umg_widget_text`, a confirmed-write proposal for updating the text of one existing `TextBlock` in a Widget Blueprint.

Supported request forms:

- Explicit proposal API: `operation_type=set_umg_widget_text`.
- Agent Chat: `Set WBP_MainHUD TitleText text to 'Mission Ready'`.
- Inventory-assisted resolution: when `selected_assets` is empty, Project Inventory can provide the `WBP_...` Widget Blueprint path.

Payload shape:

```json
{
  "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
  "widget_name": "TitleText",
  "text": "Mission Ready",
  "save_policy": "mark_dirty_only"
}
```

Execution boundary:

- Backend only creates and validates the proposal.
- UEAgentTool finds the widget by exact/case-insensitive name and requires it to be a `TextBlock`.
- UEAgentTool calls `UTextBlock.SetText` after user confirmation.
- The Widget Blueprint package is marked dirty, not auto-saved.
- v1 does not edit anchors, slots, bindings, animations, or arbitrary widget properties.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py -q
```

UE frontend impact: add `set_umg_widget_text` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-18 UMG CanvasPanelSlot Layout Proposal

`Editor Operation Bridge` now includes `set_umg_widget_layout`, a confirmed-write proposal for updating a limited `CanvasPanelSlot` layout on one existing UMG widget.

Supported request forms:

- Explicit proposal API: `operation_type=set_umg_widget_layout`.
- Agent Chat: `Set WBP_MainHUD TitleText position to 20 30 size to 300 48`.
- Inventory-assisted resolution: when `selected_assets` is empty, Project Inventory can provide the `WBP_...` Widget Blueprint path.

Payload shape:

```json
{
  "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
  "widget_name": "TitleText",
  "layout": {
    "position": {"x": 20, "y": 30},
    "size": {"x": 300, "y": 48},
    "alignment": {"x": 0.5, "y": 0},
    "anchors": {
      "minimum": {"x": 0, "y": 0},
      "maximum": {"x": 0, "y": 0}
    }
  },
  "slot_type": "CanvasPanelSlot",
  "save_policy": "mark_dirty_only"
}
```

Execution boundary:

- Backend only creates and validates the proposal.
- UEAgentTool finds the widget by exact/case-insensitive name and requires its slot to be `CanvasPanelSlot`.
- UEAgentTool may call `SetPosition`, `SetSize`, `SetAlignment`, and `SetAnchors` after user confirmation.
- The Widget Blueprint package is marked dirty, not auto-saved.
- v1 does not edit colors, fonts, bindings, animations, non-canvas slots, or arbitrary widget properties.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py -q
```

UE frontend impact: add `set_umg_widget_layout` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-23 UMG Slot Layout v2 Proposal

`Editor Operation Bridge` now includes `set_umg_slot_layout_v2`, a confirmed-write proposal for changing safe slot layout fields on one existing UMG widget that already lives in a `HorizontalBox`, `VerticalBox`, or `Overlay`.

Supported request forms:

- Explicit proposal API: `operation_type=set_umg_slot_layout_v2`.
- Agent Chat: `Set WBP_MainHUD IconImage HorizontalBoxSlot padding to 8 4 8 4 and horizontal alignment to center`.
- Supported `slot_type`: `HorizontalBoxSlot`, `VerticalBoxSlot`, `OverlaySlot`.

Payload:

```json
{
  "operation_type": "set_umg_slot_layout_v2",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "IconImage",
    "slot_type": "HorizontalBoxSlot",
    "layout": {
      "padding": {"left": 8, "top": 4, "right": 8, "bottom": 4},
      "horizontal_alignment": "center",
      "vertical_alignment": "fill",
      "size": {"rule": "fill", "value": 1}
    }
  }
}
```

Boundary:

- The target widget must already exist and must already have the requested slot type.
- `padding`, `horizontal_alignment`, and `vertical_alignment` work for all three supported slots.
- `size` only works for `HorizontalBoxSlot` and `VerticalBoxSlot`.
- It does not create parent containers, move widgets between panels, generate responsive layouts, or rewrite complex widget trees.

UE frontend impact: add `set_umg_slot_layout_v2` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-18 UMG Widget Visibility Proposal

`Editor Operation Bridge` now includes `set_umg_widget_visibility`, a confirmed-write proposal for changing one existing UMG widget's `Visibility` value.

Supported request forms:

- Explicit proposal API: `operation_type=set_umg_widget_visibility`.
- Agent Chat: `Hide WBP_MainHUD TitleText widget`.
- Agent Chat: `Set WBP_MainHUD StartButton visibility to hit test invisible`.
- Inventory-assisted resolution: when `selected_assets` is empty, Project Inventory can provide the `WBP_...` Widget Blueprint path.

Payload shape:

```json
{
  "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
  "widget_name": "TitleText",
  "visibility": "collapsed",
  "save_policy": "mark_dirty_only"
}
```

Supported `visibility` values:

- `visible`
- `collapsed`
- `hidden`
- `hit_test_invisible`
- `self_hit_test_invisible`

Execution boundary:

- Backend only creates and validates the proposal.
- UEAgentTool finds the widget by exact/case-insensitive name.
- UEAgentTool calls `UWidget.SetVisibility` after user confirmation.
- The Widget Blueprint package is marked dirty, not auto-saved.
- v1 does not edit render opacity, enabled state, bindings, animations, or batch widget state.

Validation:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest -q
```

UE frontend impact: add `set_umg_widget_visibility` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-22 UMG Widget Appearance Proposal

`Editor Operation Bridge` now includes `set_umg_widget_appearance`, a confirmed-write proposal for changing safe appearance fields on one existing UMG widget.

Supported request forms:

- Explicit proposal API: `operation_type=set_umg_widget_appearance`.
- Agent Chat: `Set WBP_MainHUD TitleText opacity to 0.5`.
- Agent Chat: `Set WBP_MainHUD TitleText font size to 28`.
- Hex color can be parsed from chat, for example `Set WBP_MainHUD TitleText color to #33CC66`.
- Inventory-assisted resolution: when `selected_assets` is empty, Project Inventory can provide the `WBP_...` Widget Blueprint path.

Payload shape:

```json
{
  "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
  "widget_name": "TitleText",
  "appearance": {
    "render_opacity": 0.65,
    "is_enabled": true,
    "color_and_opacity": {"r": 0.1, "g": 0.8, "b": 0.3, "a": 1.0},
    "font_size": 28
  }
}
```

Boundary:

- `render_opacity` and `is_enabled` apply to any UMG `UWidget`.
- `color_and_opacity` and `font_size` currently apply only to `UTextBlock`.
- The UE plugin marks the Widget Blueprint package dirty but does not auto-save.
- Animation editing, binding generation, dynamic style inheritance, and bulk widget tree rewrites remain out of scope.

UE frontend impact: add `set_umg_widget_appearance` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-22 UMG Widget Brush Proposal

`Editor Operation Bridge` now includes `set_umg_widget_brush`, a confirmed-write proposal for assigning one safe Brush resource to an existing UMG `Image` or `Border` widget.

Supported request forms:

- Explicit proposal API: `operation_type=set_umg_widget_brush`.
- Agent Chat: `Set WBP_MainHUD IconImage brush texture to T_Player_D`.
- Agent Chat: `Set WBP_MainHUD BackgroundBorder brush material to MI_HUD_Background`.
- Inventory-assisted resolution: Project Inventory can provide both the `WBP_...` Widget Blueprint path and the referenced `T_...` / `M_...` / `MI_...` resource path.

Payload:

```json
{
  "operation_type": "set_umg_widget_brush",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "IconImage",
    "brush": {
      "resource_type": "texture",
      "resource_path": "/Game/Textures/T_Player_D"
    }
  }
}
```

Boundary:

- Only `resource_type=texture` and `resource_type=material` are accepted.
- The UE executor only applies the Brush to `UImage` or `UBorder`.
- It does not create widgets, edit animations, generate bindings, edit atlases, or rewrite inherited style systems.
- The Widget Blueprint package is marked dirty but not auto-saved.

UE frontend impact: add `set_umg_widget_brush` to any operation whitelist/card label map if one exists. The existing proposal confirmation and result callback flow can be reused.

## 2026-05-19 Editor Operation Preview and History v1

`Editor Operation Bridge` now returns a richer, backward-compatible preview contract for every editor operation proposal.

New `dry_run_preview` fields:

- `affected_targets`: normalized list of assets, widgets, actors, materials, or Blueprint targets that may change after confirmation.
- `preflight_checks`: backend validation and safety checks, including pending user confirmation and UE plugin execution.
- `expected_result_contract`: fields the UE plugin should report back through `POST /api/v1/editor-operations/results`.
- `preview_summary`: compact risk and target summary for UI cards and Debug View.

Result recording now also stores `operation_result.result_summary`:

- `execution_state`
- `success`
- `target_count`
- `dirty_packages`
- `applied_field_count`
- `failed_field_count`
- `error_codes`
- `needs_user_attention`

New read-only endpoint:

```http
GET /api/v1/editor-operations/history?limit=50
GET /api/v1/editor-operations/history?operation_type=set_umg_widget_visibility&limit=20
```

This endpoint returns recent editor operation proposals with preview and result summaries. It is intended for Debug View, future operation history panels, and follow-up context.

Frontend impact: no mandatory change. Existing Proposal cards can ignore the new fields. Optional UI improvements can show `affected_targets`, `preflight_checks`, and `result_summary` when available.

User View detail blocks:

- Blueprint Graph operations can include `editor_operation_graph_details`.
- UMG operations can include `editor_operation_umg_details`.
- Other ordinary editor operations can include
  `editor_operation_target_details`, which summarizes operation-specific result
  fields, dirty packages, applied fields, failed fields, and UE errors.

These blocks are additive. A frontend that already renders generic
`user_view.blocks[]` can show them without calling a new endpoint.

## 2026-05-19 UEAgentTool Result Contract Normalization

UEAgentTool now normalizes editor operation execution results at the Tool Registry exit point. This keeps individual executors focused on real UE Editor API work while guaranteeing a stable backend-facing result shape.

Normalized result fields:

- `success`
- `execution_state`
- `operation_type`
- `tool_id`
- `save_policy`
- `applied_fields`
- `failed_fields`
- `dirty_packages`
- `undo_hint` when available

Behavior:

- Existing executor-specific fields are preserved.
- Existing `save_policy`, `dirty_packages`, `applied_fields`, and `failed_fields` are not overwritten.
- If a successful editor write does not provide `save_policy`, UEAgentTool fills `mark_dirty_only`.
- If a blocked/failed operation does not provide `save_policy`, UEAgentTool fills `not_applied`.
- `dirty_packages` falls back to common fields such as `package_name`, `level_name`, `asset_path`, `blueprint_path`, `widget_blueprint_path`, or `material_instance_path` when the executor did not set it explicitly.

Frontend impact: no mandatory change. The existing result callback remains the same, but Debug View and future operation history can rely on these common fields being present.

## 2026-05-19 Blueprint Graph Snapshot v2

The optional read-only `get_blueprint_graph` TCP/MCP tool now returns a richer Blueprint graph snapshot for future Blueprint Graph Automation work.

New/expanded `structuredContent` fields:

- `graph_schema_version`: currently `blueprint_graph_snapshot_v2`.
- `graph_metrics`: graph count, node count, pin count, link count, and snapshot limits.
- `graphs[].graph_id`: stable graph identifier when available.
- `graphs[].nodes[].node_id`: node GUID.
- `graphs[].nodes[].pin_count`, `input_pin_count`, `output_pin_count`, `link_count`.
- `graphs[].nodes[].pins[]`: pin id, name, direction, type, linked target count, and limited linked pin summaries.

Limits:

- Up to 64 graphs.
- Up to 64 nodes per graph.
- Up to 32 pins per node.
- Up to 8 linked targets per pin.

Boundary:

- This is still read-only.
- It does not create nodes, connect pins, compile Blueprints, or modify assets.
- It is intended to support safer future graph editing because later write proposals can refer to explicit graph/node/pin identifiers instead of vague names.

Frontend impact: no mandatory change. If Debug View displays raw MCP structured content, the new fields will appear automatically.

## 2026-05-24 Level Actor Arrangement Pattern Proposal

`Editor Operation Bridge` now includes `arrange_actors_pattern`, a confirmed-write
proposal for arranging existing Level Actors into a simple line, grid, or circle.

Use it when Agent Chat needs to prepare a safe layout operation such as:

- `Arrange BP_EnemySpawner_1 and BP_PatrolPoint_1 in a line spacing 250`
- `Put selected patrol points into a grid`
- `Arrange these actors in a circle with radius 600`

Explicit proposal API:

```json
{
  "operation_type": "arrange_actors_pattern",
  "payload": {
    "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1"],
    "pattern": {
      "type": "line",
      "spacing": 250,
      "axis": "x"
    }
  }
}
```

Supported pattern fields:

- `type`: `line`, `grid`, or `circle`.
- `spacing`: distance between line/grid items. Default: `200`.
- `axis`: `x` or `y` for line layout. Default: `x`.
- `columns`: optional grid column count.
- `radius`: optional circle radius.
- `origin`: optional `{ "x": 0, "y": 0, "z": 0 }`; UEAgentTool uses the first actor location when omitted.

Safety boundary:

- Requires user confirmation like all editor writes.
- Only arranges existing actors found in the current level.
- Accepts 2 to 12 actor references per proposal.
- Only changes actor location through UEAgentTool.
- Does not create, delete, duplicate, rotate, scale, attach, save, or stream actors.
- Marks touched levels dirty but does not auto-save.

Expected UE result callback fields:

- `arranged_actors`
- `pattern_type`
- `item_count`
- `origin`
- `save_policy`
- `dirty`
- `dirty_packages`

Frontend impact: add `arrange_actors_pattern` to any local operation whitelist or
title map if one exists. The existing Proposal confirmation and result callback
flow is reused.

## 2026-06-08 Level Actor Selection Proposal

`Editor Operation Bridge` now includes `select_level_actors`, a confirmed
Proposal for selecting a bounded set of Actors in the current editor level.

Use it when Agent Chat needs to prepare a target set before later Actor edits:

- `Select actors tagged Enemy`
- `Highlight BP_EnemySpawner_1`
- `Focus all actors whose class contains PointLight`

Explicit proposal API:

```json
{
  "operation_type": "select_level_actors",
  "payload": {
    "selection": {
      "actor_references": ["BP_EnemySpawner_1"],
      "tag": "Enemy",
      "max_count": 10
    }
  }
}
```

Supported selector fields:

- `actor_references`: exact actor label/name/path list.
- `query`: fuzzy match against actor label/name/path.
- `class_contains`: substring match against actor class name/path.
- `tag`: exact Actor tag match.
- `folder_path`: editor outliner folder substring.
- `max_count`: 1-50, default 20.

Safety boundary:

- Requires user confirmation because it changes editor selection state.
- Does not move, rename, tag, place, delete, save, or dirty Actors.
- UEAgentTool executes the selection through `GEditor.SelectActor`.
- Follow-up Actor edits still require their own confirmed Proposals.

Expected UE result callback fields:

- `selected_actor_count`
- `selected_actors`
- `selection_changed`
- `save_policy=selection_only_no_save`

## 2026-06-08 Level Actor Folder Proposal

`Editor Operation Bridge` now also includes `set_actor_folder`, a confirmed
Proposal for moving a bounded set of current-level Actors into one World
Outliner folder.

Use it after live Actor sensing or Actor selection when the user wants to
organize the level hierarchy:

- `Move actors tagged Enemy into folder Gameplay/EncounterA`
- `Put BP_EnemySpawner_1 and BP_PatrolPoint_1 under folder Gameplay/Spawners`
- `Organize selected actors into folder Lighting/KeyLights`

Explicit proposal API:

```json
{
  "operation_type": "set_actor_folder",
  "payload": {
    "selection": {
      "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1"],
      "max_count": 12
    },
    "target_folder_path": "Gameplay/EncounterA"
  }
}
```

Selector fields are the same as `select_level_actors`:

- `actor_references`: exact actor label/name/path list.
- `query`: fuzzy match against actor label/name/path.
- `class_contains`: substring match against actor class name/path.
- `tag`: exact Actor tag match.
- `folder_path`: source outliner folder substring.
- `max_count`: 1-50, default 20.

Safety boundary:

- Requires user confirmation before execution.
- Only calls `AActor.SetFolderPath` on matched current-level Actors.
- Does not move transforms, rename assets, delete Actors, or auto-save levels.
- The level is marked dirty so the user can review and save manually.

Expected UE result callback fields:

- `updated_actor_count`
- `updated_actors`
- `target_folder_path`
- `level_dirty`
- `dirty_packages`
- `save_policy=mark_dirty_only`

## 2026-06-09 Level Actor Tags Proposal

`Editor Operation Bridge` now includes `set_actor_tags`, a confirmed Proposal
for replacing, appending, or removing tags on a bounded set of current-level
Actors.

Use it when Agent Chat needs to prepare gameplay/query tags after live Actor
sensing or Actor selection:

- `Add tag Combat to actors tagged Enemy`
- `Append tags Interactable, QuestTarget to selected actors`
- `Remove tag Debug from actors in folder Gameplay/Test`

Explicit proposal API:

```json
{
  "operation_type": "set_actor_tags",
  "payload": {
    "selection": {
      "tag": "Enemy",
      "max_count": 8
    },
    "tags": ["Combat", "Spawner"],
    "tag_mode": "append"
  }
}
```

Supported `tag_mode` values:

- `append`: add tags without removing existing tags.
- `replace`: clear existing tags and set the provided list.
- `remove`: remove the provided tags if present.

Safety boundary:

- Requires user confirmation before execution.
- Reuses the same bounded selector as `select_level_actors`.
- Only changes `AActor.Tags` on matched current-level Actors.
- Does not move transforms, rename assets, delete Actors, or auto-save levels.
- The level is marked dirty so the user can review and save manually.

Expected UE result callback fields:

- `updated_actor_count`
- `updated_actors`
- `tags`
- `tag_mode`
- `level_dirty`
- `dirty_packages`
- `save_policy=mark_dirty_only`

## 2026-06-09 Level Actor Visibility Proposal

`Editor Operation Bridge` now includes `set_actor_visibility`, a confirmed
Proposal for setting `Hidden In Game` on a bounded set of current-level Actors.

Use it when Agent Chat needs to hide or show gameplay Actor groups without
moving, deleting, or renaming them:

- `Hide actors tagged Enemy in game`
- `Show actors tagged Debug in game`
- `Hide selected actors in game`

Explicit proposal API:

```json
{
  "operation_type": "set_actor_visibility",
  "payload": {
    "selection": {
      "tag": "Enemy",
      "max_count": 8
    },
    "hidden_in_game": true
  }
}
```

Safety boundary:

- Requires user confirmation before execution.
- Reuses the same bounded selector as `select_level_actors`.
- Only calls `AActor.SetActorHiddenInGame`.
- Does not change editor temporary visibility, transforms, folders, tags,
  names, assets, or auto-save levels.
- The level is marked dirty so the user can review and save manually.

Expected UE result callback fields:

- `updated_actor_count`
- `updated_actors`
- `hidden_in_game`
- `level_dirty`
- `dirty_packages`
- `save_policy=mark_dirty_only`

## 2026-05-24 Tool Registry Manifest for MCP-compatible Transport

The backend now exposes a descriptive Tool Registry manifest:

```http
GET /api/v1/mcp/tool-registry/manifest
```

This endpoint converts `app.tools.registry.ToolSpec` entries into an
MCP `tools/list`-compatible shape:

- `tools[].name`
- `tools[].description`
- `tools[].inputSchema`
- `tools[].annotations`

Useful filters:

```http
GET /api/v1/mcp/tool-registry/manifest?side_effect_level=confirmed_write
GET /api/v1/mcp/tool-registry/manifest?category=write
GET /api/v1/mcp/tool-registry/manifest?transport=mcp_tcp
GET /api/v1/mcp/tool-registry/manifest?include_disabled=false
```

Compact demo profiles:

```http
GET /api/v1/mcp/tool-registry/manifest?profile=readonly_sensing
GET /api/v1/mcp/tool-registry/manifest?profile=blueprint_demo
GET /api/v1/mcp/tool-registry/manifest?profile=umg_demo
GET /api/v1/mcp/tool-registry/manifest?profile=material_demo
GET /api/v1/mcp/tool-registry/manifest?profile=level_demo
GET /api/v1/mcp/tool-registry/manifest?profile=asset_maintenance
```

Profiles are inspired by UMG-MCP's prompt/tool enablement idea: expose only the
small tool set relevant to the current demo or external client context. They do
not change permissions, side-effect levels, confirmation rules, or executor
paths. You can still combine a profile with filters, for example
`profile=blueprint_demo&side_effect_level=read_only`.

Each selected profile also returns:

- `profiles.selected.suggested_prompts`: short natural-language demo prompts.
- `profiles.selected.sample_tool_calls`: compact Tool Registry call examples
  for external clients or future UI affordances.

Safety boundary:

- The manifest is descriptive metadata, not a new write execution path.
- Read-only MCP tools can still be called only through the explicit MCP debug API when the adapter is enabled.
- `confirmed_write` tools expose `execution_boundary.mode=confirmed_write_proposal`.
- `confirmed_write` tools always use `POST /api/v1/editor-operations/proposals`; MCP cannot directly mutate Unreal assets or levels.
- The UE frontend still remains HTTP + Proposal confirmation.

Export command:

```powershell
.\.venv\Scripts\python.exe scripts\export_tool_manifest.py --output storage\artifacts\tool-registry-manifest.json
```

Frontend impact: no mandatory change. A future debug/tools panel can use this
manifest to group tools, show side-effect levels, and explain why editor writes
require Proposal confirmation.

## 2026-05-24 Multi-step Editor Workflow Planner v1

The backend now exposes a plan-only endpoint for multi-step editor workflows:

```http
GET  /api/v1/editor-operations/workflows/templates
POST /api/v1/editor-operations/workflows/plan
POST /api/v1/editor-operations/workflows/state
POST /api/v1/editor-operations/workflows/steps/proposal
```

This endpoint does not create proposals and does not execute UE writes. It
returns a workflow plan with `steps[]`; each step includes a
`create_request_hint` that can be submitted later to
`POST /api/v1/editor-operations/proposals`.

Example request:

```json
{
  "goal": "Create HUD status text and place it",
  "workflow_type": "umg_text_widget",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "StatusText",
    "text": "Ready",
    "layout": {"position": {"x": 32, "y": 48}}
  }
}
```

Supported workflow types in v1:

- `blueprint_print_then_compile`: add a BeginPlay Print String or Delay -> PrintString template, then compile the Blueprint as a separate confirmed step.
- `blueprint_connect_then_compile`: connect two explicit Blueprint pins, then compile the Blueprint as a separate confirmed step.
- `blueprint_enhanced_input_print_then_compile`: add an Enhanced Input Triggered -> Print String template, then compile the Blueprint as a separate confirmed step.
- `umg_text_widget`: add a TextBlock, set text, and optionally apply CanvasPanelSlot layout or visibility.
- `umg_hud_group`: plan a small HUD group under an existing panel using `add_umg_widget` steps for HorizontalBox, Image, TextBlock, and Button.
- `arrange_and_tag_actors`: arrange a bounded Actor set, then optionally apply the same metadata to each Actor.

Use `GET /api/v1/editor-operations/workflows/templates` to list the same
templates with required fields, optional fields, emitted operation types, and
safety boundaries.

Returned plan fields:

- `workflow_plan.schema_version = editor_workflow_plan_v1`
- `workflow_plan.status = planned | partial | needs_more_input | unsupported`
- `workflow_plan.program_counter`
- `workflow_plan.steps[].operation_type`
- `workflow_plan.steps[].proposal_ready`
- `workflow_plan.steps[].missing_inputs`
- `workflow_plan.dependency_graph.ready_step_ids`
- `workflow_plan.dependency_graph.waiting_step_ids`
- `workflow_plan.dependency_graph.edges[]`
- `workflow_plan.steps[].create_request_hint`

Safety boundary:

- `auto_execute` is always `false`.
- Every write step still requires a normal Proposal and user confirmation.
- The planner does not hide follow-up writes in the background.
- It is deterministic and template-based in v1; it is not a full autonomous task scheduler.

2026-06-02 update: Blueprint workflow planning can now reuse Active Context
Blueprint focus. If the request omits `blueprint_path`, the planner checks
`active_context.blueprint.current_blueprint_path`, `context.editor_state`, and
the latest successful Blueprint operation target. If the request omits
`graph_name`, the planner can use `active_context.blueprint.current_graph_name`.
For `ConstructionScript` or other non-EventGraph targets, the planner leaves
`entry_event` empty instead of forcing `BeginPlay`; for explicit EventGraph
requests it keeps the existing `BeginPlay` default.

2026-06-04 update: Workflow Planner v2 adds
`blueprint_connect_then_compile`. It emits:

1. `connect_blueprint_nodes`
2. `compile_blueprint`

The connect step requires `blueprint_path`, `graph_name`, `source_node_id`,
`source_pin_name`, `target_node_id`, and `target_pin_name`. The planner can fill
some of these from `active_context.blueprint.current_node_summary` and
`active_context.blueprint.current_graph_summary` when UEAgentTool has submitted
Project Inventory graph summaries and editor focus fields. It does not infer
arbitrary Blueprint wiring: if the target node or pins cannot be matched from
explicit payload fields or compact graph focus, the step returns
`proposal_ready=false` with `missing_inputs`.

2026-06-04 update: Workflow Planner v2 also adds
`blueprint_enhanced_input_print_then_compile`. It emits:

1. `add_blueprint_node_template` with `template_id=enhanced_input_print_string`
2. `compile_blueprint`

This workflow requires `blueprint_path` and `input_action_path`. It only works
with an existing `UInputAction` asset and does not edit Input Mapping Contexts,
Project Settings, or arbitrary Blueprint wiring.

2026-06-04 update: every workflow plan now includes
`dependency_graph.schema_version = editor_workflow_dependency_graph_v1`. This
machine-readable summary lists dependency-free ready steps, dependency-blocked
steps, missing-input steps, and `from_step_id -> to_step_id` edges. Existing
`steps[]` remain unchanged; the dependency graph is only a clearer projection for
Debug View, future UI, and workflow validation.

2026-06-04 update: `/api/v1/editor-operations/workflows/state` can project
runtime progress from a workflow plan plus stored editor-operation Proposals.
The endpoint reads Proposal records that contain
`context.workflow_materialization.workflow_plan_id` and reports:

- `completed_step_ids`
- `next_ready_step_ids`
- `pending_step_ids`
- `blocked_step_ids`
- `step_states[].status`
- `next_step_proposal_requests[]`
- `next_action`

This endpoint is read-only. It does not create, confirm, execute, or batch
submit workflow steps. Existing UEAgentTool UI does not need to call it, but a
future workflow panel can use it to unlock the next step after the previous
Proposal result has been recorded. `next_step_proposal_requests[]` is only a
ready-to-send request hint for
`POST /api/v1/editor-operations/workflows/steps/proposal`; the caller still has
to submit it explicitly, and the resulting Proposal still needs user
confirmation.

Frontend impact: no mandatory change. A future Workflow UI can show the plan,
let the user submit one step at a time, and stop/skip steps safely.

## 2026-05-24 Tool Registry Proposal Bridge

The backend now exposes a safe bridge from Tool Registry ids to pending editor
operation Proposals:

```http
POST /api/v1/mcp/tool-registry/proposals/prepare
POST /api/v1/mcp/tool-registry/proposals
```

`/prepare` is dry-run style metadata. It validates that the requested `tool_id`
is a registered `confirmed_write` editor tool and returns a
`proposal_request_hint` for `POST /api/v1/editor-operations/proposals`.

`/proposals` uses the same mapping and then creates a normal pending Proposal
row. It still does not execute UE Editor APIs. The UE plugin must display the
Proposal and execute only after the user confirms.

Example request:

```json
{
  "tool_id": "editor_arrange_actors_pattern",
  "arguments": {
    "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1"],
    "pattern": {"type": "line", "spacing": 250}
  },
  "reason": "Arrange two actors for a quick layout pass.",
  "requested_by": "tool_registry_proposal_bridge"
}
```

Safety boundary:

- Only `confirmed_write` ToolSpec entries mapped to `OPERATION_SPECS` are accepted.
- Read-only tools are blocked by this bridge because they should use read-only routes.
- Unknown or disabled tools are blocked.
- `auto_execute` is always `false`.
- The bridge creates or describes a pending Proposal only; the UE frontend still owns confirmation and editor execution.

Frontend impact: no mandatory change. Existing Proposal cards keep working. A
future MCP-compatible tool panel can call `/prepare` to preview the operation or
`/proposals` to create the same Proposal card the current UI already understands.

Deterministic smoke coverage:

```powershell
.\.venv\Scripts\python.exe scripts\run_tool_registry_proposal_bridge_smoke.py --output -
```

The smoke simulates MCP/Tool Registry clients creating pending Proposals for
Blueprint graph editing, UMG widget creation, Material Instance parameter
tuning, and Level Actor placement. The Blueprint case uses
`editor_blueprint_add_step`, a high-level MCP-style alias that normalizes
`step_name=PrintString` into the existing `add_blueprint_node_template`
operation. It also verifies that read-only tools cannot enter the
confirmed-write Proposal bridge.

## 2026-05-24 Agent Chat Workflow Plan Integration

Agent Chat can now return the same plan-only editor workflow structure when the
user clearly asks for a multi-step editor plan, for example:

- "Plan a workflow: add a Print String node to `/Game/Blueprints/BP_PlayerCharacter` then compile it."
- "Plan a workflow: add a Print String after 2 seconds to `/Game/Blueprints/BP_PlayerCharacter` then compile it."
- "Plan a workflow: connect the current node to Print String then compile."
- "Plan a workflow: add Enhanced Input IA_Jump to BP_Player then compile."
- "Create HUD status text, set the copy, then apply layout."
- "Arrange these actors, then apply the same tag."

Blueprint graph workflow planning still uses fixed templates only. If the goal
mentions delay/wait/after, the first step uses `template_id=delay_print_string`
and carries `delay_seconds`; otherwise it uses `template_id=print_string`.

The handler uses the existing `EditorWorkflowPlannerService`; it does not create
Proposals automatically and does not execute UE writes. The response appears in:

- `user_view.blocks[]` with `block_type=editor_workflow_plan`.
- `user_view.blocks[]` with `block_type=workflow_ready_actions` when ready
  steps exist.
- `user_view.quick_actions[]` with `action_type=create_workflow_step_proposal`
  for dependency-free ready steps, capped to the first 5 actions.
- `data.editor_workflow_plan`.
- `data.editor_workflow_quick_actions`.
- `debug_view.workflow_trace`.

Detection boundary:

- Explicit `payload.workflow_type`, `payload.editor_workflow_type`, or `payload.workflow_plan_type` always opts into workflow planning.
- Natural language detection requires a multi-step signal such as `workflow`, `plan`, `then`, `after that`, `先`, `然后`, or `步骤`.
- A normal single-step request such as "add a Print String node" still creates one Proposal and is not converted into a workflow plan.
- Unsupported workflow goals fall back to the existing task handlers.

Frontend impact: no mandatory change. The normal chat panel can display the
assistant text and optional `user_view.blocks`. A future Workflow UI can read
`user_view.quick_actions[]` or
`data.editor_workflow_plan.steps[].create_request_hint` and let users submit one
step at a time. A quick action creates one pending Proposal only; it does not
confirm, execute, or batch-submit a workflow. Steps with `depends_on_step_ids`
remain in `data.editor_workflow_plan.steps[]` but are not exposed as quick
actions until the client has enough execution state to safely continue.

## 2026-05-24 Workflow Step Materialization

Workflow plans can now be materialized one step at a time into normal pending
editor-operation Proposals:

```http
POST /api/v1/editor-operations/workflows/steps/proposal
```

This endpoint accepts either a full workflow `step` object returned by
`/workflows/plan` or a direct `create_request` object shaped like
`steps[].create_request_hint.json`.

Example request:

```json
{
  "workflow_plan_id": "workflow_plan_xxx",
  "step": {
    "step_id": "step_0_add_blueprint_node_template",
    "proposal_ready": true,
    "missing_inputs": [],
    "create_request_hint": {
      "method": "POST",
      "path": "/api/v1/editor-operations/proposals",
      "json": {
        "operation_type": "add_blueprint_node_template",
        "payload": {
          "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
          "template_id": "print_string",
          "entry_event": "BeginPlay",
          "message": "Ready"
        },
        "reason": "Create the Blueprint graph node first.",
        "requested_by": "workflow_planner"
      }
    }
  },
  "requested_by": "workflow_ui"
}
```

Response shape:

- `workflow_step.schema_version = editor_workflow_step_materialization_v1`
- `workflow_step.workflow_plan_id`
- `workflow_step.workflow_step_id`
- `workflow_step.operation_type`
- `workflow_step.proposal_request`
- `proposal.item`
- `proposal.operation`

Safety boundary:

- Only one workflow step can be materialized per request.
- `proposal_ready=false` or non-empty `missing_inputs` is rejected.
- Steps with `depends_on_step_ids` are rejected until the caller supplies the
  prerequisite ids through `context.completed_step_ids` or
  `context.workflow_state.completed_step_ids`.
- The endpoint creates a pending Proposal only.
- It does not confirm the Proposal.
- It does not execute UEAgentTool or Unreal Editor APIs.
- The resulting Proposal uses the same confirmation card and result callback as every other editor operation.

Frontend impact: no mandatory change. If a Workflow UI is added, it can show a
"Create Proposal" button per ready, dependency-free step and call this endpoint.
Existing Proposal cards remain the only execution UI. Dependent steps should stay
visible in the plan until the frontend has confirmed that the prerequisite step
has completed.

## 2026-05-24 Follow-up Candidate Materialization

Blueprint graph diagnostics and other editor-operation repair advice can produce
follow-up candidates. A ready candidate can now be converted into a normal
pending Proposal:

```http
POST /api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal
```

Typical flow:

```text
1. UEAgentTool reports an editor-operation result.
2. Backend records operation_diagnostics and repair_advice.
3. Frontend or caller reads:
   GET /api/v1/editor-operations/proposals/{proposal_id}/follow-ups
4. User chooses one ready candidate.
5. Caller submits that one candidate to:
   POST /api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal
6. Backend creates a new pending Proposal.
7. UE frontend shows the normal confirmation card.
```

Example request:

```json
{
  "candidate": {
    "candidate_id": "connect_expected_exec_pins",
    "proposal_ready": true,
    "missing_inputs": [],
    "create_request_hint": {
      "json": {
        "operation_type": "connect_blueprint_nodes",
        "payload": {
          "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
          "graph_name": "EventGraph",
          "source_node_id": "EventBeginPlay",
          "source_pin_name": "then",
          "target_node_id": "K2Node_CallFunction_0",
          "target_pin_name": "execute",
          "compile_after_edit": true
        },
        "reason": "Follow up: connect expected execution pins.",
        "requested_by": "editor_operation_follow_up"
      }
    }
  },
  "requested_by": "workflow_ui"
}
```

Safety boundary:

- Only one follow-up candidate can be materialized per request.
- `proposal_ready=false` or non-empty `missing_inputs` is rejected.
- The endpoint creates a pending Proposal only.
- It does not confirm, execute, reconnect pins, or compile automatically.
- The returned Proposal uses the same confirmation and result callback flow as all editor writes.

Frontend impact: no mandatory change. Existing follow-up debug cards can remain
read-only. If the UI adds a "Create follow-up Proposal" button, call this
endpoint with exactly one candidate and render the returned Proposal with the
existing Proposal card.

## 2026-05-25 Editor Operation Result Follow-up Quick Actions

`POST /api/v1/editor-operations/results` now returns a user-facing result view
when Blueprint Graph diagnostics or repair advice are available.

Important response fields:

- `user_view.blocks[]` with `block_type=editor_operation_result_summary`.
- `user_view.blocks[]` with `block_type=editor_operation_follow_ups`.
- `user_view.quick_actions[]` with
  `action_type=create_editor_operation_follow_up_proposal` for ready candidates.
- `follow_up` with the same candidate payload as
  `GET /api/v1/editor-operations/proposals/{proposal_id}/follow-ups`.
- `follow_up_quick_actions[]` for clients that prefer data-level access.

Safety boundary:

- Quick actions only create one pending follow-up Proposal.
- They do not confirm or execute the follow-up.
- UEAgentTool remains the execution layer after normal user confirmation.
- If a candidate has missing inputs, no quick action is emitted.

Frontend impact: updated UEAgentTool builds can show the quick-action button
immediately after reporting an editor-operation result. Older builds can ignore
the new fields and continue to use the follow-up endpoints manually.

## 2026-05-25 Blueprint Graph Result Observability v2

UEAgentTool now reports richer structured data for Blueprint Graph operations.
This improves diagnostics and follow-up proposal generation without expanding
the write surface.

For `add_blueprint_node_template`, UEAgentTool may now include:

- `created_node_id` and `created_node_name`: the primary created node.
- `entry_node_id` and `entry_node_name`: the event node used for template links, when applicable.
- `created_nodes[]`: objects with `node_id`, `node_name`, `node_class`, `title`, `x`, `y`, and `role`.
- `linked_nodes[]`: objects with the same node shape.
- `linked_pins[]`: objects with `source` and `target` pin objects. Each pin includes `node_id`, `node_name`, `pin_id`, `pin_name`, `direction`, and `pin_type`.
- `linked_pin_summaries[]`: readable strings for display-only UI.

For `connect_blueprint_nodes`, UEAgentTool may now include:

- `source_node_id`, `source_node_name`, `source_pin_id`, `source_pin_name`.
- `target_node_id`, `target_node_name`, `target_pin_id`, `target_pin_name`.
- `linked_pins[]` and `linked_pin_summaries[]`.

Backend behavior:

- Existing string-only result arrays remain accepted for backward compatibility.
- Follow-up candidates prefer stable `entry_node_id` and `created_node_id` when present.
- If stable IDs are missing, the backend still falls back to node names such as `EventBeginPlay` or `K2Node_CallFunction_0`.
- Result-time quick actions still only create pending Proposals; they never execute graph edits automatically.
- Result-time `user_view.blocks[]` can include `block_type=editor_operation_graph_details` with `schema_version=blueprint_graph_result_details_v1`. This block summarizes stable node/pin ids into display-ready `items[]`, while keeping the structured `created_nodes[]`, `linked_pins[]`, and `linked_pin_summaries[]` under `data` for copy/debug use.

## 2026-05-24 Workflow Materialization Smoke

The backend now includes a deterministic smoke test for the two materialization
paths added in Improv4 finalization:

```powershell
.\.venv\Scripts\python.exe scripts\run_editor_workflow_materialization_smoke.py
```

It writes a JSON report to:

```text
storage/artifacts/smoke/editor-workflow-materialization-smoke-latest.json
```

Covered cases:

- `workflow_step_to_proposal`: workflow plan step becomes a pending Proposal.
- `delay_workflow_step_to_proposal`: delay-print workflow step keeps `template_id=delay_print_string` and `delay_seconds` when it becomes a pending Proposal.
- `blueprint_connect_workflow_step_to_proposal`: connect-pin workflow step becomes a pending `connect_blueprint_nodes` Proposal.
- `enhanced_input_workflow_step_to_proposal`: Enhanced Input workflow step becomes a pending `add_blueprint_node_template` Proposal with `template_id=enhanced_input_print_string`.
- `workflow_step_rejects_missing_inputs`: non-ready workflow step is rejected.
- `umg_hud_group_step_to_proposal`: first HUD group workflow step becomes a pending `add_umg_widget` Proposal.
- `follow_up_candidate_to_proposal`: Blueprint repair follow-up candidate becomes a pending Proposal.

Expected result:

```text
overall_ok = true
case_count = 7
passed = 7
failed = 0
```

This smoke test does not launch UE, execute editor writes, compile Blueprints,
or call an LLM. It only verifies backend contracts and safety boundaries.

## 2026-05-26 Project Inventory Chat Smoke

The backend also includes a deterministic no-UE/no-LLM smoke test for the
Project Inventory -> Agent Chat grounding path:

```powershell
.\.venv\Scripts\python.exe scripts\run_project_inventory_chat_smoke.py
```

It seeds an isolated Project Inventory snapshot with one Blueprint graph summary,
calls:

```http
GET  /api/v1/project-inventory/blueprint-graphs
POST /api/v1/chat/runs
```

and verifies that a natural-language graph question is routed to
`query_project_inventory` and answered with `EventGraph`, `Event BeginPlay`,
and `Print String` from the submitted snapshot.

Report output defaults to:

```text
storage/artifacts/smoke/project-inventory-chat-smoke-latest.json
```

Expected result:

```text
overall_ok = true
case_count = 1
passed = 1
failed = 0
```

This smoke test does not launch Unreal Editor, execute editor writes, compile
Blueprints, or call an LLM. It only proves that current-project graph facts can
flow from Project Inventory into Agent Chat without relying on generic UE
knowledge.

## 2026-05-27 Agent Chat Editor Operation Routing Fix

本轮修复了自由聊天触发 Blueprint Graph 操作时的两类路由问题：

- 中文请求如 `在BP_ProjectSpecificName加上Print String`、`帮我给BP_ProjectSpecificName的Begin play加上print string` 会稳定进入 `editor_add_blueprint_node_template`，不再退化成 Project QA 的说明性回答。
- 英文请求如 `Add a Print String node to BP_ProjectSpecificName EventGraph` 不再因为资产名里的 `Name` 被误判为 `set_actor_metadata`，而是生成 `add_blueprint_node_template` Proposal。
- 如果用户明确写 `unconnected / no connection / 不连接 / 只创建`，后端仍会保持 `entry_event=""`，只创建节点不自动连接 BeginPlay。
- 当内容浏览器没有选中资产时，后端会优先用 Project Inventory 中的同名 Blueprint 解析 `blueprint_path`；因此 UE 插件打开时自动同步 Inventory 越完整，自由聊天里的编辑器操作解析越稳定。

新增回归覆盖：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py::test_agent_chat_routes_chinese_print_string_action_to_editor_operation_from_inventory tests\integration\test_editor_operations.py::test_agent_chat_english_print_string_does_not_match_actor_metadata_when_bp_name_contains_name tests\integration\test_editor_operations.py::test_agent_chat_unconnected_print_string_from_inventory_keeps_node_unlinked -q
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py
```

当前 `run_editor_operation_chat_bridge_smoke.py` 基线为 `30/30 passed`。本修复不要求 UE 前端改接口；如果前端没有选中资产，建议保持插件启动后的 Project Inventory 自动同步。

## 2026-05-31 UMG Reparent Widget Proposal

`Editor Operation Bridge` now includes `reparent_umg_widget`, a confirmed-write
proposal for moving one existing UMG widget under another existing panel widget.

Use it when a HUD/UserWidget already contains the target widget and the desired
parent container, for example:

```json
{
  "operation_type": "reparent_umg_widget",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "IconImage",
    "new_parent_name": "RootCanvas"
  }
}
```

Agent Chat can also create the same Proposal from Project Inventory:

```text
Move WBP_MainHUD IconImage widget under RootCanvas
```

Safety behavior:

- The backend only creates a pending Proposal; UEAgentTool executes after user confirmation.
- The target widget and new parent must be different names.
- UEAgentTool blocks reparenting the root widget, missing widgets, non-panel parents, same-parent moves, and moving a panel under one of its descendants.
- The Widget Blueprint package is marked dirty but not auto-saved.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py -q
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py --output -
.\.venv\Scripts\ruff.exe check app tests scripts --no-cache
```

Current no-UE smoke baseline:

```text
editor-operation-chat-bridge: 21/21 passed
```

## 2026-05-31 UMG Duplicate Widget Proposal

`Editor Operation Bridge` now includes `duplicate_umg_widget`, a confirmed-write
proposal for copying one existing non-panel UMG widget under the same parent.

Use it when the Widget Blueprint already contains a reusable child widget and
you want a second instance with a new name:

```json
{
  "operation_type": "duplicate_umg_widget",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "IconImage",
    "new_widget_name": "IconImage_Copy"
  }
}
```

Agent Chat can also create the same Proposal from Project Inventory:

```text
Duplicate WBP_MainHUD IconImage widget as IconImage_Copy
```

Safety behavior:

- The backend only creates a pending Proposal; UEAgentTool executes after user confirmation.
- The source widget and new widget name must be different.
- UEAgentTool blocks missing widgets, duplicate target names, root widget duplication, panel widget duplication, and widgets without a parent panel.
- UEAgentTool copies common slot layout fields for `CanvasPanelSlot`, `HorizontalBoxSlot`, `VerticalBoxSlot`, and `OverlaySlot` when source and target slot types match.
- The Widget Blueprint package is marked dirty but not auto-saved.

Current no-UE smoke baseline:

```text
editor-operation-chat-bridge: 21/21 passed
```

## 2026-05-31 UMG Delete Widget Proposal

`Editor Operation Bridge` now includes `delete_umg_widget`, a confirmed-write
proposal for removing one existing non-root non-panel UMG widget.

Use it when a test Widget Blueprint contains a child widget that should be
removed after review:

```json
{
  "operation_type": "delete_umg_widget",
  "payload": {
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "IconImage_Copy"
  }
}
```

Agent Chat can also create the same Proposal from Project Inventory:

```text
Remove WBP_MainHUD IconImage widget
```

Safety behavior:

- The backend only creates a pending Proposal; UEAgentTool executes after user confirmation.
- UEAgentTool blocks missing widgets, root widget deletion, Panel widget deletion, and widgets without a parent panel.
- Deletion is wrapped in `FScopedTransaction`, so editor Undo can restore the widget.
- The Widget Blueprint package is marked dirty but not auto-saved.

Current no-UE smoke baseline:

```text
editor-operation-chat-bridge: 21/21 passed
```

## 2026-06-04 UMG Result Diagnostics

UMG editor-operation results now produce structured diagnostics when the UE
plugin reports common execution errors. The backend stores the diagnostics under
`result_summary.operation_diagnostics` with:

- `schema_version=umg_operation_diagnostics_v1`
- `category=umg`
- `execution_error_codes`
- `diagnostic_flags`
- `repair_advice`

Common mappings include:

- `widget_blueprint_not_found` / `widget_blueprint_load_failed` ->
  `umg_blueprint_unresolved`
- `widget_not_found` / `target_widget_not_found` / `source_widget_not_found` ->
  `umg_widget_unresolved`
- `parent_widget_not_found` / `new_parent_widget_not_found` ->
  `umg_parent_unresolved`
- `widget_class_not_supported` -> `umg_widget_class_unsupported`
- `slot_type_not_supported` -> `umg_slot_unsupported`
- `brush_resource_not_found` -> `umg_brush_resource_unresolved`
- duplicate-name and unsafe tree operations -> deterministic warning/error
  advice

Frontend impact: no mandatory change. Existing Proposal cards and result
callbacks remain compatible. For richer User View / Debug View output,
UEAgentTool should continue reporting `errors[].code` and/or `result.error_code`
with stable values such as `widget_not_found`; the backend will turn those into
diagnostic flags and repair-advice actions automatically.

When diagnostics are available, `user_view.blocks[]` also includes
`block_type=editor_operation_umg_details`. This block summarizes the target
Widget Blueprint, widget name, execution error codes, dirty packages, failed
fields, and UE error messages so the normal UI can show the issue without
forcing users to inspect raw JSON.

## 2026-05-31 Asset Read-only Inspection APIs

`Editor Operation Bridge` now also exposes two read-only Asset inspection
endpoints backed by the latest Project Inventory snapshot:

```http
GET /api/v1/editor-operations/inspect/assets?asset_type=StaticMesh&query=Rock
GET /api/v1/editor-operations/inspect/asset-detail?asset_id=SM_Rock
```

Use these when a tool or UI needs stable project facts without creating a
confirmed-write Proposal:

- `inspect_assets` returns matching asset records, including captured path,
  type, package path, dependencies, referencers, settings, and properties when
  present in Project Inventory.
- `inspect_asset_detail` returns one asset by `asset_id`, `asset_path`, name,
  or fallback query.
- Both endpoints are `read_only`; they do not load UE packages, mutate Asset
  Registry state, rename/move/delete assets, or save anything.
- Agent Chat can still use the broader `query_project_inventory` tool for
  natural language project questions. These endpoints are a clearer tool/API
  boundary for panels, Debug View, and future MCP-compatible adapters.

## 2026-05-31 Asset Duplicate Proposal

`Editor Operation Bridge` now includes `duplicate_asset`, a confirmed-write
proposal for copying one existing UE asset to a new `/Game` path.

Example:

```json
{
  "operation_type": "duplicate_asset",
  "payload": {
    "source_asset_path": "/Game/Blueprints/BP_EnemySpawner",
    "new_name": "BP_EnemySpawner_Copy",
    "target_folder": "/Game/Blueprints"
  }
}
```

Agent Chat can also create the Proposal from selected assets or Project
Inventory:

```text
Duplicate BP_EnemySpawner asset as BP_EnemySpawner_Copy
```

Safety behavior:

- Backend creates a pending Proposal only; UEAgentTool executes after user confirmation.
- Source and target must both stay under `/Game`.
- Target path must differ from the source path.
- UEAgentTool blocks missing source assets and existing target assets.
- The duplicated package is marked dirty but not auto-saved.

Current no-UE smoke baseline:

```text
editor-operation-chat-bridge: 21/21 passed
```

## 2026-05-31 Asset Redirector Fixup Proposal

`Editor Operation Bridge` now includes `fixup_redirectors`, a confirmed-write
asset maintenance proposal for cleaning Unreal redirectors under one bounded
`/Game/...` folder.

Example:

```json
{
  "operation_type": "fixup_redirectors",
  "payload": {
    "folder_path": "/Game/Blueprints",
    "recursive": true,
    "max_redirectors": 50
  }
}
```

Agent Chat can create the same Proposal from explicit maintenance requests:

```text
Fix redirectors in /Game/Blueprints
```

Safety behavior:

- Backend creates a pending Proposal only; UEAgentTool executes after user confirmation.
- The folder must be a bounded `/Game/...` subfolder; `/Game` root is rejected.
- `max_redirectors` defaults to `50` and is capped at `200`.
- UEAgentTool scans `UObjectRedirector` assets through Asset Registry and blocks execution if the scan exceeds the configured cap.
- Redirector fixup may update referencers or redirector packages through Unreal's `AssetTools.FixupReferencers`; review source-control changes after execution.
- After a successful asset rename, batch rename, or move result is reported, the backend may surface a ready follow-up candidate that creates a `fixup_redirectors` Proposal for the source folder. This is still a pending Proposal only; it is never confirmed or executed automatically.

Current no-UE smoke baseline:

```text
editor-operation-chat-bridge: 21/21 passed
```

## 2026-06-01 Editor Operation Catalog Refactor

后端开始把 `Editor Operation Bridge` 从单一大服务拆成更清晰的模块。当前已完成第一步：

- `app/services/editor_operations/catalog.py`：集中保存 operation specs、read-only inspection specs、operation groups、协议常量、字段白名单和 `EditorOperationValidationError`。
- `app/services/editor_operations/capabilities.py`：集中组装 `/editor-operations/capabilities` 返回的工具目录、分组、风险计数和只读能力信息。
- `app/services/editor_operations/result_contracts.py`：集中保存每个 operation 期望 UE 前端回传的结果字段。
- `app/services/editor_operations/preview.py`：集中保存 Proposal preflight checks 和 preview summary 模板。
- `app/services/editor_operation_service.py`：继续负责 Proposal 创建、payload 规范化、结果记录、诊断和历史摘要。
- `app/services/editor_workflow_planner_service.py` 与 `app/services/tool_proposal_bridge_service.py`：直接读取 catalog 中的 operation metadata。

这次是行为不变的结构优化，不影响 UEAgentTool 使用方式。API 路径、Proposal JSON、用户确认流程、UE 前端执行和结果回传契约都保持不变。

本轮回归：

```text
ruff check app tests scripts --no-cache: passed
pytest editor operation / catalog / tool registry / MCP adapter: 149 passed
editor-operation-chat-bridge smoke: 30/30 passed
blueprint-graph-operation smoke: 17/17 passed
```

## 2026-06-03 Editor Operation Result User View Refactor

Editor Operation result display assembly has been split into
`app/services/editor_operations/result_user_view.py`.

This module owns display-ready result blocks for editor-operation execution
results:

- `editor_operation_result_summary`
- `editor_operation_graph_details`
- `editor_operation_follow_ups`

The public HTTP contract is unchanged. `POST /api/v1/editor-operations/results`
still returns the same `user_view`, `follow_up`, `item`, and `task` fields.
Older UEAgentTool builds can continue to ignore `user_view`; newer builds can
render the same blocks as before.

Why this matters:

- Blueprint node/pin summaries are now directly unit-testable.
- The main `EditorOperationService` stays focused on proposal orchestration,
  validation, result persistence, and history APIs.
- Future UI display blocks can be added without growing the core service.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_result_user_view.py tests\unit\test_blueprint_result_diagnostics.py tests\unit\test_editor_operation_results.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py::test_blueprint_node_template_result_summary_includes_graph_diagnostics tests\integration\test_editor_operations.py::test_blueprint_node_template_result_summary_flags_missing_expected_links tests\integration\test_editor_operations.py::test_editor_operation_history_returns_preview_and_result_summary -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py --output -
```

## 2026-06-03 Editor Operation History and Diagnostics Refactor

Editor Operation history and diagnostics response assembly has been split into
`app/services/editor_operations/history.py`.

This module owns read-only JSON projection for:

- `GET /api/v1/editor-operations/history`
- `GET /api/v1/editor-operations/diagnostics`

The database query remains in `EditorOperationService`; the new module only
formats already-loaded Proposal records. Public response fields are unchanged,
including `summary`, `items`, `result_summary`, `diagnostic_flag_counts`,
`repair_action_counts`, and `recent_attention_items`.

Why this matters:

- History filtering and diagnostics counters are now directly unit-testable.
- Debug/observability code is separate from confirmed-write Proposal creation.
- Future history UI fields can be added without touching payload validation or
  editor operation execution flow.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_history.py tests\unit\test_editor_operation_result_user_view.py tests\unit\test_editor_operation_results.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py::test_editor_operation_history_returns_preview_and_result_summary tests\integration\test_editor_operations.py::test_blueprint_node_template_result_summary_flags_missing_expected_links tests\integration\test_editor_operations.py::test_editor_operation_diagnostics_summary_counts_attention_flags -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-05 UMG Plan-only Context Tools

The Tool Registry now mirrors the Blueprint context-tool pattern for UMG. These
tools are plan-only: they read Project Inventory and return a compact context
patch, but they never mutate Unreal Editor state.

New local plan tools:

- `editor_umg_set_widget_blueprint_context`
- `editor_umg_set_cursor_widget`

Call path:

```http
POST /api/v1/mcp/tool-registry/plans/{tool}/call
```

Example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/mcp/tool-registry/plans/editor_umg_set_cursor_widget/call" `
  -ContentType "application/json" `
  -Body '{
    "arguments": {
      "project_id": "RushBa",
      "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
      "widget_name": "TitleText"
    }
  }'
```

Returned context:

- `result.context_patch.umg_edit_context.widget_blueprint_path`
- `result.context_patch.umg_edit_context.root_widget_name`
- `result.context_patch.umg_edit_context.cursor_widget`
- `result.next_tool_hints`

`POST /api/v1/mcp/tool-registry/proposals/prepare` and
`POST /api/v1/mcp/tool-registry/proposals` can now consume
`context.umg_edit_context`. UMG write tools can inherit:

- `widget_blueprint_path`
- cursor widget name for set/layout/visibility/appearance/brush/slot/reparent/
  duplicate/delete proposals
- cursor widget or root widget as `parent_widget_name` for add-widget proposals

Workflow Planner also consumes the same context for `umg_text_widget` and
`umg_hud_group`, using the focused Widget Blueprint and current/root widget as
safe defaults.

Frontend impact: no mandatory UI change. Existing UEAgentTool Proposal
execution remains unchanged. A future MCP/tool panel can call the plan-only UMG
context endpoint before creating UMG Proposals to make the workflow feel closer
to UMGMCP/UElink-style "observe target -> propose edit -> user confirms".

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_tool_manifest_service.py tests\unit\test_tool_proposal_bridge_service.py tests\unit\test_editor_workflow_planner_service.py tests\integration\test_mcp_tools_api.py -q
.\.venv\Scripts\python.exe scripts\run_tool_registry_proposal_bridge_smoke.py --output -
.\.venv\Scripts\python.exe scripts\run_editor_demo_smoke_suite.py --output -
.\.venv\Scripts\python.exe -m ruff check app\tools\registry.py app\services\tool_registry_plan_call_service.py app\services\tool_proposal_bridge_service.py app\services\tool_manifest_service.py app\services\editor_workflow_planner_service.py tests\unit\test_tool_manifest_service.py tests\unit\test_tool_proposal_bridge_service.py tests\unit\test_editor_workflow_planner_service.py tests\integration\test_mcp_tools_api.py scripts\run_tool_registry_proposal_bridge_smoke.py --no-cache
```

Latest deterministic smoke result:

- Tool Registry Proposal Bridge smoke: 13/13 passed.
- Aggregate editor demo smoke suite: 7/7 suites, 83/83 cases passed.

## 2026-06-05 Material Plan-only Context Tools

Material Instance editing now has the same plan-only context bridge as
Blueprint and UMG.

New local plan tools:

- `editor_material_set_instance_context`
- `editor_material_set_parameter_context`

Typical flow:

```text
set material instance context
-> set material parameter context
-> confirmed-write material parameter Proposal
-> user confirmation in UEAgentTool
-> UE Editor API execution
```

Example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/mcp/tool-registry/plans/editor_material_set_parameter_context/call" `
  -ContentType "application/json" `
  -Body '{
    "arguments": {
      "project_id": "RushBa",
      "material_instance_path": "/Game/Materials/MI_Rock",
      "parameter_name": "Roughness"
    }
  }'
```

Returned context:

- `result.context_patch.material_edit_context.material_instance_path`
- `result.context_patch.material_edit_context.cursor_parameter`
- `result.context_patch.material_edit_context.parameter_counts`
- `result.next_tool_hints`

`POST /api/v1/mcp/tool-registry/proposals/prepare` and
`POST /api/v1/mcp/tool-registry/proposals` can consume
`context.material_edit_context`. Material write tools can inherit:

- `material_instance_path`
- `parameter_name`
- `parameter_type` for scalar/vector parameter proposals

Texture and static-switch proposals also inherit the material instance path and
parameter name, while still requiring the actual new texture path or boolean
value from the user/tool request.

Frontend impact: no mandatory UI change. Existing Material Proposal execution
is unchanged. Future UI/MCP panels can call these plan-only endpoints to make
parameter editing less repetitive and less dependent on LLM guessing.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_tool_manifest_service.py tests\unit\test_tool_proposal_bridge_service.py tests\integration\test_mcp_tools_api.py -q
.\.venv\Scripts\python.exe scripts\run_tool_registry_proposal_bridge_smoke.py --output -
.\.venv\Scripts\python.exe scripts\run_editor_demo_smoke_suite.py --output -
.\.venv\Scripts\python.exe -m ruff check app\tools\registry.py app\services\tool_registry_plan_call_service.py app\services\tool_proposal_bridge_service.py app\services\tool_manifest_service.py tests\unit\test_tool_manifest_service.py tests\unit\test_tool_proposal_bridge_service.py tests\integration\test_mcp_tools_api.py scripts\run_tool_registry_proposal_bridge_smoke.py --no-cache
```

Latest deterministic smoke result:

- Tool Registry Proposal Bridge smoke: 15/15 passed.
- Aggregate editor demo smoke suite: 7/7 suites, 85/85 cases passed.

## 2026-06-04 Active Blueprint Graph Focus

Agent Chat / Project QA now resolves the currently focused Blueprint graph from
Project Inventory when the request includes:

- `context.editor_state.current_blueprint_path`
- `context.editor_state.current_graph_name`
- `context.editor_state.selected_node_id` or `selected_node_name` when the
  editor has a focused graph node

The backend matches common UE object path variants such as
`/Game/Blueprints/BP_TestActor.BP_TestActor`, `/Game/Blueprints/BP_TestActor`,
and `BP_TestActor`. If the latest Project Inventory snapshot contains the
Blueprint `graph_summaries`, the Context Bundle exposes:

- `project_inventory_context.current_blueprint`
- `project_inventory_context.current_blueprint_graph`
- `project_inventory_context.current_blueprint_node`
- `active_context.blueprint.current_blueprint_inventory`
- `active_context.blueprint.current_graph_summary`
- `active_context.blueprint.current_node_summary`

This lets the Agent answer questions like "what nodes are in the currently
focused Blueprint graph?" from project facts instead of guessing from generic UE
knowledge. If the current node can be matched by id, node name, or display
title, the backend also exposes a compact node summary with `node_id`,
`node_name`, `node_class`, `title`, `pin_count`, and up to eight pins. This gives
future Blueprint operation planning a safer default target when the user says
"this Blueprint", "the current graph", or "this node".

No frontend contract change is required. Existing UEAgentTool builds that
already submit Project Inventory `graph_summaries` and editor focus fields can
use this automatically. If no snapshot exists, these fields are returned as
`null` rather than omitted, so Debug View and User View parsing remain stable.

When Agent Chat routes a current-graph question to the read-only
`mcp_get_blueprint_graph` tool but no live MCP executor is enabled, the backend
now returns a Project Inventory focus summary instead of a generic placeholder.
The answer includes the current Blueprint, graph metrics, node preview, and the
focused node when available. This keeps the user-facing response useful while
preserving the same no-write safety boundary.

## 2026-06-03 Editor Operation Result Recording Refactor

Editor Operation result recording helpers now live in
`app/services/editor_operations/result_recording.py`.

This module owns:

- standard `operation_result` payload construction;
- task `data.editor_operation` updates;
- task `data.editor_operation_results[]` append behavior;
- Debug View `side_effects[]` result synchronization;
- action proposal `dry_run_preview` refresh;
- `raw_response` mirror updates when a task response already exists.

The database writes remain in `EditorOperationService`, so persistence,
validation, audit logging, and API behavior are unchanged.

Frontend impact: no mandatory change. `POST /api/v1/editor-operations/results`
continues to return the same `item`, `proposal`, `user_view`, `follow_up`, and
`follow_up_quick_actions` fields.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_result_recording.py tests\unit\test_editor_operation_followups.py tests\unit\test_editor_operation_results.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py::test_editor_operation_history_returns_preview_and_result_summary tests\integration\test_editor_operations.py::test_blueprint_node_template_result_summary_flags_missing_expected_links tests\integration\test_editor_operations.py::test_assets_inspect_emits_rename_editor_operation_proposal -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-03 Editor Operation Follow-up Materialization Refactor

Follow-up materialization now lives beside follow-up candidate generation in
`app/services/editor_operations/followups.py`.

This covers the safe conversion from one ready follow-up candidate into a typed
`EditorOperationProposalRequest` payload. `EditorOperationService` keeps the
same public wrapper, so route behavior and response fields do not change.

Safety behavior remains unchanged:

- The materialized step creates a pending Proposal only.
- `auto_execute` remains `false`.
- User confirmation is still required before UEAgentTool executes any Editor
  API.
- Candidates with `missing_inputs` or `proposal_ready=false` are rejected.
- Only operation types registered in the Editor Operation catalog can be
  materialized.

Frontend impact: no mandatory change. Existing calls to
`POST /api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal`
continue to work.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_followups.py tests\unit\test_editor_operation_history.py tests\unit\test_editor_operation_result_user_view.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py::test_blueprint_node_template_result_summary_flags_missing_expected_links tests\integration\test_editor_operations.py::test_blueprint_compile_failed_result_includes_repair_advice tests\integration\test_editor_operations.py::test_editor_operation_follow_ups_require_result_before_suggesting -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-05 Tool Registry Plan-only Blueprint Context Calls

The backend now has a local plan-only Tool Registry call path:

```text
POST /api/v1/mcp/tool-registry/plans/{tool}/call
```

This path is for MCP-style planning tools that prepare context for later editor
operations but do not read/write Unreal Editor state directly. It complements
the existing boundaries:

- Read-only tools use `POST /api/v1/mcp/tool-registry/tools/{tool}/call`.
- Plan-only tools use `POST /api/v1/mcp/tool-registry/plans/{tool}/call`.
- Confirmed-write tools still use `POST /api/v1/editor-operations/proposals`
  or the Tool Registry Proposal Bridge.

New Blueprint Graph context tools:

- `editor_blueprint_set_edit_function`: selects a Blueprint graph/function as
  the default edit target for later add/connect/compile Proposal tools.
- `editor_blueprint_set_cursor_node`: selects a Blueprint node as the default
  cursor node for later pin connection or node insertion planning.

Example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/mcp/tool-registry/plans/editor_blueprint_set_edit_function/call" `
  -ContentType "application/json" `
  -Body '{
    "arguments": {
      "project_id": "RushBa",
      "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
      "graph_name": "EventGraph"
    }
  }'
```

The response contains:

- `result.context_patch.blueprint_edit_context`: compact context that a client
  can merge into later tool calls.
- `result.next_tool_hints`: suggested follow-up tools such as
  `editor_blueprint_add_step`, `editor_connect_blueprint_nodes`, or
  `editor_compile_blueprint`.
- `result.inventory_match`: best-effort Project Inventory match for the graph
  or node.

Safety boundary:

- These tools are `plan_only`.
- They do not create Proposals by themselves.
- They do not execute UE Editor API calls.
- They are not enabled for free-chat auto execution.
- They make the Blueprint workflow closer to UMG-MCP's `set_edit_function` /
  `set_cursor_node` style without changing the existing HTTP Proposal safety
  model.

Frontend impact: no mandatory UI change. A future MCP/tool panel can call this
endpoint before creating Blueprint add/connect/compile Proposals. The current
UEAgentTool can continue using the existing Proposal flow.

The Tool Registry Proposal Bridge can also consume this context. If a client
passes `context.blueprint_edit_context` to
`POST /api/v1/mcp/tool-registry/proposals/prepare` or
`POST /api/v1/mcp/tool-registry/proposals`, Blueprint write tools can inherit:

- `blueprint_path`
- `graph_name`
- cursor node `node_id`
- cursor node output exec pin name when available

This makes the practical flow:

```text
plan-only set_edit_function / set_cursor_node
-> confirmed-write add_step / connect_blueprint_nodes / compile_blueprint proposal
-> user confirmation in UEAgentTool
-> UE Editor API execution
```

Workflow Planner also consumes the same context. If
`context.blueprint_edit_context` is passed to
`POST /api/v1/editor-operations/workflows/plan`, Blueprint workflow templates
can inherit:

- the focused Blueprint path;
- the focused graph/function name;
- the cursor node id;
- the cursor node output exec pin.

This lets a tool panel or future MCP adapter run:

```text
set_edit_function / set_cursor_node
-> /editor-operations/workflows/plan
-> /editor-operations/workflows/steps/proposal
```

The workflow planner still creates plan steps only. Step materialization creates
pending Proposals, and UE writes still require user confirmation.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_tool_proposal_bridge_service.py tests\unit\test_tool_manifest_service.py tests\integration\test_mcp_tools_api.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_workflow_planner_service.py tests\integration\test_editor_operations.py::test_editor_workflow_plan_api_uses_blueprint_edit_context tests\integration\test_editor_operations.py::test_editor_workflow_plan_api_returns_proposal_steps -q
.\.venv\Scripts\python.exe scripts\run_tool_registry_proposal_bridge_smoke.py --output -
.\.venv\Scripts\python.exe scripts\run_editor_demo_smoke_suite.py --output -
.\.venv\Scripts\python.exe -m ruff check app\services\tool_registry_plan_call_service.py app\services\tool_proposal_bridge_service.py app\services\tool_manifest_service.py app\api\routes\mcp_tools.py app\tools\registry.py tests\unit\test_tool_proposal_bridge_service.py tests\unit\test_tool_manifest_service.py tests\integration\test_mcp_tools_api.py --no-cache
```

Latest deterministic smoke result for this slice:

- Tool Registry Proposal Bridge smoke: 10/10 passed.
- Aggregate editor demo smoke suite: 7/7 suites, 80/80 cases passed.

## 2026-06-05 Local Tool Registry Read-only Calls

The backend now exposes a local read-only Tool Registry call path:

```http
POST /api/v1/mcp/tool-registry/tools/{tool}/call
```

This endpoint is intentionally MCP-compatible in shape, but it does not require
an external MCP server. It is meant for demo scripts, optional tool panels, and
future MCP-compatible adapters that need to inspect project facts before
creating a Proposal.

Supported local read-only calls in this slice:

- `get_blueprint_graph` / `mcp_get_blueprint_graph`
- `get_widget_tree` / `mcp_get_widget_tree`
- `editor_inspect_assets`
- `editor_inspect_asset_detail`
- `editor_inspect_level_actors`
- `editor_inspect_level_actor_detail`
- `editor_inspect_material_instance_parameters`
- `editor_inspect_material_instance_detail`

Example:

```http
POST /api/v1/mcp/tool-registry/tools/get_blueprint_graph/call
Content-Type: application/json

{
  "arguments": {
    "project_id": "RushBa",
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "graph_name": "EventGraph"
  }
}
```

The result is sourced from the latest Project Inventory snapshot and returns a
`structuredContent` block with graph metrics, nodes, variables, components, and
snapshot summary metadata. `get_widget_tree` similarly reads Widget Blueprint
tree data when the UE plugin has submitted it in the Inventory snapshot.

The Tool Registry manifest also exposes UI / transport friendly metadata on
each tool annotation:

- `operation_family`: `asset`, `blueprint`, `umg`, `level`, `material`, etc.
- `frontend_executor_id`: the UEAgentTool operation id or read-only executor id.
- `operation_type`: the editor-operation type when the tool maps to one.
- `bridge_kind`: `editor_operation_proposal`, `inventory_readonly`,
  `mcp_readonly_or_inventory_fallback`, or plain `tool_registry`.

Safety boundary:

- This endpoint executes read-only sensing tools only.
- It never creates, confirms, or executes editor writes.
- Confirmed-write tools such as `editor_set_actor_transform` are rejected with
  `tool_is_not_read_only`.
- The normal UE integration path remains HTTP Proposal Bridge:
  Agent creates Proposal -> user confirms in UEAgentTool -> UEAgentTool executes
  Editor API -> backend records result.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_tool_manifest_service.py tests\integration\test_mcp_tools_api.py tests\integration\test_editor_operations.py::test_editor_operation_capabilities_and_registry -q
.\.venv\Scripts\python.exe scripts\run_tool_registry_readonly_smoke.py --output -
.\.venv\Scripts\python.exe scripts\run_tool_registry_proposal_bridge_smoke.py --output -
.\.venv\Scripts\python.exe scripts\run_mcp_tcp_adapter_smoke.py --output -
.\.venv\Scripts\python.exe scripts\run_editor_demo_smoke_suite.py --output -
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-05 UEAgentTool TCP / MCP Adapter Smoke

The optional TCP adapter can connect to the UEAgentTool editor tool server when
the plugin exposes its local JSON-RPC line server. This is separate from the
local Inventory-backed Tool Registry call above:

- Local Tool Registry read-only call: no UE TCP server required; reads the
  latest Project Inventory snapshot.
- MCP TCP adapter call: connects to a live TCP JSON-RPC tool server such as
  UEAgentTool's optional editor tool server.

Typical local configuration:

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_TRANSPORT=tcp
MCP_TCP_HOST=127.0.0.1
MCP_TCP_PORT=8765
MCP_ALLOWED_TOOLS=ue_agent_tools_list,get_editor_context,get_selected_assets,get_asset_details,get_static_mesh_details,get_selected_actors,get_level_actors,get_level_actor_details,get_blueprint_graph,get_blueprint_node_details,get_widget_tree,get_widget_details,get_material_instance_parameters,get_material_parameter_details
MCP_TCP_TIMEOUT_MS=3000
```

Safety boundary:

- `MCP_ALLOWED_TOOLS` is still mandatory and should include read-only tools by
  default.
- Confirmed-write editor operations still use HTTP Proposal Bridge.
- UEAgentTool's raw TCP tool server also rejects write tools and points back to
  the Proposal confirmation flow.

Validation without launching Unreal:

```powershell
.\.venv\Scripts\python.exe scripts\run_mcp_tcp_adapter_smoke.py --output -
```

The smoke emulates the UEAgentTool TCP server and validates:

- backend adapter status for `mcp_tcp`;
- `tools/list` discovery filtered by allow-list;
- `tools/call` for `get_blueprint_graph`;
- `tools/call` for `get_blueprint_node_details`;
- `tools/call` for `get_widget_tree`;
- `tools/call` for `get_widget_details`;
- backend allow-list blocking for a write tool;
- UEAgentTool-style server-side rejection if a raw write tool is explicitly
  allow-listed by mistake.

Optional live check when UEAgentTool is open and its TCP tool server is enabled:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_ue_tool_server_smoke.py --host 127.0.0.1 --port 8765 --output -
```

To also call read-only graph tools, pass real project paths:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_ue_tool_server_smoke.py --host 127.0.0.1 --port 8765 --actor-reference BP_PlayerCharacter_1 --blueprint-path /Game/Blueprints/BP_PlayerCharacter --blueprint-graph-name EventGraph --blueprint-node-query "Print String" --widget-blueprint-path /Game/UI/WBP_MainHUD --output -
```

The live smoke is intentionally not part of CI because it requires Unreal
Editor and the plugin TCP server. It is useful for local demo readiness and
transport troubleshooting.

Agent Chat live sensing behavior:

- When routing selects `mcp_get_blueprint_graph`, `mcp_get_blueprint_node_details`,
  or `mcp_get_widget_tree`, and
  the MCP adapter is configured as ready, the backend now tries the live TCP
  read-only tool first.
- Explicit read-style prompts such as `Show the current Blueprint graph` or
  `Inspect the Widget Tree for /Game/UI/WBP_MainHUD` can select those read-only
  MCP tools. Broader current-project fact questions still prefer Project
  Inventory.
- The Tool Registry marks these read-only sensing tools as
  `allowed_in_free_chat=true`
  because they are read-only and still gated by `MCP_ALLOWED_TOOLS`.
- If the TCP call fails, the tool is not allow-listed, or the UE tool server
  returns an error, the backend next tries the local Tool Registry read-only
  executor backed by the latest Project Inventory snapshot. If that also lacks
  enough data, it falls back to the focused Inventory summary or placeholder
  path.
- In Debug View, `retrieval_trace.mode=mcp_tcp_readonly` means a live TCP tool
  answered. `retrieval_trace.mode=local_tool_registry_readonly` means the answer
  came from local Project Inventory through the same read-only Tool Registry
  contract, not from a live MCP/TCP call.
- This does not grant Agent Chat permission to execute write tools. Writes still
  require Editor Operation Proposal confirmation.

## 2026-06-04 UE Knowledge Domains Expansion

The local knowledge base now includes additional UE-focused domains for
Blueprint/UMG automation and editor-operation troubleshooting.

Added domains and folders:

- `knowledge/blueprint-umg/`: UMG Widget Tree layout and Blueprint graph safe
  templates.
- `knowledge/troubleshooting/`: editor operation error codes and repair advice.
- `knowledge/engine-notes/ue-material-instance-parameters.md`: Material
  Instance parameter editing notes.

How it is used:

- Agent Chat and Code Generate can retrieve these notes through the existing
  RAG/local lexical search pipeline.
- When embeddings/Qdrant are disabled, the same Markdown files are still used
  by lexical retrieval and local grep fallback.
- When embeddings/Qdrant are enabled and the KB is reindexed, the same files
  can also participate in vector or hybrid retrieval.

Recommended maintenance workflow:

1. Add distilled UE notes under the most specific `knowledge/` folder.
2. Include `domain`, `topic`, `keywords`, and `use_for` metadata near the top.
3. Restart the backend or call the knowledge refresh/reindex endpoint.
4. Add or update a small eval case when the new note should be discoverable.

Validation:

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --dataset tests/eval/rag_ue_knowledge_dataset.jsonl --source-path ./knowledge --top-k 4 --min-hit-at-k 0.8 --min-route-accuracy 1.0 --output storage/artifacts/evals/rag-ue-knowledge-latest.json --markdown-output docs/rag-ue-knowledge-report.md
```

## 2026-06-03 Shared Proposal Presenter Refactor

Proposal response serialization now lives in `app/services/proposal_presenter.py`.
Both generic Proposal APIs and Editor Operation APIs use the same
`proposal_payload()` helper.

This keeps the public `ActionProposal` response shape consistent across:

- pending Proposal list/detail APIs;
- Proposal decision responses;
- Editor Operation Proposal creation responses;
- Editor Operation result responses.

Frontend impact: no mandatory change. The fields remain `proposal_id`, `title`,
`proposal_type`, `before_summary`, `after_summary`, `rationale`, `risk_flags`,
`dry_run_preview`, `display_hints`, `requires_confirmation`, and `confirmation`.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_proposal_presenter.py tests\integration\test_editor_operations.py::test_editor_operation_rename_proposal_confirm_and_result tests\integration\test_editor_operations.py::test_assets_inspect_emits_rename_editor_operation_proposal tests\integration\test_mcp_tools_api.py::test_tool_registry_proposal_api_creates_pending_editor_proposal -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-03 Editor Operation Proposal Builder Refactor

Editor Operation Proposal response assembly now lives in
`app/services/editor_operations/proposal_builder.py`.

`EditorOperationService` still owns request normalization, target extraction,
database persistence, and audit logging. The new builder only assembles the
already-computed dry-run preview, display hints, confirmation contract, and
Blueprint graph policy preview.

Frontend impact: no mandatory change. The Proposal response, `dry_run_preview`,
`display_hints`, confirmation endpoints, and Blueprint graph policy fields keep
the same shape.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_proposal_builder.py tests\integration\test_editor_operations.py::test_blueprint_node_template_print_string_proposal_contract tests\integration\test_editor_operations.py::test_editor_operation_rename_proposal_confirm_and_result -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-03 Editor Operation Summary Builder Refactor

Editor Operation before/after summary generation now lives in
`app/services/editor_operations/summaries.py`.

The summary builder is pure and only turns a normalized operation payload into
display text. `EditorOperationService` still handles detection, normalization,
Proposal creation, persistence, and audit logging.

Frontend impact: no mandatory change. Existing `before_summary` and
`after_summary` fields remain part of the same Proposal response contract.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_summaries.py tests\integration\test_editor_operations.py::test_blueprint_node_template_delay_print_string_proposal_contract tests\integration\test_editor_operations.py::test_set_umg_widget_appearance_proposal_contract tests\integration\test_editor_operations.py::test_place_actor_in_level_proposal_contract tests\integration\test_editor_operations.py::test_set_material_instance_texture_parameter_proposal_contract -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-03 Editor Operation Affected Targets Refactor

Editor Operation affected-target preview generation now lives in
`app/services/editor_operations/targets.py`.

The target builder is pure and only turns a normalized operation payload into
the `affected_targets` list used by dry-run previews and preflight checks.
`EditorOperationService` still owns normalization, Proposal persistence, and
confirmed-write safety boundaries.

Frontend impact: no mandatory change. Existing `dry_run_preview.affected_targets`
items keep the same shape.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_targets.py tests\integration\test_editor_operations.py::test_batch_rename_assets_proposal_contract tests\integration\test_editor_operations.py::test_blueprint_node_template_custom_event_print_string_contract tests\integration\test_editor_operations.py::test_set_umg_widget_appearance_proposal_contract tests\integration\test_editor_operations.py::test_arrange_actors_pattern_proposal_contract tests\integration\test_editor_operations.py::test_set_material_instance_scalar_parameter_proposal_contract -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```

## 2026-06-03 Editor Operation Follow-up Candidate Refactor

Editor Operation follow-up candidate generation now lives in
`app/services/editor_operations/followups.py`.

This module owns:

- Blueprint graph repair candidates such as `connect_blueprint_nodes`.
- Blueprint compile retry candidates.
- Asset redirector fixup candidates after asset rename / move results.
- Stable node identifier helpers used by follow-up proposal hints.

The safety model is unchanged:

- Follow-up candidates are suggestions only.
- Ready candidates can create a pending Proposal.
- They never execute UE writes automatically.
- The UE frontend still confirms and executes through the normal Editor
  Operation Proposal flow.

Frontend impact: no mandatory change. Existing follow-up quick actions and
`/editor-operations/proposals/{proposal_id}/follow-ups` responses keep the same
shape.

Validation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_editor_operation_followups.py tests\unit\test_editor_operation_history.py tests\unit\test_editor_operation_result_user_view.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_editor_operations.py::test_blueprint_node_template_result_summary_flags_missing_expected_links tests\integration\test_editor_operations.py::test_blueprint_compile_failed_result_includes_repair_advice tests\integration\test_editor_operations.py::test_editor_operation_follow_ups_require_result_before_suggesting -q
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
```
## 2026-06-05 Update: UMG Widget Detail Read-only Tool

后端新增一个 Project Inventory 驱动的 UMG 只读工具：

- Tool ID: `editor_inspect_umg_widget_detail`
- Local call: `POST /api/v1/mcp/tool-registry/tools/editor_inspect_umg_widget_detail/call`
- Manifest profiles: `readonly_sensing`, `umg_demo`
- Side effect: `read_only`

示例：

```json
{
  "arguments": {
    "project_id": "YourProject",
    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
    "widget_name": "TitleText"
  }
}
```

返回会包含：

- `structuredContent.widget_name`
- `structuredContent.widget_class`
- `structuredContent.parent_widget_name`
- `structuredContent.slot`
- `structuredContent.layout`
- `structuredContent.properties`
- `structuredContent.style`
- `structuredContent.children`
- `structuredContent.widget_tree_summary`

这个工具用于“先观察再提案”的工作流：Agent 或 MCP-style client 可以先读取某个 Widget 的属性、父子关系和布局，再创建 `editor_set_umg_widget_text`、`editor_set_umg_widget_layout`、`editor_set_umg_widget_appearance`、`editor_reparent_umg_widget` 等 confirmed-write Proposal。

边界：

- 不直接修改 Widget Blueprint。
- 不绕过 Proposal confirmation。
- 结果质量依赖 UEAgentTool 提交的 Project Inventory 是否包含 Widget Tree / slot / properties / style 字段。
- 不强制 UE 前端改 UI；如果后续要做更好的 UMG 面板，可以把这个工具作为“Inspect Widget Detail”按钮或 Agent 自动观察步骤。

## 2026-06-05 Update: Blueprint Node Detail Read-only Tool

后端新增一个 Project Inventory 驱动的 Blueprint 节点只读工具：

- Tool ID: `editor_inspect_blueprint_node_detail`
- Local call: `POST /api/v1/mcp/tool-registry/tools/editor_inspect_blueprint_node_detail/call`
- Manifest profiles: `readonly_sensing`, `blueprint_demo`
- Side effect: `read_only`

示例：

```json
{
  "arguments": {
    "project_id": "YourProject",
    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
    "graph_name": "EventGraph",
    "node_title": "Print String"
  }
}
```

返回会包含：

- `structuredContent.blueprint_path`
- `structuredContent.graph_name`
- `structuredContent.node_id`
- `structuredContent.node_title`
- `structuredContent.node_class`
- `structuredContent.pins`
- `structuredContent.linked_pins`
- `structuredContent.graph_summary`

这个工具用于 Blueprint 自动化的“先观察再提案”流程。Agent 可以先读取某个节点的 pin 和连接关系，再决定是否创建 `editor_connect_blueprint_nodes`、`editor_blueprint_add_step` 或 `editor_compile_blueprint` Proposal。

边界：

- 不创建、不删除、不连接蓝图节点。
- 不绕过 Proposal confirmation。
- 结果质量依赖 UEAgentTool 提交的 `graph_summaries[].nodes[].pins` 是否足够完整。
- 不强制 UE 前端改 UI；未来可以在 Blueprint 工具面板里增加“Inspect Node Detail”入口。

## 2026-06-05 Update: Read-only Tool Builder Split

后端把 Tool Registry local read-only executor 做了一次小型模块化拆分：

- `app/services/tool_registry_readonly_call_service.py`：保留工具调度、权限边界和统一响应 envelope。
- `app/services/tool_registry_readonly/blueprint.py`：负责 Blueprint Node Detail 的纯结果构建。
- `app/services/tool_registry_readonly/umg.py`：负责 Widget Tree / Widget Detail 的纯结果构建。

这个拆分不改变任何 API，也不要求 UE 前端修改。它的目的只是让后续继续补 MCP-style sensing 工具时，不把主执行器重新堆成巨型文件。

## 2026-06-05 Update: Tool Manifest Workflow Preview

`GET /api/v1/mcp/tool-registry/manifest?profile=umg_demo` 等 profile 现在会在 `profiles.selected.workflow_preview` 中返回轻量流程提示。

示例字段：

- `workflow_id`
- `title`
- `summary`
- `observe_tools`
- `context_tools`
- `proposal_tools`
- `happy_path`
- `confirmation_required`

用途：

- 帮助前端或演示页展示“先观察 -> 选上下文 -> 生成 Proposal -> 用户确认”的推荐路径。
- 帮助 MCP-style client 理解哪些工具适合只读观察，哪些工具只做 context，哪些工具会进入 confirmed-write Proposal。
- 不改变任何工具执行行为；confirmed-write 仍然必须走 Proposal confirmation。

当前提供 preview 的 profile：

- `readonly_sensing`
- `blueprint_demo`
- `umg_demo`
- `material_demo`
- `level_demo`
- `asset_maintenance`

## 2026-06-06 Update: Aggregated Tool Workflow Previews

`GET /api/v1/mcp/tool-registry/manifest?profile=full` now also returns
`manifest.profiles.workflow_previews`.

This field is an aggregate list of all available profile workflow previews. It
is designed for user-facing clients such as the UE plugin:

- Show users the recommended operation path.
- Explain which tools are read-only observe tools.
- Explain which tools only set temporary context.
- Explain which tools create confirmed-write Proposals.

The UE plugin `Show Tools` action now displays a compact
`Suggested Tool Workflows` card after the editor-operation catalog. If workflow
preview loading fails, the original tool catalog still works.

Important boundary:

- Workflow previews are metadata only.
- They do not execute editor operations.
- Confirmed-write operations still require Proposal confirmation in UE.

## 2026-06-06 Update: Live MCP Editor Context Tool

When the optional UEAgentTool TCP editor tool server is enabled, the backend can
use a new read-only MCP-style tool:

```text
mcp_get_editor_context -> get_editor_context
```

Purpose:

- Verify that the live UE editor tool server is reachable.
- Read lightweight editor status before doing deeper Blueprint, UMG, Material,
  or Level sensing.
- Give Agent Chat a grounded answer for explicit questions such as
  "Show the current editor status".

Returned `structuredContent` includes:

- `context_schema_version`
- `server_status`
- `transport`
- `tool_summary.tool_count`
- `tool_summary.read_only_tool_count`
- `tool_summary.confirmed_write_tool_count`
- `tool_summary.category_counts`
- `editor_world.world_name`
- `editor_world.map_name`
- `editor_world.current_level_name`
- `editor_world.selected_actor_count`

Safety boundary:

- This tool is read-only.
- It does not execute editor writes.
- It does not replace Project Inventory; it only complements Inventory with
  live editor status when TCP MCP is enabled.
- Write operations still require HTTP Proposal confirmation in UEAgentTool.

Optional live smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_ue_tool_server_smoke.py --host 127.0.0.1 --port 8765 --output -
```

## 2026-06-08 Update: Live MCP Selected Actors Tool

When the optional UEAgentTool TCP editor tool server supports it, the backend can
use another read-only MCP-style tool:

```text
mcp_get_selected_actors -> get_selected_actors
```

Purpose:

- Read the currently selected Level Actors from the live Unreal Editor session.
- Give Agent Chat a grounded answer for explicit questions such as
  "List selected actors".
- Prepare an observe-before-propose workflow for later actor movement,
  arrangement, and metadata update proposals.

Returned `structuredContent` is expected to include:

- `selection_schema_version`
- `server_status`
- `transport`
- `world_name`
- `map_name`
- `selected_actor_count`
- `max_actors_returned`
- `actors[].actor_label`
- `actors[].actor_name`
- `actors[].actor_class`
- `actors[].actor_path`
- `actors[].transform.location`
- `actors[].transform.rotation`
- `actors[].transform.scale`
- `actors[].component_count`
- `actors[].components[].component_name`
- `actors[].components[].component_class`
- `actors[].components[].is_registered`
- `actors[].components[].is_scene_component`
- `actors[].components[].relative_location`
- `actors[].components[].relative_rotation`
- `actors[].components[].relative_scale`
- `actors[].components[].attach_parent`

Agent Chat routing:

- Explicit read-style prompts such as `List selected actors` can route to
  `mcp_get_selected_actors`.
- The backend first tries the live TCP tool when `MCP_TOOL_ADAPTER_ENABLED=true`,
  `MCP_TRANSPORT=tcp`, and `MCP_ALLOWED_TOOLS` contains
  `get_selected_actors`.
- If live TCP is unavailable, the stable fallback chain remains active and broad
  project-fact questions still prefer Project Inventory.

Safety boundary:

- This tool is read-only.
- It does not move, place, arrange, rename, tag, save, or otherwise mutate
  Actors.
- Actor write operations still require HTTP Editor Operation Proposal
  confirmation in UEAgentTool.

Suggested TCP allow-list:

```env
MCP_ALLOWED_TOOLS=ue_agent_tools_list,get_editor_context,get_selected_assets,get_asset_details,get_static_mesh_details,get_selected_actors,get_level_actors,get_level_actor_details,get_blueprint_graph,get_blueprint_node_details,get_widget_tree,get_widget_details,get_material_instance_parameters,get_material_parameter_details
```

## 2026-06-08 Update: Live MCP Selected Assets Tool

When the optional UEAgentTool TCP editor tool server supports it, the backend can
also use:

```text
mcp_get_selected_assets -> get_selected_assets
```

Purpose:

- Read the currently selected Content Browser assets from the live Unreal Editor
  session.
- Give Agent Chat a grounded answer for explicit questions such as
  "List selected assets".
- Prepare an observe-before-propose workflow for asset rename, move, duplicate,
  redirector fix, or asset inspection proposals.

Returned `structuredContent` is expected to include:

- `asset_selection_schema_version`
- `server_status`
- `transport`
- `content_browser_available`
- `selected_asset_count`
- `max_assets_returned`
- `assets[].asset_name`
- `assets[].asset_path`
- `assets[].asset_type`
- `assets[].package_name`
- `assets[].package_path`

Fallback behavior:

- If MCP/TCP is enabled and `MCP_ALLOWED_TOOLS` contains `get_selected_assets`,
  the backend uses the live TCP result first.
- If MCP/TCP is unavailable but the normal UE HTTP request context already
  contains `selected_assets`, the backend can answer from that request context
  instead of returning a generic placeholder.

Safety boundary:

- This tool is read-only.
- It does not rename, move, duplicate, delete, save, or fix up assets.
- Asset write operations still require HTTP Editor Operation Proposal
  confirmation in UEAgentTool.

## 2026-06-08 Update: Live MCP Material Instance Parameters Tool

When the optional UEAgentTool TCP editor tool server supports it, the backend can
use:

```text
mcp_get_material_instance_parameters -> get_material_instance_parameters
```

Purpose:

- Read scalar, vector, texture, and static-switch parameters from a live
  Material Instance.
- Ground Agent Chat questions such as `Show selected material instance
  parameters` before creating a later Material parameter Proposal.
- Prefer the live frontend MCP/TCP tool when available, then fall back to local
  Project Inventory through the same read-only Tool Registry path.

Arguments:

- `material_instance_path` is optional for live TCP. If omitted, UEAgentTool
  tries the currently selected Content Browser Material Instance.
- Local Inventory fallback can use `material_instance_path`, `asset_path`, or
  `query` to find a captured Material Instance.

Returned `structuredContent` is expected to include:

- `material_instance_schema_version`
- `server_status`
- `transport`
- `resolved_from`
- `material_instance_path`
- `material_instance_name`
- `parent_material`
- `parameter_count`
- `parameters[]`
- `scalar_parameters[]`
- `vector_parameters[]`
- `texture_parameters[]`
- `static_switch_parameters[]`

Safety boundary:

- This tool is read-only.
- It does not edit Material Graphs, compile shaders, save assets, or change
  parameter values.
- Material writes still require normal HTTP Editor Operation Proposal
  confirmation in UEAgentTool.

Optional live smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_ue_tool_server_smoke.py `
  --material-instance-path "/Game/Materials/MI_Player" `
  --material-parameter-name "Roughness"
```

## 2026-06-08 Update: Live MCP Focused Material Parameter Details

`get_material_parameter_details` is the focused read-only version of Material
Instance sensing. It is useful when the user asks one concrete question such as
`What is MI_Player Roughness value?` or `这个材质的 Roughness 是多少？`.

Tool mapping:

```text
mcp_get_material_parameter_details -> get_material_parameter_details
```

Arguments:

- `parameter_name` is required by the backend Tool Registry path. The frontend
  TCP tool also accepts `query` or `target_parameter` as aliases.
- `material_instance_path` is optional for live TCP. If omitted, UEAgentTool
  tries the currently selected Content Browser Material Instance.
- `parameter_type` is optional and can narrow matching to `scalar`, `vector`,
  `texture`, or `static_switch`.

Provider order:

```text
frontend MCP/TCP get_material_parameter_details
  -> local Project Inventory material instance fallback
```

Returned `structuredContent` is expected to include the resolved Material
Instance, parent material, matched parameter name/type/value, and a compact
summary string for Agent Chat. This remains read-only: it does not modify
parameters, save assets, compile shaders, or edit Material Graphs. Any Material
write still uses the confirmed Editor Operation Proposal chain.

## 2026-06-08 Update: Frontend MCP Tool Provider View

The backend now exposes a provider view that merges the static Tool Registry
with optional live frontend MCP discovery:

```text
GET /api/v1/mcp/tool-providers
GET /api/v1/mcp/tool-providers?include_live_discovery=true
```

Use the first form for a fast static view. It does not connect to Unreal Editor
or any MCP server. Use `include_live_discovery=true` only when the UEAgentTool
TCP server or another user-provided MCP server is running and you want the
backend to call `tools/list`.

Provider priority:

- `frontend_mcp_live`: live MCP tools exposed by UEAgentTool or another frontend
  MCP server. These are preferred only for matched read-only tools.
- `local_tool_registry`: backend local read-only or plan-only Tool Registry
  tools, usually backed by Project Inventory.
- `http_proposal_bridge`: confirmed-write path. The backend creates a Proposal
  and UEAgentTool executes it only after user confirmation.

Important safety rules:

- Unknown external MCP tools are shown as `trust_state=external_unmapped`.
- Unknown external tools are not automatically available to Agent free-chat
  routing.
- Raw MCP write execution is not trusted. Write tools must be mapped to
  `ToolSpec`, converted to a Proposal, and confirmed in UEAgentTool.
- HTTP remains the primary UE frontend/backend protocol; MCP is a tool-provider
  layer for observation, compatibility, and future extension.

Example PowerShell check:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/v1/mcp/tool-providers?include_live_discovery=true"
```

Recommended UEAgentTool TCP allow-list:

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_TRANSPORT=tcp
MCP_ALLOWED_TOOLS=ue_agent_tools_list,get_editor_context,get_selected_assets,get_asset_details,get_static_mesh_details,get_selected_actors,get_level_actors,get_level_actor_details,get_blueprint_graph,get_blueprint_node_details,get_widget_tree,get_widget_details,get_material_instance_parameters,get_material_parameter_details
```

### Live Focused Asset Details

`get_asset_details` is the focused read-only tool for one Content Browser asset.
It accepts:

```json
{
  "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter"
}
```

or:

```json
{
  "query": "BP_PlayerCharacter"
}
```

When no query/path is provided, UEAgentTool tries the current Content Browser
selection. The live response includes:

- `asset_name`, `asset_path`, `asset_type`
- `package_name`, `package_path`
- `loaded_class` and `asset_class` when the asset can be loaded
- `blueprint_parent_class` for Blueprint assets
- embedded `static_mesh` details when the asset is a Static Mesh

Agent Chat can route prompts such as `What type and path is BP_PlayerCharacter?`
or `Inspect selected asset details` to this tool. If live MCP/TCP is unavailable,
the backend maps `mcp_get_asset_details` to the existing Project
Inventory-backed `editor_inspect_asset_detail` fallback.

Provider order:

```text
frontend MCP/TCP get_asset_details
  -> local Project Inventory editor_inspect_asset_detail fallback
```

This tool is read-only. It does not rename, move, duplicate, save, delete, or
modify assets. Asset edits still go through confirmed Editor Operation Proposal
tools.

### Live Selected Static Mesh Details

`get_selected_assets` is still a read-only Content Browser sensing tool. When a
selected asset is a Static Mesh, newer UEAgentTool builds also return:

- `assets[].static_mesh.nanite_enabled`
- `assets[].static_mesh.lod_count`
- `assets[].static_mesh.lightmap_resolution`
- `assets[].static_mesh.collision_complexity`
- `assets[].static_mesh.material_slot_count`
- `assets[].static_mesh.material_slots[]`

Agent Chat can route explicit prompts such as `Show selected static mesh
Nanite, LOD and collision settings` to this live MCP/TCP tool. The backend
summarizes these fields in the normal answer card; raw JSON stays in Debug View.
No asset edit is performed by this tool.

`get_static_mesh_details` is the focused version for a single Static Mesh. It
accepts `static_mesh_path`, `asset_path`, or `query`; if omitted, the UE plugin
uses the currently selected Content Browser Static Mesh. It returns the same
Nanite / LOD / lightmap / collision / material slot fields and is useful for
prompts such as `SM_Rock 的 Nanite、LOD、Collision 和材质槽是什么`.

Provider order:

```text
frontend MCP/TCP get_static_mesh_details
  -> local Project Inventory StaticMesh detail fallback
```

This tool is read-only. It does not change Static Mesh settings or save assets.

### Live Level Actor Query

`get_level_actors` is a read-only live MCP/TCP sensing tool for current map /
level Actor inspection. It supports optional `query`, `class_contains`, `tag`,
`folder_path`, and `limit` arguments.

Typical Agent Chat prompts:

- `List current level actors`
- `Find level actors by tag Player`
- `Show current level actors whose class contains Character`

The backend prefers the live UEAgentTool MCP/TCP tool when available. If the TCP
tool is unavailable, it can fall back to local Project Inventory level Actor
inspection. The answer card summarizes world/map, total and matched Actor
counts, filters, Actor labels/classes/folders/tags, and component counts. No
Actor is selected, moved, renamed, tagged, or otherwise modified by this tool.

### Live Focused Level Actor Details

`get_level_actor_details` is the focused version of Level Actor sensing. It
accepts:

```json
{
  "actor_reference": "BP_PlayerCharacter_1"
}
```

The live UEAgentTool response includes one `actor` object with label/name/path,
class, folder, tags, transform, component count, and component summaries. The
backend can route prompts such as `Inspect BP_PlayerCharacter_1 actor transform
and components` to this tool. If live MCP/TCP is unavailable, the backend maps
`mcp_get_level_actor_details` to the existing Project Inventory-backed
`editor_inspect_level_actor_detail` fallback.

Provider order:

```text
frontend MCP/TCP get_level_actor_details
  -> local Project Inventory editor_inspect_level_actor_detail fallback
```

This tool is read-only. It does not select, move, rename, tag, place, delete, or
save Actors. Level Actor writes still go through confirmed Editor Operation
Proposal tools.

### Live Widget Tree Detail Enrichment

`get_widget_tree` remains a read-only MCP/TCP sensing tool, but newer
UEAgentTool builds return more than the raw Widget hierarchy. For each returned
Widget, the live payload can now include:

- `widget_name` / `widget_class`
- `parent_widget` / `parent_widget_class`
- `visibility`
- `render_transform` and `render_transform_pivot`
- `slot`, including `CanvasPanelSlot` position, size, alignment, anchors,
  auto-size, and z-order when applicable
- `text_block.text` and `text_block.font_size` for `UTextBlock`
- `image.resource_path`, `image.resource_name`, and `image.image_size` for
  `UImage`

The backend normal answer card summarizes these fields as compact Widget preview
lines, while the full structured payload stays available in Debug View. This is
useful for prompts such as:

- `Inspect the Widget Tree for /Game/UI/WBP_MainHUD`
- `WBP_MainHUD 里 TitleText 的文本和布局是什么`
- `Which widgets in this UMG blueprint are visible and where are they placed`

Boundary: this tool does not create, delete, reparent, move, style, save, or
compile UMG assets. Any UMG write still goes through confirmed Editor Operation
Proposal tools.

### Live Focused UMG Widget Details

`get_widget_details` is the focused version of Widget Tree sensing. It accepts:

```json
{
  "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
  "widget_name": "TitleText"
}
```

The live UEAgentTool response includes one `widget` object plus direct
`children[]` when the target widget is a panel. The backend can route prompts
such as `Inspect TitleText widget properties and layout in /Game/UI/WBP_MainHUD`
to this tool. If live MCP/TCP is unavailable, the backend maps
`mcp_get_umg_widget_details` to the existing Project Inventory-backed
`editor_inspect_umg_widget_detail` fallback.

Provider order:

```text
frontend MCP/TCP get_widget_details
  -> local Project Inventory editor_inspect_umg_widget_detail fallback
```

This tool is read-only. It does not change text, layout, visibility, parent,
style, brush, save state, or compilation state.

### Live Focused Blueprint Node Details

`get_blueprint_node_details` is the focused version of Blueprint graph sensing.
It accepts:

```json
{
  "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
  "graph_name": "EventGraph",
  "node_query": "Print String"
}
```

The live UEAgentTool response includes the matched node summary plus `pins[]`
and link counts when the graph node can be found. The backend can route prompts
such as `Inspect Print String node pins in /Game/Blueprints/BP_PlayerCharacter`
to this tool. If live MCP/TCP is unavailable, the backend maps
`mcp_get_blueprint_node_details` to the existing Project Inventory-backed
`editor_inspect_blueprint_node_detail` fallback.

Provider order:

```text
frontend MCP/TCP get_blueprint_node_details
  -> local Project Inventory editor_inspect_blueprint_node_detail fallback
```

This tool is read-only. It does not add, delete, connect, compile, save, or
rewrite Blueprint nodes. Blueprint graph writes still go through confirmed
Editor Operation Proposal tools.

## 2026-06-09 Improv5 Quality Gate Snapshot

This snapshot records the current backend-only deterministic verification for
the Improv5 editor-operation and live sensing work. It does not replace real UE
Editor testing, but it is the recommended fast regression gate before packaging
or demo rehearsal.

Commands:

```powershell
.\.venv\Scripts\python.exe scripts\run_editor_demo_smoke_suite.py --output -
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q
$env:RUFF_CACHE_DIR='.tmp_ruff_cache'; .\.venv\Scripts\python.exe -m ruff check app tests scripts
```

Latest result:

- Aggregate editor demo smoke suite: 7/7 suites, 102/102 cases passed.
- Unit and contract tests: 389 passed.
- Ruff: all checks passed.

Covered deterministic smoke suites:

- Blueprint Graph operation Proposal contracts.
- Agent Chat to Editor Operation Proposal routing.
- Workflow materialization to pending Proposals.
- Project Inventory grounded chat.
- Local Tool Registry read-only calls.
- Tool Registry confirmed-write Proposal bridge.
- MCP TCP adapter fixture for read-only live editor sensing.

## 2026-06-09 Update: MCP Confirmed-write Provider Bridge

The backend can now recognize MCP-style write tool names and map them back to
local `ToolSpec` entries before creating a Proposal. This is meant for future
UEAgentTool MCP providers or user-provided MCP frontends.

Supported behavior:

- Live MCP `tools/list` discovery can match local tools by exact tool name,
  `annotations.tool_id`, `annotations.local_tool_id`,
  `annotations.ue_agent_tool_id`, or built-in aliases such as `add_step`,
  `create_widget`, `set_material_parameter`, and `place_actor`.
- Matched read-only tools can still prefer the live MCP provider.
- Matched write tools are marked as `mapped_confirmed_write_proposal_only`.
  They are not directly executed through raw MCP.
- Unknown external write tools are shown as
  `trust_state=external_unmapped_write_blocked` and are not available to Agent
  Chat or automatic workflows.

Proposal bridge usage:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/mcp/tool-registry/proposals/prepare" `
  -ContentType "application/json" `
  -Body '{
    "tool_id": "add_step",
    "arguments": {
      "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
      "graph_name": "EventGraph",
      "step_name": "Print String",
      "text": "Hello from MCP alias"
    },
    "requested_by": "external_mcp_provider"
  }'
```

The response resolves `add_step` to `editor_blueprint_add_step`, then prepares a
pending `add_blueprint_node_template` Proposal. To persist the pending Proposal,
use:

```text
POST /api/v1/mcp/tool-registry/proposals
```

Safety boundary:

- No raw MCP writes.
- No direct LLM editor mutation.
- No trust for unknown external MCP write tools.
- Existing UEAgentTool HTTP Proposal confirmation remains the default execution
  path until a future MCP write executor is tested in the editor.

## 2026-06-09 Update: Backend Tooling Boundary Cleanup

The MCP provider and Tool Registry Proposal bridge code has been split into
smaller helper modules without changing public APIs:

- `app/services/mcp_provider_matching.py` now owns live MCP tool normalization,
  local `ToolSpec` matching, trust-state classification, external-tool blocking,
  and provider row construction.
- `app/services/tool_provider_service.py` remains the public facade for
  `GET /api/v1/mcp/tool-providers`.
- `app/services/tool_proposal_bridge_payloads.py` now owns MCP-style argument
  normalization and active-context defaults for Blueprint, UMG, and Material
  Proposal payloads.
- `app/services/tool_proposal_bridge_service.py` remains the public facade for
  `POST /api/v1/mcp/tool-registry/proposals/prepare` and
  `POST /api/v1/mcp/tool-registry/proposals`.

Frontend impact: no mandatory change. Response fields, Proposal confirmation,
and UEAgentTool execution behavior are unchanged. The purpose of this cleanup is
to make future MCP write mappings and editor tool additions smaller and safer.

## 2026-06-09 Update: Agent Decision Eval v1

The backend now includes a deterministic Agent Decision Eval for the Improv6
context-aware routing chain. It does not call a live LLM, does not launch Unreal
Editor, and does not execute editor writes. It checks whether Agent Chat can
choose the right high-level route, tool id, target kind, context resolution, and
Proposal safety boundary from realistic natural-language prompts.

Run it locally:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_decision_eval.py --output storage\artifacts\evals\agent-decision-eval-latest.json
```

Current deterministic baseline:

- Dataset: `tests/eval/agent_decision_dataset.jsonl`
- Case count: 33
- Covered prompt families: smalltalk, UE knowledge, Project Inventory, selected
  asset/actor/static mesh/widget/material questions, current file reads, logs,
  code review, and confirmed-write Proposal requests.
- Metrics: `route_accuracy`, `tool_accuracy`, `target_kind_accuracy`,
  `context_resolution_accuracy`, `tool_plan_accuracy`,
  `proposal_safety_accuracy`, and `overall_accuracy`.
- Latest local result for this slice: all listed metrics passed at `1.0`.

Routing boundary clarified in this slice:

- Explicit editor writes still create Proposals instead of Project Inventory
  answers.
- Material parameter value questions and explicit current-level Actor listings
  prefer live/read-only editor sensing tools.
- Broad current-project Blueprint graph/node fact questions can still prefer
  Project Inventory when the prompt is about saved project facts.
- `read_project_file` only takes over when the user explicitly asks to read,
  inspect, or summarize a current/selected file; explanatory project questions
  continue through normal Project QA.

Frontend impact: no mandatory change. UEAgentTool can keep using the existing
`POST /api/v1/chat/runs` and Proposal confirmation flow. The new eval is a
backend quality gate for Agent routing and context decisions.

## 2026-06-09 Update: ResponseSynthesizer v1

The response projection chain now has two explicit layers:

```text
handler output
-> ResponseSynthesizer
-> ResponseCritic
-> response_composer
-> persisted UnifiedTaskResponse
```

`ResponseSynthesizer` is intentionally small. It does not call LLMs, does not
execute tools, and does not change Proposal behavior. It only normalizes the
user-facing response contract before the critic runs:

- Ensures `user_view.title`, `user_view.text`, and `user_view.blocks` exist.
- Chooses a readable `assistant_message` from handler text, `data.answer`,
  block text, or a safe fallback message.
- Writes `response_synthesizer_v1` diagnostics to `data` and `debug_view`.

`ResponseCritic` still owns internal-tooling cleanup. This means the frontend
continues to render the same `user_view` and `assistant_message` fields, while
Debug View can explain whether the answer was handler-authored, synthesized
from data, or safely defaulted.

Frontend impact: no mandatory change.

## 2026-06-09 Update: Agent DAG Projection v1

Debug View now includes `agent_dag`, a framework-neutral projection of the
current single-process Agent chain. It is not a new runtime framework and does
not add extra LLM calls. It turns the existing backend pipeline into stable DAG
metadata that can be reviewed, evaluated, or later mapped to LangGraph-style
nodes.

Current nodes:

- `input`: normalize request and editor context.
- `intent_draft`: draft user intent and candidate target.
- `intent_verify`: apply deterministic corrections and safety checks.
- `context_resolve`: resolve selected asset/actor/Blueprint/widget/material
  references.
- `tool_plan`: decide read-only tool, retrieval path, or Proposal plan.
- `evidence_or_tool`: run retrieval/read-only sensing or create pending
  Proposals.
- `response_synthesize`: normalize `user_view` and `assistant_message`.
- `response_critic`: clean internal-tooling leakage from User View.
- `finalize`: persist the final `UnifiedTaskResponse`.

The DAG also exposes linear `edges`, `summary`, and `migration_notes`. Write
operations are still shown as `waiting_confirmation` when a Proposal exists;
the DAG never means the backend executed a UE write.

Frontend impact: optional only. Existing UI can ignore `debug_view.agent_dag`.
If a future debug panel wants to visualize the Agent chain, this field is the
preferred source.

## 2026-06-09 Update: Optional LLM Intent Drafter v1

The Agent chain now has an optional LLM intent-drafting adapter. It is disabled
by default, so existing deterministic routing remains the normal behavior.

Configuration:

```env
AGENT_INTENT_DRAFTER_MODE=disabled
AGENT_INTENT_DRAFTER_MIN_CONFIDENCE=0.78
```

Modes:

- `disabled`: default. Only deterministic router projection is used.
- `shadow`: calls the configured LLM and records `llm_intent_draft`, but does
  not change routing or execution.
- `active`: may apply the LLM draft only after JSON parsing, confidence gating,
  tool allow-list validation, and side-effect safety checks.

Safety rules:

- Unknown tool ids are rejected.
- Low-confidence drafts are ignored.
- A newly suggested confirmed-write tool is blocked unless deterministic rules
  already detected a write intent. Even then, editor writes still create
  Proposals and require user confirmation.
- LLM draft failure, invalid JSON, missing API key, or network failure falls
  back to deterministic routing.

Debug fields:

- `debug_view.llm_intent_draft`
- `debug_view.intent_draft`
- `debug_view.verified_intent`
- `debug_view.agent_dag.nodes[].evidence.llm_drafter_status`

Frontend impact: no mandatory change. This feature only affects backend
decision diagnostics unless explicitly enabled in `.env`.

## 2026-06-09 Update: Active Target Memory v1

The backend now keeps a compact short-term memory of the latest active editor
targets for each session. This is designed for follow-up prompts such as:

- "分析一下这个资产"
- "what about this Blueprint?"
- "检查一下刚才那个材质"
- "summarize the selected actor"

What it stores:

- target kind: `asset`, `blueprint`, `widget`, `level_actor`, `material`,
  `code`, or `log`.
- target id/path/reference, for example `/Game/Characters/BP_Player`.
- a display name and the source task id.

What it does not store:

- raw source code.
- raw asset details.
- full MCP payloads.
- cross-project user profiles.

Flow:

```text
Task with active UE context
-> build agent_turn_context.active_targets
-> update session metadata_json.active_target_memory
-> next task can use this memory if the current request says "this asset"
   but does not include a fresh selected target
```

Priority:

- Fresh UE frontend context always wins.
- Active Target Memory is only used when the current request lacks a concrete
  selected asset/Blueprint/widget/actor/material/code/log target.
- If no current context and no active target memory are available, the backend
  should ask the user to select/sync the target instead of inventing one.

Debug fields:

- `data.context_bundle.active_target_memory`
- `debug_view.context_bundle.active_target_memory`
- `debug_view.memory_summary.updated_active_target_memory`
- `debug_view.context_pack.debug_summary.active_target_memory_count`

Frontend impact: no mandatory change. Existing Project Inventory sync and
active editor context submission already provide the data needed by this
memory layer.
