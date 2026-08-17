# UEAgentCraft Backend

UEAgentCraft Backend 是一个面向虚幻引擎研发场景的本地 AI Agent 后端，配合 UE 编辑器插件使用：

https://github.com/Nath-Vikky/UEAgentTool

它不是简单的 LLM 转发层，而是把意图路由、上下文管理、知识检索、工具调用、编辑器操作提案、安全校验、观测指标和离线评测串成一条完整的 Agent 管线。后端负责推理、检索、计划和校验；UE 插件负责编辑器 UI、上下文采集、用户确认和真实 Editor API 执行。

## 核心功能

- `Agent Chat / Project QA`：结合当前 UE 上下文、项目清单、知识库和只读工具回答项目问题。
- `Code Review`：审查 UE C++ 文件，支持确定性规则检测、LLM 总结和修复建议。
- `Code Generate`：根据用户需求和知识库参考生成 UE C++ 草稿，并执行轻量 preflight 检查。
- `Logs Analyze`：分析粘贴日志片段或日志文件路径，提取错误原因和排查建议。
- `Assets Inspect`：分析选中资产的命名、类型、引用关系和常见 UE 设置。
- `Editor Operation Proposal`：为资产、蓝图、UMG、材质、关卡 Actor 等编辑器操作生成需要用户确认的提案。
- `Project Inventory / Active Context`：接收 UE 插件同步的项目清单和当前编辑器上下文，让 Agent 能理解“这个资产”“当前蓝图”“选中的 Actor”等指代。
- `Evaluation`：提供离线路由、RAG、代码审查、幻觉守卫和编辑器操作 smoke 测试脚本。

## 架构概览

```text
Unreal Editor Plugin
  -> FastAPI API
  -> Intent Router / Context Resolver
  -> Agent Turn Context / Memory / Context Budget
  -> Tool Plan / Permission Gate
  -> Skill Executors / Workflow Orchestrator
  -> Tool Registry / MCP Adapter / Editor Operation Proposal
  -> Knowledge Base / Lexical Search / Optional Vector Search
  -> Response Synthesizer / Response Critic
  -> SQLite / Artifacts / Metrics / Evaluation Reports
```

每次请求都会构建一份 `AgentTurnContext`，包括用户输入、会话摘要、UE 当前选择、Project Inventory 状态、知识库命中、工具可用性和上下文预算。工具执行前会经过权限判断：只读工具可以自动执行，计划类工具只生成方案，写入类编辑器操作必须变成用户确认的 Proposal。

## 目录结构

- `app/api/`：聊天、任务、知识库、系统状态、项目清单、编辑器操作等 HTTP 接口。
- `app/agent/`：Agent 上下文、意图草案、上下文解析、工具计划、响应校验和轻量多节点运行状态。
- `app/services/`：任务编排、会话、知识库、项目清单、编辑器操作提案、指标和工作流服务。
- `app/skills/`：面向用户功能的 Skill，例如代码审查、代码生成、日志分析、资产检查和项目问答。
- `app/tools/`：声明式 Tool Registry、工具契约、搜索工具、项目文件读取和可选 MCP adapter。
- `knowledge/`：公开 UE 知识库，供本地词法检索和可选向量检索使用。
- `tests/`：unit、contract、eval、integration 测试。
- `scripts/`：评测、smoke、导出工具目录和维护脚本。

## 快速启动

在后端仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```http
GET http://127.0.0.1:8000/api/v1/system/health
```

OpenAPI 文档：

```text
http://127.0.0.1:8000/docs
```

UE 插件默认连接地址：

```text
http://127.0.0.1:8000
```

## 最小配置

复制 `.env.example` 为 `.env`，至少配置 LLM：

```env
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=
CHAT_MODEL=gpt-4.1-mini
```

默认不需要向量数据库，知识库会走本地词法检索：

```env
KB_SOURCE_PATHS=./knowledge
EMBEDDING_ENABLED=false
RAG_MODE=hybrid
RAG_FALLBACK_MODE=lexical_only
AGENT_GRAPH_FRAMEWORK=framework_neutral
AGENT_INTENT_DRAFTER_MODE=active
LOCAL_MEMORY_ENABLED=false
LOCAL_MEMORY_ROOT=./runtime/memory
```

如果需要接入向量检索，可以再启用：

```env
EMBEDDING_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-large
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=ue_agent_default
```

## 知识库

公开知识库位于 `knowledge/`，建议使用 Markdown 编写。它同时服务于本地 lexical 检索和可选 vector 检索。

常用接口：

```http
GET  /api/v1/knowledge-base/status
POST /api/v1/knowledge-base/reindex
GET  /api/v1/knowledge-base/documents
```

如果要接入自己的本地私有资料，可以扩展 `.env`：

```env
KB_SOURCE_PATHS=./knowledge,../YourPrivateUENotes/knowledge
```

私有资料和第三方全文资料建议只保留在本地，不提交到公开仓库。

## 编辑器操作安全链路

写入类编辑器操作不会由后端直接修改 UE 工程，而是生成 Proposal：

```text
Agent 判断意图
  -> 后端生成编辑器操作提案
  -> UE 插件展示预览
  -> 用户确认或拒绝
  -> UE 插件通过 Editor API 执行
  -> 后端记录执行结果摘要
```

当前编辑器操作目录：

- [Editor Operation Catalog](./docs/editor-operation-catalog.md)
- `GET /api/v1/editor-operations/capabilities`
- `GET /api/v1/editor-operations/workflows/templates`
- `POST /api/v1/editor-operations/workflows/plan`
- `POST /api/v1/editor-operations/workflows/steps/proposal`
- `POST /api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal`
- `POST /api/v1/chat/runs`
- `GET /api/v1/mcp/tool-registry/manifest`
- `GET /api/v1/mcp/tool-providers`
- `POST /api/v1/mcp/tool-registry/proposals/prepare`
- `POST /api/v1/mcp/tool-registry/proposals`

可选 MCP/TCP sensing 用于读取编辑器现场信息，例如选中资产、当前关卡 Actor、Blueprint Graph、Widget Tree、Material Instance 参数和 focused detail。写操作仍然走 HTTP Proposal 确认链路。

如需重新生成公开目录：

```powershell
.\.venv\Scripts\python.exe scripts\export_editor_operation_catalog.py --output docs\editor-operation-catalog.md
.\.venv\Scripts\python.exe scripts\export_tool_manifest.py --output storage\artifacts\tool-registry-manifest.json
```

## 本地验证

快速检查：

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q
```

完整验证可以按需执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\eval tests\integration
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output storage\artifacts\evals\project-benchmark-latest.md
.\.venv\Scripts\python.exe scripts\run_code_review_benchmark.py --min-recall 0.85 --min-precision 0.85
.\.venv\Scripts\python.exe scripts\run_blueprint_graph_operation_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_workflow_materialization_smoke.py
.\.venv\Scripts\python.exe scripts\run_project_inventory_chat_smoke.py
.\.venv\Scripts\python.exe scripts\run_agent_decision_eval.py --output storage\artifacts\evals\agent-decision-eval-latest.json
```

评测报告默认生成到 `storage/artifacts/`，通常不作为公开文档提交。

## 公开文档

- [User Guide](./docs/backend-user-guide.md)
- [Architecture](./docs/architecture.md)
- [Editor Operation Catalog](./docs/editor-operation-catalog.md)
- [Demo Checklist](./docs/demo-checklist.md)
- [FAQ](./docs/faq.md)
- [Release Notes](./docs/release-notes/)
- [Latest Release Note](./docs/release-notes/v0.2.0.md)
- [Contributing Guide](./CONTRIBUTING.md)
