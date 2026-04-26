# RAG 与 Memory 学习文档

本文说明本项目如何建立知识库、如何接入向量模型和向量数据库，以及上下文记忆为什么需要压缩。

## 1. 知识库在项目里的作用

知识库负责回答“项目规则、引擎知识、代码参考、团队规范、历史说明”这类问题。它不负责直接读取 UE 当前工程资产；工程事实由 Project Inventory 负责。

适合进入知识库的内容：

- UE 官方文档中允许保存的摘录或用户手动整理笔记。
- 项目开发规范。
- 常见错误处理记录。
- 可复用代码示例。
- 团队资产命名规则。

不适合进入知识库的内容：

- 当前项目动态资产列表。
- 每次编辑器选中的资产。
- 超大源码全量镜像。
- 版权不清晰的整站爬取内容。

## 2. Ingestion Pipeline

知识库导入流程在 `app/rag/ingestion/*` 中：

```text
source path / uploaded text
  -> loader
  -> parser
  -> cleaner
  -> chunker
  -> dedup
  -> document / chunk records
  -> lexical index
  -> optional embedding
  -> optional Qdrant upsert
```

关键接口：

- `POST /api/v1/knowledge-base/refresh`
- `POST /api/v1/knowledge-base/import`
- `POST /api/v1/knowledge-base/reindex`
- `GET /api/v1/knowledge-base/status`
- `GET /api/v1/knowledge-base/documents`

常用文件类型：

- 第一阶段稳定支持：`.md`、`.txt`、`.html`、`.json`、`.csv`、`.ini`、`.cfg`、`.h`、`.hpp`、`.cpp`、`.cs`、`.py`
- 第二阶段增强支持：`.pdf`、`.docx`

PDF / DOCX 依赖可选解析库。没有安装依赖时，`status.parser_dependencies` 会提示能力缺口。

## 3. Chunk 和 Metadata

Chunk 是检索的基本单位。太大，召回不准；太小，缺少上下文。

Metadata 用来过滤和解释来源，常见字段：

- `domain`：`project_docs`、`engine_notes`、`code_reference`、`asset_rules`、`team_rules`、`examples`
- `source_path`
- `doc_type`
- `tags`
- `title`

推荐做法：

- 项目说明和 user guide 放 `project_docs`。
- UE 官方整理笔记放 `engine_notes`。
- 可复用代码文件放 `code_reference`。
- 资产命名规范放 `asset_rules`。
- 代码生成示例放 `examples`。

## 4. Lexical / Vector / Hybrid

### Lexical Retrieval

本地词法检索基于关键词和稀疏索引。优点是无需外部模型，启动成本低。缺点是语义泛化弱。

### Vector Retrieval

向量检索需要 embedding 模型，把 chunk 和 query 都转成向量，再在 Qdrant 中查相似度。优点是语义匹配更强。缺点是需要额外模型、向量库和索引。

### Hybrid Retrieval

Hybrid 会结合 lexical 和 vector，适合自然语言问题和专业名词混合的场景。当前项目以可用、可解释为优先，不引入复杂 reranker。

## 5. 只配置 LLM 时如何工作

如果只配置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `CHAT_MODEL`

没有配置 embedding 和 Qdrant，Project QA 仍可工作：

```json
{
  "status": "degraded",
  "lexical_ready": true,
  "embedding_ready": false,
  "vector_store_ready": false,
  "usable_for_project_qa": true
}
```

这表示系统使用 lexical-only 降级检索。它不是错误，只是语义召回能力弱一些。

## 6. 向量模型接入

环境变量：

```env
EMBEDDING_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-small
```

如果你的 embedding 服务和聊天模型使用同一个 OpenAI-compatible endpoint，通常继续使用：

```env
OPENAI_BASE_URL=...
OPENAI_API_KEY=...
```

如果后续需要拆分聊天模型和 embedding 模型，可以在下一阶段扩展为独立的 `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY`。当前版本为了个人项目边界，先不强制拆分。

## 7. Qdrant 接入

环境变量：

```env
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=ue_agent_kb
```

使用流程：

1. 启动 Qdrant。
2. 配置 embedding 和 Qdrant 环境变量。
3. 运行知识库刷新。
4. 查看 `/api/v1/knowledge-base/status` 的 `rag_readiness.vector_store_ready`。

如果 Qdrant 未启动，后端会降级，不会阻止整个服务启动。

## 8. 官方文档补充建议

合法合规的方式：

- 优先手动整理学习笔记，保存为 markdown 或 txt。
- 保存文档链接、标题、摘要和自己的理解，不整站镜像。
- 少量摘录时保留来源链接和访问日期。
- 不把受版权限制的大段原文直接导入仓库。

推荐目录：

```text
knowledge/
  engine-notes/
    ue-blueprint-notes.md
    ue-static-mesh-nanite-notes.md
  project-docs/
    rushba-architecture.md
  code-reference/
    actor-lifecycle-example.cpp
```

然后配置：

```env
KB_SOURCE_PATHS=knowledge/engine-notes;knowledge/project-docs;knowledge/code-reference
```

## 9. 本地 RAG 评测

命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --dataset tests\eval\rag_project_qa_dataset.jsonl
```

核心指标：

- `recall_at_k`：期望答案是否被召回。
- `precision_at_k`：召回结果有多少是相关的。
- `hit_at_k`：Top K 内是否命中。
- `mrr`：第一个正确结果排得有多靠前。
- `ndcg_at_k`：排序质量。
- `citation_coverage`：回答是否带引用。
- `no_result_ratio`：无结果比例。

个人项目里不用追求学术 benchmark，目标是能证明：导入的知识能被检索到，RAG 降级状态能解释清楚。

## 10. Memory 为什么需要压缩

LLM context window 有上限。如果把全部聊天历史、代码片段、资产 metadata 都塞进去，会出现：

- prompt 过长。
- 成本升高。
- 模型注意力分散。
- 旧信息挤掉当前问题。

本项目采用两层处理：

- `context_bundle_v1`：每轮请求前裁剪和组织上下文。
- `memory_summary_v1`：长会话后压缩旧消息。

当前边界：

- 不做跨项目长期用户画像。
- 不把工具任务完整结果写入聊天 history。
- 不用 LLM 自动总结 memory，先用 deterministic summary 保持稳定。

## 11. 排查入口

优先看：

- `debug_view.context_bundle`
- `debug_view.memory_summary`
- `debug_view.agent_decision_trace.decisions.retrieval_decision`
- `GET /api/v1/knowledge-base/status`
- `summary.rag_readiness`

常见问题：

- 回答“知识库没找到”：先看 `rag_readiness.indexed_chunks` 是否大于 0。
- 只接 LLM 没有向量：确认 `lexical_ready=true` 即可继续调试。
- RAG 命中不准：检查文档 domain、chunk 大小、metadata 和 query 表达。
- 聊天历史顺序不对：看 `/sessions/{session_id}/history`，不要用 task list 渲染聊天时间线。

## 12. RAG + Local Grep 双检索策略

本项目现在同时支持 RAG 和本地 grep 检索：

- RAG：适合项目说明、概念问答、自然语言解释和 citation。
- Local Grep：适合代码生成、代码参考、规则查找、类名/函数名/宏/API 精确命中。

策略：

- 文本问答有 embedding / Qdrant 时优先走 hybrid / vector RAG。
- 文本问答没有向量命中时，fallback 到 local grep。
- 代码生成无论是否接入向量，都优先把 local grep 命中的 `code_reference/examples/engine_notes` 片段交给 LLM。
- Code Review 先读选中文件并跑规则，再用 RAG/local grep 补充 `team_rules/engine_notes`。

本地搜索入口：

- `app/services/local_search_service.py`
- `debug_view.local_search`
- `summary.local_search_readiness`

本地知识目录：

```text
knowledge/
  engine-notes/
  project-docs/
  code-reference/
  examples/
  asset-rules/
  team-rules/
```

这个设计的目标不是替代向量数据库，而是在个人本地作品环境中保证“没有 embedding 也能稳定命中关键参考资料”。
