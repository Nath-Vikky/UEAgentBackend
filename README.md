# UE Agent Backend

面向 Unreal Editor 插件的本地 AI Agent 后端。项目定位是可本地运行、可调试、可评测、可接入 UE 研发场景的开源 Agent 工具链；当前不提供企业级云部署、多租户权限或复杂运维平台。

## 项目亮点

- **UE 研发场景闭环**：覆盖 `Agent Chat / Project QA`、`Code Review`、`Code Generate`、`Logs Analyze`、`Assets Inspect` 五个核心功能。
- **不是简单 LLM 转发**：后端负责意图路由、上下文压缩、知识检索、工具调用、结构化输出、调试轨迹和评测指标。
- **固定 Skill 架构**：每个显式功能由内置 Skill 执行，避免所有能力都交给 LLM 自由发挥。
- **声明式 Tool Registry**：工具有分类、输入输出契约、副作用等级、确认要求和 free-chat 白名单。
- **RAG + 本地 grep 并存**：没有向量模型时使用本地 lexical/grep 检索；配置 Embedding + Qdrant 后可扩展为混合检索。
- **Agentic RAG 轻量增强**：Project QA / Code Generate 在第一轮证据不足时最多再做 1 轮 query rewrite，并在 Debug View 暴露 `agentic_rag` 与 `retrieval_quality_gate`。
- **安全写入闭环**：代码生成默认只返回草稿，并先做轻量 UE C++ Preflight；只有显式请求并经 Proposal 确认后，才允许有限写入 `Source/` 或 `Plugins/`。
- **Editor Operation Bridge**：第一版 MCP-like 编辑器操作通过 Proposal 表达，支持从 Assets Inspect / Agent Chat 生成重命名资产、应用 Static Mesh 基础设置、创建 Blueprint 资产提案，真实执行必须由 UE 插件确认后完成。
- **可观测和可评测**：提供 `user_view / debug_view`、trace、artifact、Prometheus metrics、alerts、RAG eval 和项目级 benchmark。
- **可选 MCP 工具层**：HTTP 仍是 UE 前端和后端主协议，MCP 只作为未来工具 transport，默认关闭。

## 架构概览

```text
Unreal Editor Plugin
  -> FastAPI HTTP API
  -> Router / Context Manager / Skill Executors
  -> Tool Registry / ReAct Lite / Proposal Service
  -> Knowledge Base / Local Search / Optional Vector RAG
  -> SQLite Storage / Artifacts / Metrics / Eval Reports
```

核心设计边界：

- UE 插件负责采集编辑器上下文和展示结果。
- 后端负责 Agent 决策、检索、LLM 调用、工具协议、安全确认和评测。
- 自研 Agent pipeline 是主链路，`LangChain / LangGraph` 仅保留为可选依赖，不作为当前主工作流叙事。
- 写入类能力必须经过 `Proposal -> 用户确认 -> 后端安全校验 -> 执行记录`。

## 核心功能

| 功能 | 面向场景 | 当前边界 |
| --- | --- | --- |
| Agent Chat / Project QA | 自由聊天、项目事实问答、知识库问答、项目资产/代码清单查询 | 只允许自动调用只读工具 |
| Code Review | 扫描并审查 UE C++ / C# 文件 | 生成审查结果，不自动改源码 |
| Code Generate | 根据需求和知识库生成 UE 代码草稿，并附带轻量 Preflight | 默认不落盘，可选确认式写入 |
| Logs Analyze | 分析 UE 日志文本、错误片段或日志文件路径 | RAG 只作辅助，不覆盖日志本身判断 |
| Assets Inspect | 分析选中资产、命名、类型、依赖、常见设置 | 批量修改或重命名后续必须走 Proposal |

保留兼容但不作为主菜单功能：`config_generate`、`config_validate`、`assets_plan`、`assets_execute`、`perf_analyze`。

## 快速启动

在 `backend/` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果只是本地临时验证，不跑迁移通常也能启动，因为应用启动时会尝试 `create_all`。

首次准备环境可参考：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 最小配置

复制 `.env.example` 为 `.env` 后，最小 LLM 配置如下：

```env
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=
CHAT_MODEL=gpt-4.1-mini
```

如果修改了 `CHAT_MODEL` 后自由聊天仍显示旧模型或 LLM 未连接，重启后端即可让内置 `default` Runtime Profile 自动同步 `.env`。编辑器操作 Proposal 不依赖在线 LLM，所以模型不可用时仍可能正常生成并执行资产改名、Static Mesh 设置或 Blueprint 创建提案。

知识库默认使用：

```env
KB_SOURCE_PATHS=./knowledge
KB_DIR=./storage/kb
EMBEDDING_ENABLED=false
RAG_MODE=hybrid
RAG_FALLBACK_MODE=lexical_only
```

可选向量检索：

```env
EMBEDDING_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-large
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=ue_agent_default
```

可选 MCP 工具层，默认关闭：

```env
MCP_TOOL_ADAPTER_ENABLED=false
MCP_STDIO_COMMAND=
MCP_STDIO_ARGS=
MCP_ALLOWED_TOOLS=
MCP_AUTO_DISCOVER_ON_STARTUP=false
```

## 知识库使用

公开仓库只提交 `./knowledge` 中的原创蒸馏知识，例如 UE C++ 常用模式、资产检查规则、代码生成参考和团队规则。后端开发文档、交接文档、改进计划默认不进入用户知识库，避免 Agent Chat 引用内部过程资料。

刷新或重建索引：

```http
POST /api/v1/knowledge-base/reindex
```

本地私有全量资料可以只在 `.env` 中追加，不要提交资料本体：

```env
KB_SOURCE_PATHS=./knowledge,../XG-UE-Cpp-Course-Skill-main/knowledge,../TeamNotes/UE
```

扫描私有知识源覆盖情况：

```powershell
.\.venv\Scripts\python.exe scripts\scan_knowledge_sources.py --markdown-output storage\artifacts\private-kb-scan.md
```

这个脚本只统计路径、后缀、domain 和大小，不复制正文。

## 量化评估

生成本地 benchmark：

```powershell
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output docs\benchmark-report.md
```

默认 benchmark 只使用公开项目资料和 UE 知识库：`./README.md`、`./docs`、`./knowledge`。目录扫描会跳过本地过程文档，例如 `improveplan.md`、`frontend-unified-handoff.md`、`backend-dev-log.md`，避免评测和用户知识库被开发过程资料污染。

如果本机有 `make`：

```powershell
make benchmark
```

代码审查专项离线 benchmark（不需要 LLM / Qdrant）：

```powershell
.\.venv\Scripts\python.exe scripts\run_code_review_benchmark.py --min-recall 0.85 --min-precision 0.85
```

Agentic RAG A/B 对比（普通 RAG vs 最多 2 轮 query rewrite）：

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_agentic_ab.py --top-k 4 --max-hit-drop 0.0
```

该脚本会生成 `docs/rag-agentic-ab-report.md`，用于展示 Agentic RAG 是否提升检索指标，或至少证明没有造成回退。

幻觉守卫评测（证据不足时是否拒答、是否避免展开不存在的项目事实）：

```powershell
.\.venv\Scripts\python.exe scripts\run_hallucination_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --min-grounding-accuracy 1.0 --max-unsupported-answer-rate 0.0 --output storage\artifacts\evals\hallucination-guard-latest.json --markdown-output docs\hallucination-guard-report.md
```

报告包含：

- RAG：`recall_at_k`、`precision_at_k`、`normalized_precision_at_k`、`top1_accuracy`、`hit_at_k`、`mrr`、`citation_coverage`
- 路由：`route_accuracy`
- 任务：`success_rate`、`field_coverage`、`semantic_accuracy`
- 幻觉守卫：`grounding_accuracy`、`abstention_accuracy`、`unsupported_answer_rate`
- 性能：`p50_ms`、`p95_ms`
- Code Review 专项：`recall`、`precision`、`false_positive_rate`、`clean_case_accuracy`、多阶段链路耗时

读取本地评测报告：

```http
GET /api/v1/knowledge-base/eval/reports
GET /api/v1/knowledge-base/eval/reports/project-benchmark-latest.json
```

这两个接口只读，不会重新运行评测，适合 Debug View 或本地项目质量面板展示。

当前量化报告见 [docs/benchmark-report.md](./docs/benchmark-report.md)、[docs/hallucination-guard-report.md](./docs/hallucination-guard-report.md) 和 [docs/code-review-benchmark-report.md](./docs/code-review-benchmark-report.md)。

## 关键 API

系统能力：

- `GET /api/v1/system/health`
- `GET /api/v1/system/bootstrap`
- `GET /api/v1/system/capabilities`
- `GET /api/v1/system/runtime-profiles`
- `GET /api/v1/system/settings`
- `GET /api/v1/system/alerts`
- `GET /metrics`

聊天与任务：

- `POST /api/v1/chat/runs`
- `POST /api/v1/chat/runs/stream`
- `GET /api/v1/chat/runs/{run_id}`
- `GET /api/v1/chat/runs/{run_id}/events/stream`
- `POST /api/v1/tasks/project-qa`
- `POST /api/v1/tasks/code-review`
- `POST /api/v1/tasks/code-review/files`
- `POST /api/v1/tasks/code-generate`
- `POST /api/v1/tasks/logs-analyze`
- `POST /api/v1/tasks/assets-inspect`
- `GET /api/v1/tasks/recent`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/artifacts`

知识库：

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`
- `POST /api/v1/knowledge-base/import`
- `POST /api/v1/knowledge-base/reindex`
- `GET /api/v1/knowledge-base/documents`
- `GET /api/v1/knowledge-base/jobs/{job_id}`
- `POST /api/v1/knowledge-base/jobs/{job_id}/retry`
- `DELETE /api/v1/knowledge-base/documents/{doc_id}`
- `GET /api/v1/knowledge-base/eval/reports`

项目清单：

- `POST /api/v1/project-inventory/snapshot`
- `GET /api/v1/project-inventory/summary`
- `GET /api/v1/project-inventory/assets`
- `GET /api/v1/project-inventory/assets/{asset_id}`
- `GET /api/v1/project-inventory/code-files`
- `POST /api/v1/project-inventory/query`

`Project Inventory v2` 会保留 UE 插件提交的蓝图父类、组件、变量、函数、图表、Static Mesh 设置、代码文件类名等摘要。Agent Chat 会把最近快照和当前选中资产注入 Active Context，用于回答“当前项目有哪些蓝图资产”“这个蓝图有哪些组件/变量”“当前文件属于哪个模块”等项目事实问题。

编辑器操作：

- `GET /api/v1/editor-operations/capabilities`
- `POST /api/v1/editor-operations/proposals`
- `POST /api/v1/editor-operations/proposals/{proposal_id}/confirm`
- `POST /api/v1/editor-operations/proposals/{proposal_id}/reject`
- `POST /api/v1/editor-operations/results`

MCP 调试接口，默认关闭，仅用于本地验证可选工具层：

- `GET /api/v1/mcp/tools`
- `POST /api/v1/mcp/tools/{tool_name}/call`

当前后端支持资产改名、Static Mesh 基础设置、Blueprint 创建，以及 Blueprint Graph Automation v1 的三个 proposal 契约：添加变量、添加组件、创建基础事件 stub。所有写入都必须由 UE 前端确认并执行。

会话：

- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/history`
- `GET /api/v1/sessions/{session_id}/tasks`
- `POST /api/v1/sessions/{session_id}/clear`

## 本地验证

推荐先跑轻量验证：

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit tests\integration tests\contract tests\eval
```

如果本机有 `make`，可以使用统一 review 入口：

```powershell
make review
```

RAG smoke eval：

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --top-k 4 --min-hit-at-k 0.25 --min-route-accuracy 0.75 --output storage\artifacts\evals\local-rag-eval-smoke.json --markdown-output storage\artifacts\evals\local-rag-eval-smoke.md
```

幻觉守卫 eval：
```powershell
.\.venv\Scripts\python.exe scripts\run_hallucination_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --min-grounding-accuracy 1.0 --max-unsupported-answer-rate 0.0 --output storage\artifacts\evals\hallucination-guard-latest.json --markdown-output docs\hallucination-guard-report.md
```

Code Review benchmark：

```powershell
.\.venv\Scripts\python.exe scripts\run_code_review_benchmark.py --min-recall 0.85 --min-precision 0.85
```

GitHub Actions 当前只保留手动触发入口，不随 push 自动运行。日常验证以本地 Ruff、pytest 和 eval 为准。

## Docker 本地演示

```powershell
docker compose up --build
```

默认启动：

- `app`：http://127.0.0.1:8000
- `qdrant`：http://127.0.0.1:6333

Compose 默认 `EMBEDDING_ENABLED=false`，优先演示本地 lexical RAG。要测试向量模式时，再设置 `EMBEDDING_ENABLED=true` 并安装 rag extras。

## 文档入口

- [docs/backend-user-guide.md](./docs/backend-user-guide.md)：完整使用手册。
- [docs/integration-smoke-tests.md](./docs/integration-smoke-tests.md)：本地端到端 smoke test 请求示例。
- [docs/benchmark-report.md](./docs/benchmark-report.md)：当前量化评估结果。
- [docs/hallucination-guard-report.md](./docs/hallucination-guard-report.md)：证据不足与幻觉守卫评估结果。
- [docs/code-review-benchmark-report.md](./docs/code-review-benchmark-report.md)：代码审查专项量化结果。
- [docs/project-review-checklist.md](./docs/project-review-checklist.md)：项目收口、验证和交付检查清单。
- [docs/release-notes/v0.1.0.md](./docs/release-notes/v0.1.0.md)：`v0.1.0` 版本说明。

开发日志、改进计划、前端交接、学习笔记等过程文档默认保留在本地，并已加入 `.gitignore`，避免公开仓库首页被过程资料稀释。

## 项目边界

- 不做服务器部署、多租户、鉴权计费、企业监控平台。
- 不让 LLM 自动执行破坏性写入。
- 不把 UE 前端改成 MCP client，HTTP 仍是主链路。
- 不承诺覆盖所有 UE API，知识库按高频研发场景持续蒸馏。
- 不把外部课程或私有资料全文提交到公开仓库。

可以这样概括：这是一个面向 UE 研发管线的本地 Agent 后端，包含上下文、知识库、工具调用、安全确认、观测和评测的完整闭环，而不是单纯把聊天模型接进编辑器。
## Multi-Agent Code Review Chain

Code Review 保留默认单阶段审查，同时支持轻量链式 Agent：

- 触发方式：`POST /api/v1/tasks/code-review` 的 `payload.enable_multi_agent=true`，或 `payload.workflow_mode="review_fix_validate"`。
- 链路阶段：`Review -> Fix Draft -> Validate`。
- 安全边界：Generate 阶段只返回虚拟 `generated_items` 草案，不写入 UE 工程；如果未来要落盘，仍必须走独立的 `write_code_files` proposal 和用户确认。
- 返回字段：`data.multi_agent`、`debug_view.multi_agent`、`user_view.blocks[block_type="phase_result"]`。
- 默认行为：不传触发字段时，原 Code Review 接口和前端展示方式不变。

## Optional MCP Stdio Client

后端提供最小 MCP stdio client，用于本地连接只读 MCP server：

- 默认关闭，不会随启动拉起外部进程。
- 仅允许调用 `MCP_ALLOWED_TOOLS` 白名单中的工具。
- 调用入口是 `/api/v1/mcp/tools` 和 `/api/v1/mcp/tools/{tool_name}/call`。
- MCP 仍只是后端工具 transport；UE 前端和后端之间继续使用 HTTP。
