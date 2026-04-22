# UE Agent 后端收缩方案与后续开发计划

## 当前状态（2026-04-21）

- 后端范围已经正式收口到 5 个核心功能：`Agent Chat / Project QA`、`Code Review`、`Code Generate`、`Logs Analyze`、`Assets Inspect`
- 后端平台层和 5 条主链路已完成当前收口验证
- 前端现在可以按统一交接文档集中调整 UI
- 当前保留的非阻塞边界：`events/stream` 仍是事件回放、`code_generate` 不直接写工程、`LangSmith / OTel` 仍是本地契约层

## 目标

这份计划用于把 UE Agent 项目从“功能很多但边界发散”的状态，收缩成适合个人作品集展示、联调和录屏演示的一版。

核心原则：

- 只保留能形成闭环的 5 个核心能力
- 延后或隐藏会明显拉宽产品边界的功能
- 后端保持本地单机作品集定位，不再按企业部署形态扩展
- UE 前端按任务类型做专用面板，不再把所有功能都做成同一种聊天 UI
- 所有功能继续保留 `user_view / debug_view` 双视图思路

## 正式产品范围

### 1. Code Review

目标：用户在 UE 插件中看到当前工程代码文件列表，选择一个文件后让 LLM 做单文件审查。

后端边界：

- 扫描工程代码文件并返回文件列表
- 接收用户选中的目标文件路径
- 只读方式读取文件内容
- 返回结构化审查结果、问题列表、风险等级和建议
- 不做全工程自动巡检
- 不自动修复或写回工程

推荐 UI：

- 文件搜索框
- 代码文件列表
- `Analyze Selected File` 按钮
- 下方结果区展示摘要、问题列表和风险分级

### 2. Code Generate

目标：用户输入需求后，后端先查知识库里是否有可参考的代码文件；有则结合参考生成，没有则直接由 LLM 生成草稿。

后端边界：

- 接收自然语言需求
- 先检索 `code_reference`、`examples`、`project_docs`
- 返回 `generated_items`
- 不直接写用户工程
- 不自动 patch 源码文件
- 不做 compile / build 验证

推荐 UI：

- 顶部需求输入框
- `Generate` 按钮
- 用户需求保留在时间线
- 生成结果以按钮 / Tab / 列表挂在需求下面
- 点击结果按钮后查看完整代码正文

### 3. Logs Analyze

目标：插件或本地脚本获取编辑器日志，用户可在日志面板中一键分析，也可复制到聊天入口继续追问。

后端边界：

- 接收 `log_text`
- 可接收 `log_source`、`time_range`、`line_window`
- 返回日志摘要、问题类型、建议动作、关键模块和资源线索
- 不直接监听 Unreal Editor 日志流
- 不负责日志文件发现与选择

推荐 UI：

- 日志预览区
- `Analyze Log` 按钮
- 结构化结果区
- 可选“发送到聊天”继续追问

### 4. Assets Inspect

目标：根据用户在编辑器中选中的资产，分析命名、类型和依赖关系。

后端边界：

- 接收前端从编辑器采集的资产元数据
- 支持 `asset_path`、`asset_type`、`package_path`、`dependencies`、`referencers`
- 输出规则问题、命名建议、类型说明和关系摘要
- 不解析 `.uasset` 二进制
- 不执行重命名、迁移或批量修改

推荐 UI：

- 当前选中资产列表
- `Inspect Selected Assets` 按钮
- 结果按“命名与规则、类型说明、依赖与关系摘要”分组显示

### 5. Agent Chat / Project QA

目标：保留唯一完整聊天入口，后端自主判断是普通聊天还是需要检索知识库的项目问答。

后端边界：

- 接收聊天消息和编辑器上下文
- 判断 `direct_answer` 或 `project_qa`
- 项目问答时触发知识库检索
- 返回 citations 和 debug 路由诊断
- 不替代 Code Review、Logs Analyze、Assets Inspect 的专用 UI

推荐 UI：

- 标准聊天时间线
- 底部固定输入框
- 回答中展示 citation/source 小卡片
- Debug View 可展开 route、retrieval、trace

## 延后或隐藏功能

以下功能不再作为本版主线能力：

- `config_generate`
- `config_validate`
- `perf_analyze`
- `assets_plan`
- `assets_execute`

处理方式：

- 后端代码暂时保留兼容
- 前端主菜单隐藏
- 不再为它们新增 UI 包装
- 不纳入作品集主流程讲解

## 后续开发环节

### 阶段 A：范围收口与契约冻结

状态：已完成。

输出：

- `system/capabilities` 收口
- 5 个核心功能清单
- 统一前端交接文档

### 阶段 B：输入链补齐

状态：已完成。

输出：

- Code Review 文件列表接口
- Code Generate 代码知识库参考链
- Logs Analyze 输入协议
- Assets Inspect richer metadata payload

### 阶段 C：核心功能精修

状态：已完成当前收口版验证。

输出：

- 单文件代码审查闭环
- 知识库增强代码生成闭环
- 日志分析结构化结果
- 资产检查关系摘要结果
- 更稳定的 Agent Chat / Project QA 分流

### 阶段 D：前端 UI 对齐

状态：可以开始。

目标：

- 前端不再套同一种界面模板
- 5 个功能使用各自匹配的 UI
- 保留统一 shell、上下文栏和 Debug View

### 阶段 E：文档、验收与展示

状态：进行中。

目标：

- 最终用户指南
- 最终前端交接文档
- 调试 checklist
- 作品集演示路径

## 插件整体 UI 样式总结

- 顶层保持统一 Agent shell
- 左侧或顶部保留 5 个核心入口
- 每个功能使用专用内容区
- Debug View 作为可折叠高级区域
- 普通用户优先看 `user_view`
- 开发调试再看 `debug_view`
- 只有 `Agent Chat / Project QA` 是完整聊天 UI
- Code Review、Logs Analyze、Assets Inspect 更像工具面板
- Code Generate 是“对话式需求输入 + 结构化代码结果区”

## 2026-04-21 UE 联调反馈处理状态

已按 UE 端反馈补齐以下后端问题：

- `Agent Chat / Project QA`：修复 LLM 路由复核成功后返回 `None` 导致 500 的问题，并为非法 JSON、空结果、LLM 失败增加降级保护。
- `Code Review`：文件扫描接口现在返回 `file_path`、`label`、`module_name`、`file_type`，并提供 `scan_diagnostics` 说明空结果原因。
- `Code Review`：选中文件审查会在调试信息中暴露绝对路径、读取状态、内容长度和应用的 focus。
- `Assets Inspect`：支持前端传入的 `asset_name`，对 `NewMap` 等默认/占位名做确定性命名 lint，并返回 reason / suggestion。
- `user_view.blocks`：核心结果块已向 `summary`、`issues`、`recommendations`、`references` 等稳定类型收敛。

后续前端可继续统一 UI 调整，但应优先按 `backend/docs/frontend-unified-handoff.md` 的第 11 节读取新增字段。

## 2026-04-21 二次联调优化状态

UE 端进一步指出两个体验问题：中文工作流下 Highlight 仍有英文自然语言，以及 Code Review 在知识库证据不足时输出不够完整。后端已做适度收敛优化：

- Code Review 的 `user_view.blocks` 固定输出 `summary/issues/recommendations/references/next_steps`。
- Code Review 没有 KB 命中时，会明确说明使用当前文件内容和通用 Unreal/C++/C# 规则 fallback，而不是返回空泛总结。
- Code Review 增加 `data.localized_review`，前端可直接使用本地化后的问题、建议、证据说明和下一步。
- Code Review 在 LLM 可用时尝试综合审查；LLM 不可用时不阻塞，仍返回确定性规则扫描结果。
- Assets Inspect 的 `issues` block 会本地化 `reason/suggestion`，中文环境下 `NewMap` 会显示中文原因和中文改名建议。

前端下一步只需要按统一交接文档消费 `user_view.blocks` 和 `data.localized_review`，不需要自己再拼自然语言审查结论。

## 2026-04-22 架构收缩决策：固定内置 Skill 与统一知识库导入

本轮继续收缩边界：后端不做“运行时任意安装/卸载技能”的复杂插件系统，而是采用固定内置 Skill 架构。这样更适合作品集项目，也能让前端 UI、后端 API、调试视图保持稳定。

### Function 优化方向：固定内置 Skill 架构

核心原则：
- 只保留 5 个用户可见能力：`ProjectQASkill`、`CodeReviewSkill`、`CodeGenerateSkill`、`LogsAnalyzeSkill`、`AssetsInspectSkill`
- 每个 Skill 内部可以继续拆成 `collector`、`rules`、`retrieval`、`llm`、`projector`，但不额外暴露成新的主功能入口
- `collector` 负责把 UE 编辑器、项目文件、日志、资产元数据整理成后端可消费的标准输入
- `rules` 负责确定性检查，保证 LLM 不可用时也能返回有价值结果
- `retrieval` 负责按需查询知识库，而不是所有请求都强制 RAG
- `llm` 负责自由回答、综合审查、生成代码、解释日志等自然语言推理
- `projector` 负责把内部结果收敛成稳定的 `user_view`、`debug_view`、`data` 字段，前端只消费这些稳定字段

代码审查的 UE 工程文件扫描决策：
- 扫描并读取 `.cpp`、`.h`、`.hpp`、`.cs` 等 UE 工程源码文件，不单独做成一个用户可见 Skill
- 它属于 `CodeReviewSkill` 的内部 `collector`
- 前端 UI 仍然只显示“文件列表 + 选择文件 + 发送审查”这一个工具面板
- 后端可以继续优化扫描规则、模块识别、文件读取安全、大小限制、编码识别，但这些都是 `CodeReviewSkill` 的内部实现

后续如果某个功能需要增强，优先在对应 Skill 内补充子能力，而不是新增主菜单。例如：
- 代码审查要支持 Build.cs 检查，就补到 `CodeReviewSkill.rules`
- 代码生成要支持项目代码示例参考，就补到 `CodeGenerateSkill.retrieval`
- 日志分析要支持 UE 日志分类，就补到 `LogsAnalyzeSkill.rules`
- 资产检查要支持命名规范表，就补到 `AssetsInspectSkill.rules`

### 知识库方向：统一 ingestion pipeline

知识库统一走一条导入链路：

`source paths / inline text -> loader -> parser -> cleaner -> chunker -> lexical index -> embedding -> vector store -> retrieval`

阶段边界：
- 第一阶段优先稳定支持文本、代码、HTML：`.md`、`.txt`、`.html`、`.json`、`.csv`、`.ini`、`.cfg`、`.h`、`.hpp`、`.hh`、`.inl`、`.c`、`.cc`、`.cpp`、`.cxx`、`.cs`、`.py`
- 第二阶段增强支持 PDF、DOCX：`.pdf`、`.docx`
- PDF/DOCX 依赖 `docling` 或 `unstructured` 等解析库，缺失依赖时不阻塞普通文本/code/html 导入
- 知识库文档会统一分类为 `project_docs`、`code_reference`、`asset_rules`、`engine_notes`、`team_rules`、`incident_history`、`perf_notes`、`config_schema`、`examples`
- 代码生成优先检索 `code_reference` / `examples`
- 项目问答优先检索 `project_docs` / `engine_notes` / `team_rules`
- 代码审查优先检索 `code_reference` / `team_rules` / `engine_notes`

推荐补充知识库的方式：
- UE 项目规则、命名规范、开发流程放入 `docs/` 或通过 `/api/v1/knowledge-base/import` 导入
- 可复用代码片段、示例类、插件 API 用法放入 `code_reference` 或 `examples`
- HTML 文档可直接导入，后端会清理标签并保留主要文本
- PDF/DOCX 适合导入外部手册，但应作为增强资料，不应成为基础调试链路的唯一来源

这个方向能让后端保持“Agent 项目”的基本结构：工具/技能负责采集与执行，知识库负责长期记忆，检索负责外部上下文，LLM 负责推理和表达，调试视图负责解释每一步为什么这么做。

## 2026-04-22 优化落地进度

已开始把上面的方向落到后端代码里，当前完成第一轮基础优化：

- 新增固定内置 Skill registry，集中描述 5 个核心 Skill 的 `collector`、`rules`、`retrieval_domains`、`projector_outputs`
- `system/capabilities` 新增 `skill_catalog`、`core_skill_ids`、`skill_architecture`
- `feature_catalog` 和 `ui_recommendations` 改为从 Skill registry 派生，减少能力清单分叉
- 修正 task type 到 primary tool 的映射，避免字典推导被辅助工具覆盖主工具
- 知识库导入能力集中到 ingestion capabilities，`status` 可以返回 pipeline、格式分组、解析依赖和知识域
- inline text 导入兼容 `content` / `text`，并保存 `metadata`、`tags`、`doc_type`
- 新增 `/api/v1/knowledge-base/jobs/{job_id}` 和 `/retry` 短路径，保留旧 `import-jobs` 路径兼容
- 新增 Skill runtime descriptor，每次任务响应会在 `debug_view.skill`、`data.skill`、`trace_summary.skill_id` 标记当前 Skill 与本次检索状态

已完成：

- 把 `CodeReviewSkill` 迁移到独立 executor
- 把 `CodeGenerateSkill` 迁移到独立 executor
- 把 `LogsAnalyzeSkill` 迁移到独立 executor
- 把 `AssetsInspectSkill` 迁移到独立 executor
- `debug_view.skill`、`data.skill`、`trace_summary.skill_id` 已覆盖核心任务响应

下一轮建议继续优化：

- 评估是否需要抽离 `ProjectQASkillExecutor`，但它与普通聊天、RAG 路由和上下文管理耦合较高，可暂缓
- 给 Code Generate 的前端结果区优先展示 `data.reference_lookup.sources` 和 `data.retrieved_references`，用于说明“命中了哪些代码参考”
- 给知识库补一个轻量管理 UI 契约：新增资料、刷新路径、查看失败原因、重建索引
- 视情况把聊天模型和 embedding 模型配置拆分为独立 provider 配置

## 2026-04-22 CodeReviewSkill Executor 进度

已完成第一步执行层抽离：

- 新增 `CodeReviewSkillExecutor`
- `TaskService._execute_code_review()` 改为委托 executor
- Code Review 原有响应契约保持不变
- 本地化 helper、推荐项生成、证据说明、下一步建议和 LLM prompt helper 已搬入 executor
- `TaskService` 对 Code Review 只保留 executor 创建和任务生命周期调度

后续迁移顺序建议：

- 第二步：已完成 `CodeGenerateSkillExecutor`
- 第三步：已完成 `LogsAnalyzeSkillExecutor` 和 `AssetsInspectSkillExecutor`
- 第四步：如果 executor 文件继续变大，再拆出 `projector.py` 和 `prompts.py`

## 2026-04-22 CodeGenerateSkill Executor 进度

已完成第二步执行层抽离：

- 新增 `CodeGenerateSkillExecutor`
- `TaskService._execute_code_generate_v2()` 改为委托 executor
- Code Generate 原有响应契约保持不变
- `data.generated_items`、`data.reference_lookup`、`data.retrieved_references`、`data.generation_mode` 继续保留
- `debug_view.skill.skill_id` 和 `trace_summary.skill_id` 会稳定显示 `CodeGenerateSkill`

下一步迁移顺序建议：

- 已完成 `LogsAnalyzeSkillExecutor`
- 已完成 `AssetsInspectSkillExecutor`
- 再视情况抽离 `ProjectQASkillExecutor`

## 2026-04-22 LogsAnalyzeSkill / AssetsInspectSkill Executor 进度

已完成剩余两个工具型 Skill 的执行层抽离：

- 新增 `LogsAnalyzeSkillExecutor`
- 新增 `AssetsInspectSkillExecutor`
- `TaskService._execute_logs_analyze()` 改为委托 executor
- `TaskService._execute_assets_inspect()` 改为委托 executor
- Logs Analyze 原有响应契约保持不变
- Assets Inspect 原有响应契约保持不变
- `debug_view.skill.skill_id` 和 `trace_summary.skill_id` 会稳定显示 `LogsAnalyzeSkill` 或 `AssetsInspectSkill`

当前迁移结论：

- 4 个工具型核心 Skill 已经进入独立 executor
- `ProjectQASkill` 暂时保留在 `TaskService`，后续如果要强化上下文压缩、RAG 策略或聊天记忆，再单独抽离更合适
