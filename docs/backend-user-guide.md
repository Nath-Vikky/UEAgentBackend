# UE Agent Backend User Guide

## 1. 项目定位

这个后端服务配合 Unreal Editor 插件使用，定位是本地单机作品集项目。它不追求企业级部署和过宽的功能面，而是收口到 5 个核心能力：

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

边界：

- 不直接写用户工程
- 不自动 patch 文件
- 不做 compile / build 验证
- 代码参考增强已经落地，但结果仍然是“建议草稿”而不是执行器

### 4.4 Logs Analyze

现在支持：

- 传入 `log_text`
- 可选传入 `log_source`、`time_range`、`line_window`
- 返回结构化事件、问题类型、建议动作
- `user_view` 已按日志面板形态输出：
  - 摘要
  - 问题类型
  - 建议动作
  - 日志窗口信息
  - 模块 / 资源线索

边界：

- 日志采集应由插件或本地脚本负责
- 后端只分析文本，不直接接管 Unreal Editor 日志面板

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
KB_SOURCE_PATHS=../backend.md,../forward.md,./docs,../knowledge
KB_DIR=./storage/kb
KB_MAX_FILE_BYTES=5000000
KB_CHUNK_SIZE=600
KB_CHUNK_OVERLAP=100
```

启动后调用：

```http
POST /api/v1/knowledge-base/refresh
```

请求体可以为空，此时使用 `KB_SOURCE_PATHS`。如果只想刷新指定路径：

```json
{
  "source_paths": [
    "../knowledge/project_docs",
    "../knowledge/code_reference"
  ],
  "force_rebuild": false
}
```

如果要彻底重建本地知识库：

```json
{
  "source_paths": [
    "../knowledge"
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
- 本地作品集演示：`RAG_MODE=hybrid`，`EMBEDDING_ENABLED=true`，接入 Qdrant
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
- 后端接收日志文本后做模式识别和 LLM 分析
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
