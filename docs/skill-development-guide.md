# Skill 开发指南

本文说明后续优化功能时如何扩展固定内置 Skill，避免把项目做成过度分散的接口集合。

## 1. Skill Protocol v1

当前协议：

```text
collector -> rules -> retrieval -> llm_analyzer -> projector
```

运行时字段：

- `debug_view.skill.protocol_version = "skill_protocol_v1"`
- `debug_view.skill.skill_id`
- `debug_view.skill.lifecycle.collector.status`
- `debug_view.skill.lifecycle.rules.status`
- `debug_view.skill.lifecycle.retrieval.status`
- `debug_view.skill.lifecycle.llm.status`
- `debug_view.skill.lifecycle.projector.status`

静态 manifest：

- `GET /api/v1/system/capabilities`
- `capabilities.skill_catalog[]`

## 2. 5 个固定内置 Skill

### ProjectQASkill

入口：`agent_chat` / `project_qa`

职责：

- 普通自由聊天。
- 判断是否需要知识库。
- 判断是否需要 Project Inventory。
- 输出聊天式结果和 citations。

### CodeReviewSkill

入口：`POST /api/v1/tasks/code-review`

职责：

- 扫描 UE 工程源码文件。
- 读取用户选中的 cpp/h/cs 等代码。
- 运行确定性审查规则。
- 检索代码规范或引擎笔记。
- 可选调用 LLM 做自然语言解释。
- 输出适合高亮按钮展示的 `user_view.blocks`。

### CodeGenerateSkill

入口：`POST /api/v1/tasks/code-generate`

职责：

- 接收用户需求。
- 优先检索 `code_reference` / `examples`。
- 有参考代码时结合需求改写。
- 无参考代码时生成草案。
- 不直接写入用户工程。

### LogsAnalyzeSkill

入口：`POST /api/v1/tasks/logs-analyze`

职责：

- 接收 UE 日志文本。
- 提取错误签名、严重等级和模块。
- 检索历史问题或引擎笔记。
- 输出摘要、原因和建议。

### AssetsInspectSkill

入口：`POST /api/v1/tasks/assets-inspect`

职责：

- 接收 UE 当前选中资产 metadata。
- 检查命名、类型、依赖、引用关系。
- 分析常见资产设置，例如 Blueprint 父类、Tick、StaticMesh Nanite、LOD、Collision、材质槽。
- 可选调用 LLM 生成更自然的分析说明。

## 3. 如何判断改哪一层

### Collector

负责“拿到输入事实”。

例子：

- Code Review 增加读取 `.Build.cs`。
- Assets Inspect 增加读取 Blueprint 组件列表。
- Logs Analyze 增加从前端传来的 editor log buffer。

判断标准：如果问题是“后端有没有拿到足够信息”，通常改 collector。

### Rules

负责不依赖 LLM 的确定性判断。

例子：

- `Tick` 中同步加载资源。
- 资产名仍是 `NewMap`。
- StaticMesh 没有碰撞或 LOD 信息。
- Blueprint 开启 Tick 但没有说明用途。

判断标准：如果可以用代码稳定判断，就先做 rule。

### Retrieval

负责查证据。

例子：

- Code Review 查 `code_reference` 和 `team_rules`。
- Code Generate 查 `examples`。
- Assets Inspect 查 `asset_rules`。
- Project QA 查 `project_docs` / `engine_notes`。

判断标准：如果需要“参考资料、规范、示例”，改 retrieval 或 KB domain。

### LLM Analyzer

负责把事实和证据综合成人话。

例子：

- Code Review 解释为什么某个写法在 UE 中有风险。
- Assets Inspect 总结资产依赖关系是否合理。
- Logs Analyze 判断错误最可能的根因。

判断标准：如果确定性规则能发现问题，但需要更好的解释和建议，改 llm_analyzer。

### Projector

负责输出给前端看的结构。

例子：

- Code Review 高亮按钮读 `user_view.blocks[block_type="llm_analysis"]`。
- Code Generate 把代码结果放成按钮或 tabs。
- Assets Inspect 把命名问题和关系摘要拆成卡片。

判断标准：如果后端数据是对的，但 UI 展示不舒服，先检查 projector。

## 4. 扩展 Code Review 示例

需求：希望检查 UE C++ 中 `Tick()` 里是否直接 `LoadObject`。

推荐改动：

- Collector：确保已读取选中文件内容，检查 `data.review_scope.read_status = "ok"`。
- Rules：在 `app/skills/executors/code_review.py` 增加 rule hit。
- Retrieval：可选查 `engine_notes` 或 `team_rules`。
- LLM Analyzer：把 rule hit 和代码片段传给 LLM。
- Projector：把问题放入 `user_view.blocks` 的 issues / recommendations。
- Tests：增加集成测试，断言 rule id、`llm_analysis`、用户可见 blocks。

不要做：

- 不要新增一个单独的 `tick-review` 主接口。
- 不要让前端直接传整段 JSON 到高亮弹窗。
- 不要把 raw LLM response 当用户展示字段。

## 5. 扩展 Assets Inspect 示例

需求：希望分析蓝图父类、Tick、组件、依赖关系。

推荐改动：

- Collector：要求 UE 前端在 `payload.asset_items[].settings/properties` 中传 `parent_class`、`tick_enabled`、`components`、`dependencies`、`referencers`。
- Rules：增加 Blueprint 专项检查。
- Retrieval：查 `asset_rules`。
- LLM Analyzer：对选中资产生成自然语言总结。
- Projector：输出 `summary`、`llm_analysis`、`issues`、`recommendations`、`relationship_summary`。

如果用户在自由聊天问“当前项目有哪些蓝图资产”，不要走 Assets Inspect。那是 ProjectQASkill 调用 Project Inventory 的场景。

## 6. 测试建议

每个 Skill 扩展至少覆盖：

- 输入不足时能返回明确 reason code。
- LLM 缺 API key 时能 skipped，但用户仍有 fallback 结果。
- LLM 返回非 JSON 文本时能安全兜底。
- `user_view` 不暴露 raw JSON。
- `debug_view.skill.lifecycle` 能反映 collector/rules/retrieval/llm/projector 状态。

常用命令：

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests --no-cache
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\unit -q
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\integration\test_system_and_tasks.py -q
```

## 7. 开发边界

当前阶段不要做：

- 用户动态安装 Skill。
- Skill marketplace。
- 多租户权限。
- 复杂权限沙箱。
- 自动修改 UE 工程文件。

当前阶段应该做：

- 把核心能力做稳定。
- 每个功能能降级、能解释、能测试。
- Debug View 能说清楚为什么用了某个工具、为什么跳过 LLM、为什么 RAG 没结果。
