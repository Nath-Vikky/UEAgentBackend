# UE Agent Backend User Guide

## 0. 文档边界

公开仓库默认只保留：

- `README.md`：快速启动和最小配置。
- `docs/backend-user-guide.md`：完整使用手册。
- `docs/architecture.md`：公开架构说明。
- `docs/integration-smoke-tests.md`：本地端到端 smoke test 请求示例。
- `docs/benchmark-report.md`：当前量化评估结果。
- `docs/hallucination-guard-report.md`：证据不足与幻觉守卫评估结果。
- `docs/project-review-checklist.md`：项目收口、验证和交付检查清单。
- `docs/release-notes/v0.1.0.md`：稳定版本说明。

开发过程文档，例如 `docs/improveplan.md`、`docs/backend-dev-log.md`、`docs/frontend-unified-handoff.md`、架构学习笔记和请求生命周期复盘，建议只保留在本地，不发布给普通使用者。这样 GitHub 页面会更清爽，也更接近一个可交付项目。

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
- 后端会校验文件必须位于 `project_root` 内。
- 只允许读取 `.h/.cpp/.cs/.md/.txt/.json/.ini/.uproject/.uplugin/.yaml/.yml` 等文本文件。
- 默认最多读取约 40KB，最大 120KB。
- 只读，不写入、不删除、不移动、不执行。

### Tool Contract

后端有轻量工具契约校验：

- `validate_tool_registry()`：启动时检查工具注册表。
- `validate_tool_call_input()`：检查 ReAct 工具调用输入是否满足 required/type。
- `validate_tool_result()`：检查工具结果是否满足 required/type。
- `app/tools/context.py`：提供 `ToolContext`、`ToolResult`、`CompositeToolResult`，作为后续新工具 executor / MCP transport 的标准入参和出参 envelope。

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
.\.venv\Scripts\python.exe scripts\run_hallucination_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --min-grounding-accuracy 1.0 --max-unsupported-answer-rate 0.0 --output storage\artifacts\evals\hallucination-guard-latest.json --markdown-output docs\hallucination-guard-report.md
```

GitHub Actions 当前仅保留手动触发入口，不再随 push 自动运行。日常验证以本地 Ruff、pytest 和 RAG eval 为准；CI 只用于需要时手动复核，不做部署。

`storage/artifacts/evals/*.md` 是本地生成的 Markdown 评估报告，展示 `hit_at_k`、`mrr`、`route_accuracy`、`citation_coverage` 等核心指标。当前评估是 smoke 级别，用于证明“可测、可复现、可继续优化”，不是企业级大规模 benchmark。

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
- `docs/rag-agentic-ab-report.md`

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

当前 Code Generate 已补充第一批常用 UE 场景模板：当需求包含“角色增强输入 / Enhanced Input Character / Input Mapping Context / Input Action”等信号时，即使没有配置 LLM，也会返回 `ACharacter` 版本的 Enhanced Input 草稿，建议路径为 `Source/<Module>/Public/<Class>.h` 和 `Source/<Module>/Private/<Class>.cpp`，并在 `patch_plan` 中提示添加 `EnhancedInput` 模块依赖。交互组件、射线交互组件、GameInstanceSubsystem 也有基础兜底草稿。

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
  ]
}
```

常用查询：

- `GET /api/v1/project-inventory/summary`：资产和代码文件总览
- `GET /api/v1/project-inventory/assets?asset_type=StaticMesh`：按资产类型查询
- `GET /api/v1/project-inventory/assets/{asset_id}`：查看单个资产详情
- `GET /api/v1/project-inventory/code-files?module_name=RushBa`：查询代码文件索引
- `POST /api/v1/project-inventory/query`：按自然语言关键词查询资产或代码索引

Project Inventory 已经最小接入 Agent Chat / Project QA。用户问“工程里有哪些资产”“有哪些开启 Nanite 的静态网格体”“某模块有哪些 C++ 文件”这类项目事实问题时，后端会先查询项目快照，并把命中的资产 / 代码摘要并入回答上下文。LLM 不可用时也会返回基于快照的基础回答。

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
      "code_file_type_counts": {"cpp": 1}
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
- `debug_view.context_bundle.budget`：字符预算、估算字符数、裁剪策略和 warnings。
- `debug_view.memory_summary.context_budget`：Debug View 中更短的预算摘要，方便快速判断是否接近上下文限制。

当前边界：

- 工具型任务不会写入 `/sessions/{session_id}/history`，只写入 task 列表和 tool context 摘要。
- 第一版不做自动长期记忆总结，不做复杂 graph，也不做多 agent 上下文共享。
- 如果需要看某次请求到底带了哪些上下文，优先打开 `debug_view.context_bundle`，不要从 raw prompt 反推。

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
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output docs\benchmark-report.md
```

默认模式：

- `offline_fallback`：不调用 live LLM，适合可复现本地评估。
- `RAG_MODE=lexical`：benchmark 中关闭向量依赖，确保没有 embedding / Qdrant 也能跑。
- `source_paths=./README.md, ./docs, ./knowledge`：同时评估公开项目文档问答和 UE 知识库问答。
- benchmark 会把 `--source-path` 同步写入隔离运行时的 `KB_SOURCE_PATHS`，保证 RAG 主索引和 local grep fallback 搜同一批资料。
- 目录扫描默认跳过本地过程文档，例如 `docs/improveplan.md`、`docs/frontend-unified-handoff.md`、`docs/backend-dev-log.md`。如果确实要导入这些文件，需要显式把文件路径写进 `source_paths`。

如果要评估真实 LLM 链路：

```powershell
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --use-live-llm --markdown-output docs\benchmark-report.md
```

当前报告位置：

- `docs/benchmark-report.md`
- `docs/hallucination-guard-report.md`
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
- `capabilities.tool_registry.protocol.transports`：`local_python / http / mcp_stdio / mcp_http`
- `capabilities.tool_registry.protocol.execution_policy`：自由聊天、草稿工具和确认写入工具的统一执行边界。
- `capabilities.tool_registry.tools[].category`：工具类别。
- `capabilities.tool_registry.tools[].transport`：当前工具执行通道。
- `capabilities.tool_registry.tools[].requires_confirmation`：是否必须用户确认。
- `capabilities.tool_registry.tools[].active_context_keys`：工具依赖哪些上下文。
- `capabilities.tool_registry.tools[].allowed_in_free_chat`：是否允许 Agent Chat 自动选择。

当前执行策略：

- Agent Chat 只能自动调用 `read_only` 且 `allowed_in_free_chat=true` 的工具。
- `plan_only` 工具只生成草稿、建议、计划或 preview，不写入项目。
- `confirmed_write` 工具必须经过前端确认和后端安全校验。
- 显式功能面板仍优先使用固定 Skill 流程，避免 LLM 自由选错工具。

Debug View 新增：

- `debug_view.active_context`
- `debug_view.tool_registry_protocol`
- `debug_view.tool_execution_policy`
- `debug_view.tools[].category`
- `debug_view.tools[].transport`
- `debug_view.tools[].side_effect_level`
- `debug_view.tools[].approval_state`

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
MCP_STDIO_COMMAND=
MCP_STDIO_ARGS=
MCP_ALLOWED_TOOLS=
MCP_STDIO_TIMEOUT_MS=3000
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
MCP_STDIO_COMMAND=uv
MCP_STDIO_ARGS=run,--directory,D:/Path/To/McpServer,Server.py
MCP_ALLOWED_TOOLS=get_target_umg_asset,get_widget_tree
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

第一版只支持 3 个操作：

- `rename_selected_asset`：重命名一个选中资产，不移动目录，不批量重命名。
- `apply_static_mesh_basic_settings`：修改一个 Static Mesh 的白名单基础设置。
- `create_blueprint_asset`：在 `/Game` 下创建一个普通 Blueprint 资产。

查看能力：

```http
GET /api/v1/editor-operations/capabilities
```

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

提交后，`GET /api/v1/project-inventory/summary` 会额外返回：

- `blueprint_count`
- `static_mesh_count`
- `map_count`
- `blueprint_parent_class_counts`

Agent Chat / Project QA 会把最近项目快照注入：

- `debug_view.context_bundle.project_inventory_context`
- `debug_view.active_context.inventory`
- `debug_view.active_context.asset.selected_asset_details`
- `debug_view.active_context.code.current_file_inventory`

因此用户问“当前项目有哪些蓝图资产”“这个蓝图有哪些组件/变量”“当前文件属于哪个模块”时，后端可以优先用项目快照回答；如果问题包含“为什么、怎么做、建议、风险”，再组合知识库和 LLM 综合。

`POST /api/v1/project-inventory/query` 也支持可选 `selected_assets`：

```json
{
  "project_id": "RushBa",
  "query": "What components does this asset have?",
  "selected_assets": ["/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter"]
}
```

当问题包含 `this asset / selected asset / components / variables / functions / graphs` 这类上下文词时，后端会优先返回选中资产，而不是列出全项目资产。

边界：

- 后端不解析 `.uasset`，只消费 UE 前端提交的结构化摘要。
- 快照是本地 JSON 存储，不做企业级索引服务。
- Active Context 只保留摘要，不把大段源码或完整资产元数据塞进 prompt。

## 26. Blueprint Graph Automation v1 Proposal 契约

后端已经把蓝图图表自动化纳入 `Editor Operation Bridge`，但第一版仍然只生成 proposal，不直接执行 UE Editor API。UE 前端回传确认：以下三个 operation 已在 UE 侧接入真实执行路径，`GET /api/v1/editor-operations/capabilities` 中的 `frontend_status` 已标记为 `implemented_v1`。

新增 operation：

```text
add_blueprint_variable
add_blueprint_component
create_blueprint_event_stub
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

安全边界：

- 仍然必须走 `confirm -> UE 前端执行 -> results 回传`。
- v1 不做复杂节点连线、不生成大段蓝图逻辑、不自动放入关卡、不自动保存包。
- `create_blueprint_event_stub` 仅允许 `BeginPlay / Tick / ActorBeginOverlap / ActorEndOverlap`。
- 变量类型只允许常见内置类型、短别名，或 `/Script/`、`/Game/` 开头的项目/引擎类型。
- `/api/v1/editor-operations/results` 的 `result` 是开放对象，后端接受 `applied_fields`、`failed_fields`、`dirty_packages`、`graph_name`、`created_nodes`、`save_policy` 等 UE 侧回传字段；`dirty_packages` 建议传字符串数组，当前不强制固定为某一种 package path 格式。
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
docs/code-review-benchmark-report.md
storage/artifacts/evals/code-review-benchmark-latest.json
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

## 29. Optional MCP Stdio Client v1

后端现在有最小 MCP stdio client。它仍是可选工具层，不是 UE 前端主通信协议，也不会替代现有 HTTP API。

### 默认行为

- `MCP_TOOL_ADAPTER_ENABLED=false` 时完全关闭。
- 后端启动和健康检查不会自动拉起外部 MCP server。
- `MCP_AUTO_DISCOVER_ON_STARTUP=false` 默认关闭，避免启动时产生不可控外部进程。
- 只有显式调用 `/api/v1/mcp/tools` 或 `/api/v1/mcp/tools/{tool_name}/call` 时才会尝试启动配置的 stdio server。

### 配置

```env
MCP_TOOL_ADAPTER_ENABLED=true
MCP_STDIO_COMMAND=python
MCP_STDIO_ARGS=D:/Path/To/your_mcp_server.py
MCP_ALLOWED_TOOLS=get_widget_tree,get_target_umg_asset
MCP_STDIO_TIMEOUT_MS=5000
MCP_AUTO_DISCOVER_ON_STARTUP=false
```

`MCP_ALLOWED_TOOLS` 是强制安全边界。未在白名单内的工具会在后端调用 MCP server 前被拦截。

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

- 不实现 MCP server。
- 不打包或依赖 UMG-MCP。
- 不把 MCP 工具自动注册进 Agent Chat。
- 不允许 LLM 自动调用未知 MCP 写入工具。
- 写入类 MCP 工具未来也必须先转成 Editor Operation Proposal，由用户确认后再由 UE 前端执行。

### 项目表达

可以这样说明：项目主体是自研 HTTP Agent backend，MCP 是可选工具 transport。这样既能保持当前 UE 前端简单稳定，又为后续接入外部工具生态留下接口，而不是把整个项目绑定到某个 MCP 实现。
## 2026-05-10 后端连通性与 smoke test 补充

当前后端增加了几项内部可维护性补强：RAG 统一 facade、Workflow 可复用节点、轻量 ingestion job queue，以及 LLM fallback 的结构化标记。这些改动不改变 UE 前端已有主接口，也不要求前端 UI 立即调整。

本地验证建议优先查看：

- `docs/integration-smoke-tests.md`：7 条最小端到端 HTTP smoke test。
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
- `debug_view.web_memory`
- `debug_view.web_memory_store`
- `data.retrieval_quality_gate.web_memory_retrieved_count`
- `data.source_arbitration.source_counts.web_memory`

### Web Memory FTS5 召回

`WEB_MEMORY_FTS_ENABLED=true` 时，SQLite 环境会尝试创建本地 FTS5 虚拟表，用于对已缓存的 Web Search 摘要做全文召回。它只索引 `entry_id/title/domain/snippet`，不保存网页全文，也不会写入正式知识库。

兼容边界：

- 如果当前 SQLite 不支持 FTS5，后端自动回退到原来的 Python token 召回。
- 如果 FTS5 对中文或特殊查询没有命中，后端也会回退到 Python token 召回。
- `data.web_memory.summary.search_mode` 会显示 `sqlite_fts5`、`python_token_fallback` 或 `python_token`。
- `data.web_memory.summary.fts5` 会显示是否启用、是否命中、同步/搜索诊断。
- UE 前端不需要修改；这些字段主要给 Debug View 和后端调试使用。

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
- `TaskService` now keeps lifecycle, persistence, routing dispatch, context helpers, tool-plan helpers, Proposal helpers, and guarded file/inventory helper methods.

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
- Owns common context, routing, tool-plan, and safety helper methods.
- Delegates concrete task execution to `RouteExecutionDispatcher` and `app/services/task_handlers/*`.
- No longer owns feature-specific execution methods except shared helper methods used by handlers.

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
