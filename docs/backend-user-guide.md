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
  - 规则问题
  - 重命名建议
  - 资产类型
  - 关系摘要
  - 参考规则摘要

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

### KB 不足时的审查策略

如果项目知识库没有命中足够证据，Code Review 仍会基于当前文件内容和通用 Unreal/C++/C# 规则给出结果，并在 `references` 块中明确说明“仅供参考”。这能避免前端看到空洞总结，也能帮助用户知道下一步应补充哪些项目规范。
