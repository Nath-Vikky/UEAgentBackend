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

### 17.14 UE 官方文档补充到知识库的合规做法

推荐只补充公开可访问的 Epic / Unreal Engine 官方文档页面，并且把它们当作本地 RAG 检索资料，而不是训练数据。

当前可执行原则：

- 只抓取公开文档页，优先 `https://dev.epicgames.com/documentation/` 下的 Unreal Engine 文档。
- 不抓取登录、搜索、账户、过滤器、portal 一类页面；`https://dev.epicgames.com/robots.txt` 当前明确限制了这些路径，并提供了文档 sitemap。
- 不把抓取到的 Epic 内容用于模型训练、微调或任何“模型会从输入继续学习”的流程。保持在本地知识库检索、引用和摘要范围内即可。
- 控制抓取频率，保留原始来源 URL、标题和抓取时间，便于后续删除或更新。
- 对作品集项目，优先使用“官方文档摘要 + 原始链接”方式入库；不要把整站镜像直接塞进仓库。

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
- `source_kind = "query_only"` 或 `llm_analysis.reason_code = "missing_selected_code_content"`：请求缺少可解析的选中文件内容，通常需要前端补齐 `payload.project_root + payload.file_path`。
- `llm_review.reason = "completed_text_fallback"`：LLM 已返回内容但未严格按 JSON schema 返回，后端会尽量修复常见 JSON-like 格式；如果仍不合法，也会尝试从原文提取 summary / issue / suggestion 放入 `llm_analysis.text`，状态仍是 `completed`。

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
- 面试演示或排查“为什么这次走 RAG / 为什么没走 RAG / 为什么 LLM skipped”时，优先看这里。

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
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --dataset tests\eval\rag_project_qa_dataset.jsonl
```

评测 summary 会包含：

- `recall_at_k`
- `precision_at_k`
- `hit_at_k`
- `mrr`
- `ndcg_at_k`
- `route_accuracy`
- `language_accuracy`
- `citation_coverage`
- `low_confidence_ratio`
- `no_result_ratio`

### 18.13 Skill Protocol v1

后端现在把 5 个核心能力收敛成固定内置 Skill，而不是动态插件市场：

- `ProjectQASkill`：Agent Chat / Project QA，自由聊天、项目问答、知识库检索、Project Inventory 查询都从这里进入。
- `CodeReviewSkill`：代码审查，负责 UE 工程源码扫描、选中文件读取、规则检查、KB 证据和可选 LLM 分析。
- `CodeGenerateSkill`：代码生成，负责根据需求和 `code_reference/examples/engine_notes` 生成代码草案。
- `LogsAnalyzeSkill`：日志分析，负责日志文本提取、严重性归类、签名识别和建议生成。
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
- 不做动态安装 Skill、不做 marketplace、不做复杂沙箱；这是个人作品级、面试展示级项目，目标是稳定、清晰、可讲。

### 18.14 学习文档入口

如果要系统复习这个后端，可以按下面顺序阅读：

- `docs/agent-architecture-study.md`：先理解整体 Agent loop、模块边界和面试讲法。
- `docs/request-lifecycle.md`：再用真实请求复盘 Agent Chat、Project QA、Code Review 等路径。
- `docs/rag-and-memory-study.md`：理解知识库、检索、向量模型、Qdrant 和上下文压缩。
- `docs/skill-development-guide.md`：最后看后续如何扩展固定内置 Skill。

这些文档不要求 UE 前端实现新 UI，主要用于后端学习、复盘和作品集展示。
