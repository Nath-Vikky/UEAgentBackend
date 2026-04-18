# 知识库导入与检索说明文档

本文档说明 Phase 2 已落地的知识库导入、切片、元数据和检索路径。

## 支持的输入来源

- 文件
- 目录
- 内联文本

## 当前支持的格式

- `md`
- `txt`
- `html`
- `json`
- `csv`
- `pdf`
- `docx`

## 导入接口

- `GET /api/v1/knowledge-base/status`
- `POST /api/v1/knowledge-base/refresh`
- `POST /api/v1/knowledge-base/import`
- `GET /api/v1/knowledge-base/import-jobs/{job_id}`

## 导入管线

1. 发现知识源
2. 解析文档
3. 清洗文本
4. 切片
5. 生成 metadata
6. 持久化 `kb_documents` 与 `kb_chunks`
7. 项目问答时走检索与 citation 生成

## 解析策略

- 优先 `Docling`
- 失败时回退 `Unstructured`
- 对 `md/txt/html/json/csv` 使用 builtin 文本解析

补充说明：

- 当前代码路径始终保留 `Unstructured` fallback
- 但在 Python 3.13 开发环境下，依赖安装默认会跳过 `unstructured`
- 因此若要完整验证第二层 fallback，建议使用 Python 3.12

## 切片策略

- 默认 `KB_CHUNK_SIZE=600`
- 默认 `KB_CHUNK_OVERLAP=100`
- 章节标题会尽量进入 `section_path`

## 元数据字段

| 字段 | 说明 |
|---|---|
| `doc_id` | 文档 ID |
| `chunk_id` | 切片 ID |
| `source_path` | 原始来源 |
| `source_type` | `file` / `text` |
| `domain` | 知识域 |
| `title` | 文档标题 |
| `section_path` | 章节路径 |
| `language` | `zh-CN` / `en-US` |
| `doc_type` | `reference` / `schema` / `manual` |
| `module` | 预留 UE 模块字段 |
| `token_count` | 切片 token 估算值 |

## 知识域划分

当前至少覆盖：

- `project_docs`
- `config_schema`
- `incident_history`
- `perf_notes`
- `asset_rules`
- `team_rules`
- `engine_notes`
- `examples`

当前实现采用“路径 / 文件名优先”的分类策略，避免项目主文档因为正文里出现“规范”等字样被误判。

## 检索路径

项目问答当前走：

`language detect -> intent classify -> filter build -> lexical / local hybrid retrieval -> rerank -> answer compose -> citations`

## 当前返回的关键字段

- `data.sources`
- `data.confidence`
- `data.retrieved_docs`
- `data.filters_applied`
- `data.citations`
- `retrieval_trace.mode`
- `retrieval_trace.degraded_mode`
- `retrieval_trace.reason`

## 当前限制

- 远端 Qdrant 向量索引尚未在测试环境强依赖
- `reindex`、文档列表和文档删除接口仍待后续阶段补齐
- rerank 仍是轻量本地重排，不是外部模型重排
