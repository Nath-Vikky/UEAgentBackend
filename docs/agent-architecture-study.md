# UE Agent Backend 架构学习文档

本文用于面试展示和自学复盘：说明这个后端为什么不只是 LLM wrapper，而是一个收缩边界后的 UE Editor Agent 后端。

## 1. 项目定位

本项目是个人作品级、面试展示级 Agent 后端，服务对象是本地 UE 编辑器插件。它不做云端部署、多租户权限、企业审计和动态插件市场，目标是把一个 Agent 项目最关键的能力做完整、可运行、可解释。

保留 5 个核心功能：

- `Agent Chat / Project QA`
- `Code Review`
- `Code Generate`
- `Logs Analyze`
- `Assets Inspect`

这些功能不是互相孤立的接口，而是共享统一的路由、上下文、记忆、RAG、Skill、观测和响应投影。

## 2. 什么是本项目里的 Agent

本项目里的 Agent 可以理解为一条可解释的任务闭环：

```text
UE 输入
  -> API 入口
  -> Router / Planner
  -> Context Manager
  -> Memory Summary
  -> RAG / Project Inventory / Skill Tool
  -> LLM 或 deterministic fallback
  -> User View / Debug View / Trace
  -> Session / Task 持久化
```

它和普通聊天后端的区别在于：

- 会判断问题是否需要自由聊天、知识库检索、项目快照查询或具体 Skill。
- 会把 UE 编辑器上下文、最近会话、工具任务摘要和检索证据统一打包。
- 会记录为什么这样路由、为什么用了或没用 RAG、为什么 LLM 被跳过。
- 会把同一次结果拆成用户可读视图和调试视图，避免把 raw JSON 暴露给用户。

## 3. 代码结构速览

核心入口：

- `app/main.py`：创建 FastAPI app，注册路由、CORS、生命周期。
- `app/api/router.py`：汇总 `/api/v1` 下的路由。
- `app/api/routes/*.py`：HTTP 接口层，只做请求转发和轻量参数处理。

Agent 核心：

- `app/services/task_service.py`：统一任务编排入口，负责路由后执行、持久化、响应组装。
- `app/agent/router.py`：判断 route type、语言、工具选择、RAG 需求。
- `app/agent/context_manager.py`：生成 `context_bundle_v1`。
- `app/agent/memory_manager.py`：生成 `memory_summary_v1`。
- `app/agent/decision_trace.py`：生成 `agent_decision_trace_v1`。
- `app/skills/registry.py`：固定内置 Skill manifest。
- `app/skills/runtime.py`：Skill 运行态和 lifecycle。
- `app/skills/executors/*.py`：各核心 Skill 的具体执行逻辑。

知识库与检索：

- `app/services/kb_service.py`：知识库导入、状态、Project QA 检索。
- `app/rag/ingestion/*`：文档加载、清洗、解析、切分、去重。
- `app/rag/indexing/*`：embedding、sparse index、Qdrant。
- `app/rag/retrieval/*`：过滤、混合检索、citation。
- `scripts/run_rag_eval.py`：本地 RAG 评测入口。

UE 项目事实：

- `app/services/project_inventory_service.py`：保存和查询 UE 端传来的资产、代码文件、设置快照。
- `app/api/routes/project_inventory.py`：Project Inventory 接口。

持久化与观测：

- `app/db/models/*`：session、task、KB、proposal、audit 等表。
- `app/db/repositories/*`：数据库访问封装。
- `app/observability/*`：metrics、audit、telemetry、LangSmith 元数据层。
- `app/services/monitoring_service.py`：alerts 和监控视图。

## 4. Agent Loop 关键阶段

### User Input

UE 前端通过 `/api/v1/chat/runs` 或 `/api/v1/tasks/...` 发送统一请求。请求里通常包含：

- `session`：会话 ID 和当前消息。
- `context`：UE 工程名、当前面板、当前文件、选中资产等。
- `payload`：功能输入，例如 user query、file path、asset items、log text。
- `runtime_options`：模型 profile、debug、输出语言等。

### Router / Planner

`classify_request()` 会输出：

- `intent.route_type`：`direct_answer`、`project_qa`、`single_tool`、`workflow` 等。
- `route.selected_tool_id`：例如 `query_project_inventory`、`review_ue_cpp_files`。
- `locale.final_output_language`：最终输出语言。
- 是否需要 RAG、是否需要 Project Inventory。

### Context Manager

`build_context_bundle()` 会把上下文整理成一个紧凑结构：

- `input_summary`
- `editor_context`
- `language_context`
- `recent_messages`
- `session_summary`
- `project_inventory_context`
- `retrieval_context`
- `tool_context`
- `budget`

核心思想：不要把所有历史和工具结果都塞进 prompt，而是先裁剪、摘要、分类，再交给 LLM 或工具。

### Memory

`update_session_memory()` 在长会话中生成 deterministic summary。它不是用户画像，也不是跨项目长期记忆，只是当前 session 的上下文压缩。

### RAG

Project QA 会根据 router 判断使用知识库。知识库可以工作在：

- lexical-only：只用本地词法检索。
- vector：用 embedding + Qdrant。
- hybrid：词法和向量结合。

如果只配置了 LLM，没有配置 embedding / Qdrant，系统仍可用 lexical 检索降级。

### Project Inventory Tool

UE 项目里的“当前有哪些蓝图资产”“某个资产 Nanite/Lod/父类/依赖关系是什么”不应该让 LLM 猜。前端插件采集项目快照后，通过 Project Inventory 保存，Agent Chat 再按用户问题调用查询工具。

### Skill Executor

固定内置 Skill 负责具体能力。每个 Skill 都按同一协议拆分：

```text
collector -> rules -> retrieval -> llm_analyzer -> projector
```

例如 Code Review：

- collector：扫描和读取 UE 源码文件。
- rules：硬编码路径、Tick 中加载资源等确定性检查。
- retrieval：查代码规范、项目规则、引擎笔记。
- llm_analyzer：让 LLM 综合解释。
- projector：输出 `user_view.blocks`、`data.llm_analysis`、Debug 字段。

### Response Projection

一次响应会分层输出：

- `assistant_message`：聊天里最直接的文本。
- `user_view`：前端主 UI 应优先渲染的结构。
- `debug_view`：排查路由、上下文、检索、Skill、LLM 的结构。
- `data`：功能数据。
- `trace_summary`：简短链路摘要。
- `artifacts`：生成物或附件。

## 5. 和 nanobot 的参考关系

本项目参考的是类似 Agent 框架中“模块化、可解释、工具化”的思想，而不是复制完整平台：

- 借鉴：路由、工具调用、上下文、记忆、RAG、可观测、可扩展能力边界。
- 不复制：多渠道接入、云部署、企业权限、复杂长期 memory、多 agent 协作市场。

面试时可以这样讲：这个项目不是追求框架规模，而是把 UE 编辑器场景下最有辨识度的 Agent 闭环做完整，并能通过 Debug View 证明每一步发生了什么。

## 6. 为什么选择固定内置 Skill

固定内置 Skill 的好处：

- 功能边界清楚，适合 UE 插件 UI。
- 方便测试和调试。
- 避免个人项目过度平台化。
- 后续优化可以在 Skill 内分层扩展，不需要到处改主流程。

什么时候新增 Skill：

- 出现全新的用户意图。
- UI 面板和输入输出形式明显不同。
- 不能自然归入现有 5 个 Skill。

否则优先扩展现有 Skill 的 collector、rules、retrieval、llm_analyzer 或 projector。

## 7. 面试复盘讲法

可以用一条真实问题复盘：

用户问：“当前项目有哪些蓝图资产？”

流程：

- Router 判断这是项目事实问题，不是普通聊天。
- Context Manager 带上项目名、编辑器上下文、最近消息。
- Project QA tool plan 选择 Project Inventory，而不是只查知识库。
- Inventory 查询当前项目快照，按 Blueprint 类型过滤。
- 如果 LLM 可用，结合查询结果生成自然语言；如果不可用，返回 inventory fallback。
- Debug View 展示 `agent_decision_trace`、`context_bundle`、`skill.lifecycle` 和 `inventory.summary`。

这说明项目具备：意图判断、工具调用、上下文管理、结构化事实源、降级策略和可观测性。
