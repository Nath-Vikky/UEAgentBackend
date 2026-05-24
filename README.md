# UEAgentCraft Backend

UEAgentCraft Backend 是一个面向 Unreal Editor 研发场景的本地 AI Agent 后端，配合 UE 编辑器插件使用：
https://github.com/Nath-Vikky/UEAgentTool

它不是简单的 LLM 转发层，而是把意图路由、上下文组织、知识检索、工具调用、编辑器操作提案、安全校验、可观测和离线评测串成一条完整 Agent 管线。

## 核心功能

- `Agent Chat / Project QA`：结合项目快照、知识库和只读工具回答 UE 项目问题。
- `Code Review`：审查 UE C++ 文件，包含确定性规则检测和可选 LLM 总结。
- `Code Generate`：根据用户需求和知识库参考生成 UE C++ 草稿，并做轻量 preflight。
- `Logs Analyze`：分析粘贴日志片段或日志文件路径。
- `Assets Inspect`：分析选中资产的命名、类型、引用关系和常见 UE 设置。
- `Editor Operation Proposal`：为 UE 插件生成需要用户确认的编辑器操作提案，例如资产改名、资产移动、Static Mesh 设置、Blueprint 创建、基础 Blueprint/UMG 操作等。

## 架构概览

```text
Unreal Editor Plugin
  -> FastAPI API
  -> Intent Router / Context Builder
  -> Skill Executors / Workflow Orchestrator
  -> Tool Registry / Editor Operation Proposal
  -> Knowledge Base / Lexical Search / Optional Vector Search
  -> SQLite / Artifacts / Metrics / Evaluation Reports
```

主要目录：

- `app/api/`：聊天、任务、知识库、系统状态、项目清单、编辑器操作等 HTTP 接口。
- `app/services/`：任务编排、会话、知识库、项目清单、编辑器提案和指标服务。
- `app/skills/`：面向用户功能的 Skill，例如代码审查、代码生成、日志分析、资产检查和项目问答。
- `app/tools/`：声明式 Tool Registry、工具契约、项目文件读取、搜索工具和可选 MCP adapter。
- `knowledge/`：本地原创 UE 知识库，供 lexical 检索和可选向量检索使用。
- `tests/`、`scripts/`：回归测试、离线评测和 smoke 工具。

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

OpenAPI：

```text
http://127.0.0.1:8000/docs
```

UE 插件：

- 插件仓库：<https://github.com/Nath-Vikky/UEAgentTool>
- 后端默认监听：`http://127.0.0.1:8000`
- 插件侧只负责编辑器 UI、用户确认和真实 Editor API 执行；后端负责 Agent 管线、Proposal、知识库、评测和记录。

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
```

后续需要向量检索时再启用：

```env
EMBEDDING_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-large
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=ue_agent_default
```

## 知识库

公开知识库位于 `knowledge/`，使用 Markdown 编写。它会同时服务于本地 lexical 检索和可选 vector 检索。

常用接口：

```http
GET  /api/v1/knowledge-base/status
POST /api/v1/knowledge-base/reindex
GET  /api/v1/knowledge-base/documents
```

如果要接入自己的本地私有资料，可以在 `.env` 扩展 `KB_SOURCE_PATHS`：

```env
KB_SOURCE_PATHS=./knowledge,../YourPrivateUENotes/knowledge
```

私有资料和第三方全文资料建议只保留在本地，不提交到公开仓库。

## 编辑器操作安全链路

写入类编辑器操作会先生成 Proposal：

```text
Agent 判断意图
  -> 后端生成编辑器操作提案
  -> UE 插件展示预览
  -> 用户确认或拒绝
  -> UE 插件通过 Editor API 执行
  -> 后端记录执行结果摘要
```

后端负责推理、校验和记录，真正修改 UE 工程的动作由插件在用户确认后执行。

当前编辑器操作目录：

- [Editor Operation Catalog](./docs/editor-operation-catalog.md)
- `GET /api/v1/editor-operations/capabilities`
- `POST /api/v1/editor-operations/workflows/plan`
- `GET /api/v1/mcp/tool-registry/manifest`

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

更完整的本地验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\eval tests\integration
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output storage\artifacts\evals\project-benchmark-latest.md
.\.venv\Scripts\python.exe scripts\run_code_review_benchmark.py --min-recall 0.85 --min-precision 0.85
.\.venv\Scripts\python.exe scripts\run_blueprint_graph_operation_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py
```

评测报告默认生成到 `storage/artifacts/`，不作为公开文档提交。

## 公开文档

- [User Guide](./docs/backend-user-guide.md)
- [Editor Operation Catalog](./docs/editor-operation-catalog.md)
- [Demo Checklist](./docs/demo-checklist.md)
- [FAQ](./docs/faq.md)
- [Release Notes](./docs/release-notes/)
- [Latest Release Note](./docs/release-notes/v0.2.0.md)
- [Contributing Guide](./CONTRIBUTING.md)
