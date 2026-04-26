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

## 2026-04-23 功能体验增强计划：LLM 分析层与 Project Inventory

当前 5 个核心功能已经能形成闭环，但 Code Review 和 Assets Inspect 的用户体验仍偏“规则检查器”：能指出问题，却缺少更像 Agent 的综合解释、风险判断和优先级说明。下一轮优化优先补齐“人类可读的 LLM 分析层”，随后再建设项目级 Inventory，让自由聊天可以回答项目事实问题。

### 阶段 F：为工具型 Skill 增加 `llm_analysis`

目标：

- Code Review 除了 `summary/issues/recommendations/references/next_steps`，新增用户可见的 `llm_analysis` 块
- Assets Inspect 除了命名、类型和依赖规则结果，新增用户可见的 `llm_analysis` 块
- `llm_analysis` 用自然语言解释“为什么这些问题重要、哪些优先处理、哪些可能只是提示”
- LLM 不可用时不阻塞主结果，返回明确的 skipped / fallback 状态

推荐响应结构：

```json
{
  "block_type": "llm_analysis",
  "title": "LLM 综合分析",
  "text": "这段代码当前最值得注意的是 UObject 生命周期和同步加载路径，它们不一定马上报错，但在运行时或资产迁移后可能放大风险。",
  "data": {
    "status": "completed",
    "reason": null,
    "reason_code": null,
    "key_points": [],
    "priority": "medium"
  }
}
```

前端 UI 建议：

- 在 Code Review / Assets Inspect 结果区新增“LLM 分析结果”卡片
- 位置建议放在 `summary` 后、`issues` 前
- 如果 `status=skipped`，显示为轻提示，不要当作错误
- `reason` 给普通用户展示，`reason_code` 给前端和 Debug View 判断
- Debug View 继续展示完整 `data.llm_analysis` / `data.llm_review`

### 阶段 G：Project Inventory / 项目快照

目标：

- 后端提供统一的项目快照导入和查询能力
- UE 插件负责扫描编辑器内资产和工程代码元数据，再提交给后端
- 后端保存轻量 JSON inventory，不直接解析 `.uasset` 二进制
- Project QA 在自由聊天中可以按需检索 inventory，回答“工程里有哪些资产”“某个资产有哪些设置”“哪些 C++ 类属于某模块”等问题

建议接口：

- `POST /api/v1/project-inventory/snapshot`：导入一次完整或增量项目快照
- `GET /api/v1/project-inventory/summary`：查看资产/代码总览
- `GET /api/v1/project-inventory/assets`：按类型、路径、名称搜索资产
- `GET /api/v1/project-inventory/assets/{asset_id}`：查看单个资产详情
- `GET /api/v1/project-inventory/code-files`：查看代码文件索引
- `POST /api/v1/project-inventory/query`：给 Project QA / Debug View 使用的轻量查询入口

后端保存的数据边界：

- 资产路径、名称、类型、包路径
- 依赖、引用、标签、Asset Registry tag
- 资产关键设置的结构化摘要
- 代码文件路径、模块、类型、大小、最后修改时间、类名/符号摘要
- 快照时间、项目名、扫描来源、插件版本

后端不做的事情：

- 不直接读取或解析 `.uasset` 二进制
- 不替代 Unreal Editor 的 Asset Registry
- 不执行资产重命名、迁移、保存或批量修改
- 不保证所有引擎私有属性都能获取，只消费 UE 插件能安全导出的元数据

### 常见 UE 资产属性采集建议

`StaticMesh`：
- Nanite 是否启用
- LOD 数量与屏幕尺寸策略
- 三角面 / 顶点数量摘要
- 碰撞复杂度、简单碰撞是否存在
- Material slot 列表
- Lightmap UV、Lightmap resolution
- Distance Field / Virtual Shadow Map 相关标记

`SkeletalMesh`：
- Skeleton / PhysicsAsset 关联
- LOD 数量
- Morph Target 数量
- Cloth / Chaos cloth 相关标记
- 使用的 Animation Blueprint 或主要动画引用

`Blueprint` / `WidgetBlueprint`：
- Parent class
- Component 列表
- 是否启用 Tick
- Replication / NetLoad / NetAddressable 相关标记
- 暴露变量、接口、主要事件数量摘要
- Construction Script 是否复杂
- Widget 层级和绑定数量摘要

`Material` / `MaterialInstance`：
- Parent material
- Shading model
- Blend mode、Two Sided、Translucency 相关设置
- Texture / Scalar / Vector 参数摘要
- 使用的纹理数量
- 是否启用 Nanite 不兼容或高成本渲染特征的提示

`Texture`：
- 分辨率
- Compression settings
- sRGB
- Mip Gen Settings
- Texture Group / LOD Group
- Virtual Texture Streaming
- 是否 Power-of-two

`World` / `Map`：
- World Partition 是否启用
- Streaming Levels / Data Layers 摘要
- Actor 数量
- Lighting / Sky / PostProcess 关键对象摘要
- NavMesh、Landscape、Level Blueprint 是否存在

`NiagaraSystem` / 粒子：
- Emitter 数量
- CPU/GPU simulation
- Fixed Bounds 是否设置
- Renderer 类型
- 主要材质和纹理引用

`SoundCue` / `MetaSound`：
- Duration / Looping
- Attenuation
- Concurrency
- SoundClass / SoundSubmix
- 主要引用关系

`DataAsset` / `DataTable`：
- RowStruct / 数据类型
- Row count
- 关键字段摘要
- 引用的 GameplayTag / SoftObjectPath 数量

### 阶段 H：Project QA 接入 Inventory

目标：

- 用户在 Agent Chat 中问项目事实问题时，后端优先查询 Project Inventory
- 如果问题涉及规则、解释或做法，再结合知识库 RAG
- 如果问题只是普通聊天，不触发 Inventory 或 RAG

示例问题：

- “这个工程里有哪些 StaticMesh？”
- “有没有开启 Nanite 的网格体？”
- “BP_PlayerCharacter 的父类和组件有哪些？”
- “哪些材质是 Translucent？”
- “某个纹理是不是 sRGB，分辨率多大？”
- “这个地图里大概有哪些关键 Actor？”
- “Gameplay 模块下有哪些 C++ 文件？”

Project QA 的上下文优先级建议：

1. 显式选中资产 / 当前文件
2. Project Inventory 精确命中
3. 知识库 RAG
4. 普通 LLM 回答

这个方向能让后端更像真正的 Agent：不仅能执行固定工具，还能理解项目事实、调用长期知识、用 LLM 做人类可读的解释。

当前落地状态：

- 已新增 Project Inventory 快照、summary、assets、asset detail、code-files、query 接口
- 已最小接入 Agent Chat / Project QA
- Project QA 命中 Inventory 时会把结果放入 `data.inventory` 和 `debug_view.inventory`
- LLM 不可用时会返回基于 Inventory 的基础回答
- Snapshot 已支持 `snapshot_time`、`scan_diagnostics`、`code_files[].last_modified`
- Snapshot 响应已稳定返回 `status`、`summary.asset_count`、`summary.code_file_count`
- 下一步需要继续扩展 UE 前端的 Asset Registry / Editor API 采集质量，让 Inventory 覆盖更多常用资产属性

## 2026-04-24 本阶段收尾：会话恢复、Agent Chat Inventory 工具选择、LLM 稳定性

这一轮已完成当前已知问题的后端侧修复：

- Session History 不再整段重复写库，而是按增量合并；assistant 回复也会进入 `sessions/{id}/history`
- 会话恢复后，历史顺序以后端返回为准，稳定按 `created_at + message_id` 排序
- Agent Chat 会识别项目级资产、代码和元数据事实问题，并选择 `query_project_inventory`
- Project QA 执行层新增 `tool_plan`，纯项目事实查询可跳过知识库检索，直接查询 Project Inventory
- Assets Inspect 边界收回为“只检查选中资产”，不承担项目级资产盘点
- Code Review / Assets Inspect 的在线 LLM 综合分析已改为更紧凑 prompt，并单独提高 timeout、收紧 `max_tokens`

当前这几个问题的状态：

- 聊天历史恢复错序：已修复
- 自由聊天问“当前项目有哪些蓝图资产”却走到 Assets Inspect：已修复，改为 Agent Chat / Project QA 选择 `query_project_inventory`
- Code Review LLM 总是 skipped：已确认主因是 `request_failed` 超时，并已做后端稳定性优化

下一步保留项：

- 继续观察真实联调下 `request_failed` 是否仍高频，如果仍高，再按供应商特性拆分 chat/JSON 配置
- 如果要正式补 UE 官方文档，优先走“官方 URL 白名单 + 本地摘要/HTML 落盘 + refresh 导入”方案，不做全站镜像
- 继续扩展 UE 前端采集的资产属性覆盖面，尤其是 Blueprint / Material / Texture / World / Niagara

## 2026-04-24 二次排查收尾：Inventory 空结果、Code Review LLM 兜底

本轮继续围绕“功能可测、问题可定位”做收口，不扩展新主功能。

已完成：

- Agent Chat 对“我当前项目的蓝图资产有哪些，你列一下”“当前项目蓝图资产有哪些”等中文问法稳定选择 `query_project_inventory`
- Project Inventory 空结果不再空回复，新增 `data.inventory.summary.empty_reason`
- `empty_reason = "no_project_inventory_snapshot"` 时，明确提示先在 UE 插件 Debug View 提交 `Submit Inventory`
- 有明确 `project_id/project_name` 时不再 fallback 到其他项目的 latest snapshot，避免串项目
- Code Review 增加 `missing_selected_code_content`，用于区分“前端没提交可读文件内容”和“LLM 调用失败”
- LLM 返回普通文本但不是 JSON 时，Code Review / Assets Inspect 使用 `completed_text_fallback` 兜底为 `llm_analysis.status = "completed"`

当前判断：

- 前端暂不需要新增 UI，只需按现有 `llm_analysis`、`data.inventory`、`debug_view.route` 和 `review_scope` 渲染与排查
- 如果 Code Review 仍 skipped，先看 `data.review_scope.read_status/content_length/source_kind`，再看 `data.llm_review.reason/error`
- 如果 Agent Chat 项目资产问题无结果，先看 `data.inventory.summary.has_snapshot` 和 `empty_reason`

## 2026-04-24 Code Review 高亮展示收口

问题：Code Review 面板没有聊天框，前端通过高亮按钮查看 LLM 回答、建议和概要；联调中发现高亮内容变成完整 JSON。

判断：

- 后端应保证用户展示字段是自然语言，Debug/raw 字段才允许保留完整 JSON
- 前端高亮按钮应读取 `user_view.blocks[].text`、`user_view.blocks[].data.items` 或 `data.localized_review`
- 不应读取 `data.llm_review`、`debug_view.raw_result`、artifact 原始内容或源码 excerpt 作为普通用户弹窗内容

已完成：

- Code Review LLM payload 展示层归一化，嵌套 dict/list 不再直接 `str()` 成 JSON-like 文本
- `completed_text_fallback` 会尝试从 JSON-like 原始文本提取概要、问题和建议
- 原始 LLM 文本继续保留在 `data.llm_review.text`，仅用于 Debug View
- 文档明确高亮按钮的推荐字段和禁止字段

前端是否需要改：

- 接口和编辑器采集项暂不需要改
- 如果当前高亮按钮仍显示 JSON，需要前端把数据源切回 `user_view.blocks` 或 `data.localized_review`
- Code Review 仍需稳定提交 `payload.project_root`、`payload.file_path`、`payload.source_roots`，以及 `context.current_file/current_module`

## 2026-04-24 语言偏好统一控制计划

目标：让后端所有用户可见输出都遵循用户选择的语言。UE 插件前端提供 `中文 / English` 切换按钮，默认中文；后端负责把语言偏好应用到 Agent Chat、Project QA 和 4 个工具型 Skill 的自然语言输出。

策略：

- 前端默认传 `runtime_options.preferred_output_language = "zh-CN"`
- 用户切换英文时传 `runtime_options.preferred_output_language = "en-US"`
- 后端会把显式语言偏好写入 session，后续请求可继续沿用
- `auto` 不再默认跟随用户输入语言，而是按 `session preference -> editor locale -> zh-CN` 决定
- 用户在消息中明确说“用英文回答 / 用中文回答”时，仍可作为单次显式覆盖

边界：

- `user_view.title/text`、`user_view.blocks[].title/text`、`assistant_message`、`reason/suggestion`、LLM prompt 的语言都要跟随最终语言
- Debug View、API 字段名、枚举、文件路径、代码符号和 raw JSON 保持英文或原文
- 当前先支持 `zh-CN` 和 `en-US`，后续如需日文/韩文再扩展枚举

前端影响：

- 需要新增语言切换按钮，并把选择保存到 UE 插件本地配置
- 每次请求都带上 `runtime_options.preferred_output_language`
- 启动/恢复 session 时可调用 `POST /api/v1/sessions` 同步 `preferred_output_language`

完成状态：

- 后端已新增统一语言工具模块，支持 `zh-CN/en-US/auto` 标准化
- `classify_request()` 已改为 `message override -> runtime preference -> session preference -> editor locale -> zh-CN`
- `auto` 不再跟随用户输入语言，英文问题默认仍按中文输出，除非前端按钮或 session 指定 `en-US`
- session 只持久化前端按钮、session 或默认语言；消息内“用英文回答/用中文回答”作为单轮 `message_override`
- `LocaleDescriptor.language_source` 新增 `message_override` 和 `editor_locale`
- 前端交接文档已明确语言切换按钮、请求字段和需要阅读的文档

## 2026-04-25 下一阶段 Agent 架构优化路线

目标：让本项目从“功能型 UE 后端工具”进一步升级为“结构清晰、可解释、可扩展、可学习展示的 Agent 项目”。参考 nanobot 这类轻量 Agent 项目的方向，但不复制多渠道部署、完整 MCP 生态或企业级运维。我们的重点是把单人作品最能打动面试官的部分做扎实：Agent 决策链、Skill 调用、上下文记忆、RAG 检索、项目事实工具、可观测性和学习文档。

### 总体判断

当前后端已经具备 Agent 项目的基本架构：

- `Router / Planner`：负责判断自由聊天、Project QA、Project Inventory 和工具型 Skill。
- `Skill Executors`：Code Review、Code Generate、Logs Analyze、Assets Inspect 已经收缩为固定内置 Skill。
- `RAG Pipeline`：已有 ingestion、chunk、lexical retrieval、vector retrieval、hybrid retrieval、Qdrant、citation 和 degraded fallback。
- `Project Inventory`：能把 UE 工程资产、代码文件和部分元数据作为项目事实层供 Agent Chat 查询。
- `Session / Task Memory`：已有 session history、assistant message 持久化、task history，并已避免工具任务污染 Agent Chat 时间线。
- `Observability`：已有 `debug_view`、`trace_summary`、`retrieval_trace`、`skill_runtime`、metrics 和 alert 雏形。
- `Frontend Contract`：UE 前端和后端已经有统一 handoff 文档，主功能边界清晰。

当前短板：

- 记忆仍偏“历史保存”，还没有稳定的上下文压缩和长期摘要机制。
- RAG 已经能工作，但“为什么检索、检索质量如何、是否可信”还需要更强的评测和解释。
- Skill 架构已有实现，但缺少统一协议文档和开发模板。
- Agent 决策链分散在 `debug_view.route`、`retrieval_trace`、`tool_plan` 等位置，面试展示时还不够一眼看懂。
- 学习文档需要从“使用说明”升级为“完整架构学习路径”。

### 设计原则

- 不再继续横向堆功能，优先纵向打磨 Agent 闭环。
- 每个新增能力都必须能解释“用户输入如何变成决策、上下文、工具调用、最终回答”。
- 工具型能力继续通过固定内置 Skill 扩展，不新增普通用户主菜单。
- RAG 和 Project Inventory 都作为 Agent 的上下文来源，而不是单独的聊天模式开关。
- Debug View 继续承担透明化职责，普通用户界面保持简洁。
- 学习文档和代码实现同步推进，避免后期补文档时说不清架构。

### 范围控制原则

本项目定位是个人作品级、面试展示级 UE Agent 后端，不是企业级 Agent 平台。后续所有阶段都按“能使用、稳定、完整、可讲清楚”作为完成标准，不追求通用平台化和无限扩展。

必须坚持的边界：

- 不做多用户、租户、组织、RBAC 权限系统。
- 不做云端部署、高可用、分布式任务队列和企业监控告警体系。
- 不做动态插件市场、在线安装 Skill、远程执行第三方不可信代码。
- 不做完整 MCP marketplace；如后续接 MCP，只作为学习型可选 adapter，不作为主架构依赖。
- 不做自动修改、重命名、保存或批量迁移 UE 资产；后端只给分析和建议。
- 不做全站爬虫或训练数据采集；官方文档只允许白名单 URL、本地摘要、合规导入。
- 不为了抽象而抽象；当功能只有 5 个固定 Skill 时，不引入复杂插件生命周期、权限沙箱或多 agent 调度。
- 不追求学术级 RAG benchmark；只做能说明检索质量和降级逻辑的项目级评测。
- 不把 Debug View 做成复杂运维平台；只展示能帮助开发、演示和排查的关键链路。

每个阶段的停止标准：

- `Context Manager`：能统一组装上下文、显示裁剪原因、服务 Agent Chat / Project QA 即可停止，不做复杂 graph。
- `Memory Summary`：能压缩长会话、恢复摘要、避免上下文爆炸即可停止，不做跨项目长期画像。
- `Agent Decision Trace`：能解释本轮路由、检索、工具、记忆和 fallback 即可停止，不做完整推理审计平台。
- `RAG Evaluation`：能跑固定样例并输出命中率、引用覆盖、降级结果即可停止，不做大规模 benchmark。
- `Skill Protocol`：能统一现有 5 个 Skill 的 manifest、生命周期和开发文档即可停止，不做动态插件系统。
- `Learning Docs`：能让自己和面试官看懂请求生命周期、RAG、Memory、Skill 即可停止，不写成教材级长篇百科。

判断是否过度开发的检查问题：

- 这个改动是否能在面试展示中 1-2 分钟讲清楚价值？
- 这个改动是否能直接提升当前 UE Agent 的可用性、稳定性或可解释性？
- 这个改动是否需要前端大改但用户看不出收益？
- 这个改动是否只是为了“像企业项目”，而不是为了“作品更完整”？
- 如果删除这个改动，核心 Agent 闭环是否仍然清晰？如果是，优先不做。

## 阶段 A：Context Manager v1

状态：已完成（2026-04-25）。

目标：建立统一上下文管理层，让每次 Agent 调用都有明确、可控、可解释的上下文来源。

后端改动：

- 新增 `app/agent/context_manager.py`。
- 定义统一 `ContextBundle`，建议包含：
  - `recent_messages`：最近 N 轮 Agent Chat / Project QA 对话。
  - `session_summary`：长会话压缩摘要。
  - `editor_context`：当前 project、panel、file、module、selected assets、language。
  - `project_inventory_context`：Project Inventory 命中结果摘要。
  - `retrieval_context`：RAG chunk 和 citation 摘要。
  - `tool_context`：最近相关工具任务摘要，不直接塞入聊天历史。
  - `budget`：本轮上下文 token / 字符预算和裁剪原因。
- `TaskService` 不再直接拼散落 prompt，上层先构造 `ContextBundle`，再交给 LLM 或 Skill。
- `debug_view.context_bundle` 展示最终进入模型或工具的上下文摘要。

边界：

- 第一版不做复杂 agent graph，不做多 agent 协作。
- 不把 Code Review / Assets Inspect 等工具结果自动全文塞入聊天上下文，只存摘要和引用。
- 不改变前端主 UI，只增加 Debug View 可读字段。

前端影响：

- 暂不需要改主界面。
- Debug View 可增加 `Context Bundle` 分区，读取 `debug_view.context_bundle`。

验收标准：

- Agent Chat 连续多轮对话时，后端能稳定带上最近对话和 session summary。
- Project QA 命中 Inventory / RAG 时，Debug View 能看到哪些上下文被采用、哪些被裁剪。
- 工具任务不会污染 Agent Chat history，但最近工具摘要可以作为可选上下文来源。

本轮完成记录：

- 新增 `app/agent/context_manager.py`，统一生成 `context_bundle_v1`。
- `debug_view.context_bundle` 和 `debug_view.memory_summary.context_budget` 已进入统一响应 schema。
- `direct_answer` 与 `project_qa` 会使用同一份 compact context 构造 LLM prompt。
- `CodeReviewSkill` 与 `CodeGenerateSkill` 已能在 `data.context_bundle` 和 Debug View 中携带上下文摘要。
- 工具型任务仍不写入 Agent Chat history，但后续自由聊天可通过 `context_bundle.tool_context` 看到最近工具摘要。
- 第一版只做最近消息、session metadata 摘要占位、editor context、tool summary 和预算估算；真正的自动 memory summary 留到阶段 B。

## 阶段 B：Memory Summary / 上下文压缩

状态：v1 已完成（2026-04-25）。

目标：把 session history 从“原始消息列表”升级为“短期记忆 + 长期摘要”的可控记忆机制。

后端改动：

- 数据层增加 session memory 字段或独立 `session_memory` 表，建议保存：
  - `summary_text`
  - `important_facts`
  - `open_questions`
  - `user_preferences`
  - `project_focus`
  - `updated_at`
  - `source_message_range`
- 新增 `SessionMemoryService`：
  - 当 session 消息超过阈值时触发摘要。
  - LLM 可用时用 LLM 生成中文/英文摘要。
  - LLM 不可用时用规则摘要兜底。
- `Context Manager` 优先读取 `session_summary`，再拼最近 N 轮对话。
- 清空 session 时同步清空 memory summary。

边界：

- 不做跨项目、跨用户的长期个性化画像。
- 不把代码文件全文或资产大量元数据写入 session memory。
- Memory 只服务当前插件项目和当前 session。

前端影响：

- Session Summary 可在 Debug View 展示。
- 普通用户界面暂不新增“记忆管理”面板。

验收标准：

- 长对话恢复后不会把全部历史塞进 prompt。
- Debug View 能看到本轮使用了 `recent_messages` 还是 `session_summary`。
- 用户切换语言后，记忆摘要不破坏最终输出语言策略。

本轮完成记录：

- 新增 `app/agent/memory_manager.py`，使用确定性摘要策略生成 `memory_summary_v1`。
- 第一版直接写入 `sessions.metadata_json.memory_summary`，不新增表、不增加迁移，符合个人作品级边界。
- 当 Agent Chat / Project QA 持久化 assistant 回复后，后端会按阈值更新 session memory。
- `Context Bundle` 已能读取 `memory_summary_v1` 并放入 `debug_view.context_bundle.session_summary`。
- 修复 Context Bundle 读取历史时超过 limit 可能拿到较早消息的问题，现在 recent messages 优先取最新历史。
- `POST /api/v1/sessions/{session_id}/clear` 会清掉旧 memory，避免清空会话后残留摘要。
- `/api/v1/sessions/{session_id}` 顶层返回 `memory_summary`，方便 Debug View 或 Monitor 查看。

## 阶段 C：RAG Evaluation / 检索质量可评测

状态：v1 已完成（2026-04-25）。

目标：让 RAG 不只是“能查”，而是能证明检索质量、引用覆盖和降级行为。

后端改动：

- 新增或完善 `tests/eval` 下的 RAG dataset：
  - `project_docs` 问答。
  - `code_reference` 问答。
  - `asset_rules` 问答。
  - `engine_notes` 问答。
  - “应当不检索”的普通聊天样例。
- 增加评测指标：
  - route accuracy：是否正确走 direct / RAG / Inventory。
  - citation coverage：是否返回引用。
  - retrieval hit rate：top-k 是否命中预期 domain / doc。
  - no-result handling：无结果是否清楚降级。
  - language accuracy：最终输出语言是否正确。
- `KnowledgeBaseService.status()` 增加更直观的 RAG readiness：
  - lexical ready
  - embedding ready
  - vector store ready
  - degraded reason
  - indexed docs / chunks / domains
- Debug View 增加检索解释：
  - 为什么检索。
  - 使用了哪些 filters。
  - top chunks 来源、分数、domain。
  - 为什么降级为 lexical 或 no result。

边界：

- 不追求学术级 RAG benchmark。
- 不引入复杂 reranker 服务，第一版只做已有 rerank 逻辑的可解释化。
- 不自动爬全站官方文档，仍走本地导入和白名单官方 URL 摘要。

前端影响：

- Monitor / Debug View 可显示 RAG readiness。
- Agent Chat 普通用户界面只显示 citation 和简洁提示，不展示复杂评分。

验收标准：

- 可以一键跑 RAG eval 并输出 summary。
- 至少覆盖 10-20 条高质量样例。
- 面试展示时能说清楚“什么时候检索、检索到了什么、没检索到怎么办”。

本轮完成记录：

- 复用已有 `scripts/run_rag_eval.py` 和 `tests/eval/rag_project_qa_dataset.jsonl`，不新增复杂评测服务。
- `GET /api/v1/knowledge-base/status` 新增 `rag_readiness`。
- `rag_readiness` 包含 `lexical_ready`、`embedding_ready`、`vector_store_ready`、`usable_for_project_qa`、`degraded_reasons`、`domain_counts`、`indexed_documents`、`indexed_chunks` 和本地 eval 命令。
- `effective_mode` 会显示当前实际检索模式；当 hybrid/vector 不可用时明确降级到 `lexical_only`。
- eval summary 已覆盖 `recall_at_k`、`precision_at_k`、`hit_at_k`、`mrr`、`ndcg_at_k`、`route_accuracy`、`language_accuracy`、`citation_coverage`、`low_confidence_ratio`、`no_result_ratio`。
- 第一版不引入 reranker 服务、不做学术 benchmark、不自动爬全站官方文档。

## 阶段 D：Skill Protocol v1

状态：v1 已完成（2026-04-25）。

目标：把现有固定内置 Skill 从“代码上已经拆分”升级为“协议清晰、可扩展、可教学”的 Skill 架构。

后端改动：

- `app/skills/registry.py` 现在为 5 个固定内置 Skill 输出统一 manifest：`skill_id`、`task_type`、`input_schema`、`collector`、`rules`、`retrieval_domains`、`llm_analyzer`、`projector_outputs`、`debug_contract`。
- `GET /api/v1/system/capabilities` 的 `capabilities.skill_catalog[]` 暴露 `protocol_version = skill_protocol_v1` 和 `protocol`。
- `app/skills/runtime.py` 统一生成 `debug_view.skill.lifecycle`，包括 `collector`、`rules`、`retrieval`、`llm`、`projector` 五段状态。
- `debug_view.skill.lifecycle.llm.reason` 优先使用稳定的机器码，例如 `missing_openai_api_key`、`degraded_fallback`，没有机器码时再退回人类可读文案。
- 第一版开发说明收敛到 `docs/backend-user-guide.md` 与 `docs/frontend-unified-handoff.md`，不额外新增分散文档，保持交接简洁。

边界：

- 不做用户可动态安装 Skill。
- 不做 marketplace。
- 不做复杂权限沙箱。
- 新功能优先扩展已有 5 个主 Skill，除非确实出现全新使用场景。

前端影响：

- Debug View 的 Skill 分区可更稳定展示生命周期。
- 普通用户主菜单不增加。
- 主 UI 不强制修改；如果 UE 前端要增强 Debug View，可展示一条 “collector -> rules -> retrieval -> llm -> projector” 流水线。

验收标准：

- 面试时能用一张图说明 Skill 执行链。（已满足）
- 新增一个规则或 LLM 分析项时，优先改对应 Skill executor / service，不需要改 TaskService 主流程。（已满足）
- `GET /api/v1/system/capabilities` 能清楚展示 Skill catalog。（已满足）
- 集成测试已覆盖 capabilities、direct chat skill lifecycle、code review skill lifecycle。（已满足）

## 阶段 E：Agent Decision Trace

状态：v1 已完成（2026-04-25）。

目标：把分散的 route、tool_plan、retrieval_trace、skill_runtime 整合成一条清晰的 Agent 决策链。

后端改动：

- 新增统一字段 `debug_view.agent_decision_trace`。
- 建议结构：
  - `input_summary`
  - `language_decision`
  - `intent_decision`
  - `context_decision`
  - `retrieval_decision`
  - `tool_decision`
  - `memory_decision`
  - `fallback_decision`
  - `final_response_plan`
- 每个 decision 包含：
  - `decision`
  - `reason`
  - `confidence`
  - `source`
  - `alternatives`
  - `warnings`
- 将现有 `route`、`tool_plan`、`retrieval_trace`、`context_bundle` 的核心信息投影到 decision trace。

边界：

- 不要求所有决策都由 LLM 产生。
- 规则决策、启发式决策和 LLM 决策都可以进入 trace，但必须标明 source。
- 不把完整 prompt 和敏感 raw payload 暴露给普通用户。

前端影响：

- Debug View 增加 `Agent Decision Trace` 分区。
- 普通用户界面不显示完整决策链。

验收标准：

- 任意一次 Agent Chat 都能解释为什么走 direct、RAG、Inventory 或某个 Skill。
- 任意一次 Code Review / Assets Inspect 都能解释 LLM 为什么 completed 或 skipped。
- 面试展示时能用一条 trace 展示完整 Agent loop。

本轮完成记录：

- 新增 `app/agent/decision_trace.py`，生成 `agent_decision_trace_v1`。
- `DebugView` schema 新增 `agent_decision_trace`。
- 每次任务响应都会在 `debug_view.agent_decision_trace.decisions` 中展示：
  - `input_summary`
  - `language_decision`
  - `intent_decision`
  - `context_decision`
  - `retrieval_decision`
  - `tool_decision`
  - `memory_decision`
  - `fallback_decision`
  - `final_response_plan`
- 第一版只汇总已有规则、路由、上下文、检索和 Skill 信息，不额外调用 LLM 生成解释。
- Debug View 可以直接读 `summary.route_type`、`summary.skill_id`、`summary.retrieval_mode`、`summary.memory_status` 和 `summary.finish_reason`。

## 阶段 F：Learning Docs / 面试展示文档

状态：v1 已完成（2026-04-25）。

目标：形成一份既能自己复习、又能给面试官看的完整学习文档。

建议新增文档：

- `docs/agent-architecture-study.md`（已完成）
- `docs/rag-and-memory-study.md`（已完成）
- `docs/skill-development-guide.md`（已完成）
- `docs/request-lifecycle.md`（已完成）

`agent-architecture-study.md` 内容：

- 什么是 Agent。
- 本项目的 Agent loop：
  - User Input
  - Router / Planner
  - Context Manager
  - Memory
  - RAG
  - Project Inventory Tool
  - Skill Executor
  - LLM
  - User View / Debug View
- 本项目和 nanobot 的参考关系：
  - 借鉴轻量、可扩展、可调试的思想。
  - 不复制多渠道和完整部署生态。
- 为什么选择固定内置 Skill，而不是无限动态插件。
- 为什么 UE 项目事实使用 Project Inventory，而不是让 LLM 直接猜。

`rag-and-memory-study.md` 内容：

- 文档导入流程。
- chunk 和 metadata 的作用。
- lexical / vector / hybrid retrieval 区别。
- embedding model 和 vector database 的关系。
- Qdrant 如何接入。
- 只接 LLM、不接 embedding 时如何降级。
- session memory 为什么需要摘要。
- context window 为什么需要预算和压缩。

`skill-development-guide.md` 内容：

- Skill 的结构。
- Collector / Rules / Retrieval / LLM Analyzer / Projector 的职责。
- 如何扩展 Code Review。
- 如何扩展 Assets Inspect。
- 如何写测试和 Debug View。

`request-lifecycle.md` 内容：

- 一次 Agent Chat 请求从 UE 到后端的完整流程。
- 一次 Code Review 请求的完整流程。
- 一次 Project Inventory 查询的完整流程。
- 每个阶段对应代码位置。
- 每个阶段对应 Debug View 字段。

验收标准：

- 读完文档后，能够独立讲清楚本项目的 Agent 架构。
- 能说清楚 RAG、Memory、Skill、Tool Calling、Observability 各自作用。
- 能拿一条真实请求做完整流程复盘。

## 推荐开发顺序

1. 阶段 A：Context Manager v1（已完成）
2. 阶段 B：Memory Summary / 上下文压缩（v1 已完成）
3. 阶段 E：Agent Decision Trace（v1 已完成）
4. 阶段 C：RAG Evaluation / 检索质量可评测（v1 已完成）
5. 阶段 D：Skill Protocol v1（v1 已完成）
6. 阶段 F：Learning Docs / 面试展示文档（v1 已完成）

原因：

- 先做 Context Manager 和 Memory，能直接提升 Agent Chat 的真实体验。
- 再做 Decision Trace，能让前面新增的上下文和记忆变得可解释。
- RAG Eval 接着做，可以验证检索质量，而不是盲目调参。
- Skill Protocol 最后做结构化收口，避免一开始过度抽象。
- 学习文档贯穿每阶段补充，最后统一整理成完整版本。

当前本轮 Agent 架构优化路线已经完成 v1。后续如果继续优化，建议从真实测试反馈出发，只在当前 5 个 Skill 边界内补能力，不新增大而泛的平台化阶段。

## 面试展示目标

最终希望能展示以下 5 个亮点：

- `Agent Loop`：用户问题如何经过 intent routing、context assembly、tool/RAG decision、LLM response。
- `Memory`：长会话如何压缩，如何避免上下文爆炸。
- `RAG`：知识库如何导入、检索、引用、降级和评测。
- `Skill`：代码审查、代码生成、日志分析、资产检查如何作为固定 Skill 执行。
- `Observability`：Debug View 如何展示 route、context、memory、retrieval、tool、trace 和 metrics。

不追求：

- 多用户企业权限。
- 云端部署和高可用。
- 多渠道聊天机器人。
- 完整 MCP marketplace。
- 自动修改 UE 工程资产或代码文件。

当前项目定位仍然是：个人作品级 UE Agent 后端，重点展示 Agent 架构理解、RAG 工程能力、工具调用闭环、可解释调试和清晰文档。

## 2026-04-26 下一步计划：双检索策略与本地 UE 知识补充

状态：v1 已实现（2026-04-25 提前完成后端部分）。

目标：在不强制接入向量模型和向量数据库的前提下，让知识检索对 Agent Chat、Project QA、Code Generate、Code Review 更稳定可用。当前 RAG 基础链路已经完成，但如果没有 embedding / Qdrant，语义召回能力有限。因此下一步采用“RAG + 本地 grep 检索”并存的策略。

### 当前判断

- RAG 已完成基础链路：文档导入、chunk、metadata、lexical retrieval、vector / hybrid 接口、Qdrant 接口、citation、readiness、eval。
- 当前未接入 embedding / Qdrant 时，vector / hybrid 不会真正发挥语义召回优势。
- `lexical RAG` 可以继续服务文本问答，但需要补充本地 UE 笔记和项目文档。
- `markdown + grep` 更适合代码生成、代码参考和规则查找，因为代码类问题通常依赖明确关键词、类名、函数名、模块名、宏、UE API 名。

### 检索策略

1. Agent Chat / Project QA 文本问答

- 已接入 embedding + Qdrant：优先走现有 RAG hybrid / vector。
- 未接入 embedding + Qdrant：优先走 lexical RAG；如果召回不足，再用本地 markdown grep 做补充。
- 适用内容：项目说明、UE 官方整理笔记、团队规则、引擎概念、资产规范。

2. Code Generate / 代码参考

- 无论是否接入向量，都优先走本地 markdown/code grep。
- grep 命中 `code_reference`、`examples`、`engine_notes` 后，把相关片段和路径交给 LLM。
- 适用内容：可复用代码示例、UE API 用法、模块模板、常见 Actor / Component / Subsystem 写法。

3. Code Review

- 规则扫描仍是第一层。
- grep 用于补充 `team_rules`、`engine_notes`、`code_reference`，给 LLM 更贴近项目的审查依据。
- 不用 grep 代替读取选中文件；选中文件仍来自 `CodeReviewSkill.collector`。

4. Assets Inspect / Logs Analyze

- 继续以确定性规则和当前 payload 为主。
- grep 仅用于查 `asset_rules`、`engine_notes`、`incident_history` 这类辅助说明。

### 文档分类规划

建议本地知识目录按 domain 分类，避免全库 grep 结果太乱：

```text
knowledge/
  engine-notes/
    ue-actor-lifecycle.md
    ue-blueprint-basics.md
    ue-static-mesh-nanite-lod-collision.md
    ue-gameplay-framework.md
  project-docs/
    rushba-project-overview.md
    rushba-module-notes.md
  code-reference/
    actor-lifecycle-example.cpp
    component-pattern-example.cpp
    subsystem-example.cpp
  examples/
    async-asset-loading-example.md
    soft-reference-example.md
  asset-rules/
    naming-conventions.md
    blueprint-asset-checklist.md
  team-rules/
    cpp-style.md
    ue-code-review-rules.md
```

domain 映射：

- `engine_notes`：UE 官方文档整理笔记、引擎概念、API 用法摘要。
- `project_docs`：当前项目说明、模块说明、开发流程。
- `code_reference`：用户手动保存的代码文件和参考实现。
- `examples`：可复制/改写的代码生成示例。
- `asset_rules`：资产命名、Blueprint、StaticMesh、材质、LOD、Collision、Nanite 等规则。
- `team_rules`：代码规范、审查规则、项目约定。

### UE 官方文档补充边界

合法合规原则：

- 不做整站爬取，不把大段官方原文直接存入仓库。
- 优先手动整理 markdown 学习笔记：标题、链接、访问日期、关键概念、自己的理解、短摘录。
- 每份笔记保留官方链接，方便引用和后续复核。
- 如果需要自动化，只做用户给定 URL 的少量页面摘要或本地保存，不做批量镜像。
- 代码示例优先使用自己整理或自己改写的最小示例。

优先整理主题：

- Actor / Component 生命周期：Constructor、BeginPlay、Tick、EndPlay、GC。
- UObject / UPROPERTY / TObjectPtr / TWeakObjectPtr 基础。
- Soft Object Reference 与异步加载。
- Blueprint 父类、Tick、组件、变量暴露。
- StaticMesh 常见设置：Nanite、LOD、Collision、Material Slots、Lightmap。
- Gameplay Framework：GameMode、GameState、PlayerController、Pawn、Character。
- Module / Build.cs / Plugin 基础结构。

### 后端开发任务

阶段 A：Local Grep Retrieval v1

- 新增本地 grep 检索服务 `app/services/local_search_service.py`。（已完成）
- 支持 domain 限定、文件扩展名限定、关键词提取、top_k、片段窗口。（已完成）
- 返回统一结构：`source_path`、`domain`、`title`、`snippet`、`score`、`matched_terms`。（已完成）
- Windows 下优先用 Python 实现，避免依赖系统 `grep` 或 `rg`。（已完成）

阶段 B：知识库配置与分类

- 在设置中新增或复用 `KB_SOURCE_PATHS`，支持 `knowledge/` 目录。（已完成，默认加入 `./knowledge`）
- 增加 domain 推断：按目录名映射到 `engine_notes`、`code_reference`、`examples` 等。（已完成）
- `GET /api/v1/knowledge-base/status` 增加 local search readiness。（已完成）

阶段 C：接入 Skill

- `CodeGenerateSkill`：优先使用 local grep 搜索 `code_reference/examples/engine_notes`。（已完成）
- `CodeReviewSkill`：通过代码审查 guidance retrieval 链路补充 grep 的 `team_rules/engine_notes/project_docs/examples`，不替代选中文件读取。（已完成）
- `ProjectQASkill`：lexical RAG 无命中时可 fallback 到 local grep。（已完成）
- Debug View 中展示 `local_search` 命中来源和 matched terms。（已完成）

阶段 D：UE 文档笔记种子

- 新增少量合法 markdown 笔记，先覆盖上述优先主题。（已完成）
- 每篇笔记包含：`source_url`、`topic`、`summary`、`key_points`、`use_for`。（已完成）
- 不追求多，先保证能让 Code Generate 和 Project QA 命中。（已完成）

阶段 E：测试与文档

- 增加 local search 单元测试。（已完成）
- 增加 Code Generate 命中本地 code reference 的集成测试。（已完成）
- 增加 Project QA 在无向量时 fallback local grep 的测试。（部分覆盖：Project QA / Code Generate 集成链路已验证，后续可补更窄用例）
- 更新 `backend-user-guide.md`、`frontend-unified-handoff.md`、`rag-and-memory-study.md`。（已完成）

### 前端影响

- 主 UI 暂不需要修改。
- Debug View 可选新增 `local_search` 分区，显示命中的 markdown/code 文件、domain、snippet、matched_terms。
- Code Generate 主 UI 可以继续显示后端已有 generated code 结果，不需要新增输入项。

### 验收标准

- 不配置 embedding / Qdrant 时，Code Generate 能通过本地 markdown/code grep 找到参考片段。
- Project QA 文本问答至少能命中本地 UE markdown 笔记或明确说明无结果。
- Debug View 能解释本轮用了 RAG、local grep，还是二者都没命中。
- 不新增企业级搜索服务，不引入复杂索引系统，不把官方文档做成大规模镜像。

### 2026-04-26 测试反馈收口

状态：已处理。

- 问题：Agent Chat 询问“知识库有什么内容”时引用 `backend.md`、`forward.md`、`docs/improveplan.md` 等后端开发资料。
- 原因：旧默认 `KB_SOURCE_PATHS` 同时包含后端设计文档和用户知识目录，导致用户可见知识库被开发资料污染。
- 决策：默认知识库范围收口为 `KB_SOURCE_PATHS=./knowledge`。后端开发文档只作为开发资料，不再默认参与用户问答检索。
- 操作：如果本地数据库已经导入旧文档，需要重启后端后调用 `POST /api/v1/knowledge-base/reindex` 清理旧索引。
- 问题：Code Generate 显示 `draft.txt`，用户无法判断文件在哪里。
- 原因：后端代码生成是非破坏性草稿，不写磁盘；`draft.txt` 只是兜底虚拟路径，但前端容易展示成真实文件。
- 决策：后端增强 target_type 兼容，泛化 `general/code/cpp/ue_cpp` 默认按 UE C++ 草案返回；同时新增 `write_policy.written_to_disk=false`、`generated_items[].write_status=not_written`、`generated_items[].is_virtual=true`。
- 前端边界：Code Generate 面板应把 `generated_items` 当成“代码结果按钮 / Tab / 列表”，点击展示 `code`，不要提示“已生成到磁盘”。

## 2026-04-26 下一步计划：常用 UE 代码知识库补强

状态：v2 已实现（Enhanced Input Character + 常用 UE 代码场景第一批）。

目标：把 Code Generate 从“只有通用 Actor 骨架”推进到“常见 UE 场景有可检索代码参考”。当前问题不是前端接口问题，而是知识库和兜底模板都缺少“角色增强输入”这类常用场景，因此 LLM/模板只能返回 BeginPlay/Tick 空骨架。

### 范围边界

- 只补作品集常见、面试展示价值高的 UE 场景，不做完整模板市场。
- 每个场景优先补 `engine_notes` + `code_reference` + 必要 `examples`，确保 local grep 能命中。
- 模板只作为非破坏性草稿返回，不写入工程、不自动修改 Build.cs。
- 前端仍只渲染 `generated_items`，不需要新增主 UI。

### 第一批优先主题

- `Enhanced Input Character`：角色移动、视角、跳跃、Mapping Context、Input Actions、Build.cs 依赖。（已完成）
- `Actor Component` 常用交互组件：Overlap、接口调用、事件广播。（已完成基础版）
- `Subsystem` 基础写法：GameInstanceSubsystem / WorldSubsystem 的生命周期和调用入口。（已完成 GameInstanceSubsystem 基础版）
- `Gameplay Tag / DataAsset` 配置驱动示例。（已完成知识笔记，模板后续视测试反馈补）
- `LineTrace Interaction`：角色射线交互、接口检查、DebugDraw。（已完成基础版）

### 本轮已完成

- 新增 `knowledge/engine-notes/ue-enhanced-input-character.md`。
- 新增 `knowledge/code-reference/enhanced-input-character-example.h`。
- 新增 `knowledge/code-reference/enhanced-input-character-example.cpp`。
- 新增 `knowledge/examples/enhanced-input-buildcs-note.md`。
- Code Generate prompt 明确 Enhanced Input / Character 请求应生成 `ACharacter`、`UInputMappingContext`、`UInputAction`、`UEnhancedInputComponent` 相关代码。
- Code Generate 兜底模板能识别“角色增强输入代码怎么写”这类中文请求，返回 `Source/<Module>/Public/<Class>.h` 和 `Source/<Module>/Private/<Class>.cpp`。
- 生成结果会在 `patch_plan` 中提示添加 `EnhancedInput` 模块依赖和在编辑器中分配 Input Action / Mapping Context 资产。
- 新增 `knowledge/engine-notes/ue-common-code-generation-patterns.md`，用于说明交互组件、射线交互、Subsystem、DataAsset、Gameplay Tags 的生成边界。
- 新增 `knowledge/code-reference/interaction-component-example.h/.cpp`。
- 新增 `knowledge/code-reference/line-trace-interaction-component-example.h/.cpp`。
- 新增 `knowledge/code-reference/game-instance-subsystem-example.h/.cpp`。
- 新增 `knowledge/examples/dataasset-gameplaytag-note.md`。
- Code Generate 兜底模板能识别“交互组件 / overlap”、“射线交互”、“GameInstanceSubsystem / 子系统 / 全局管理器”等常见请求。

### 验收标准

- 用户问“角色增强输入代码怎么写”时，Code Generate 不应再返回普通 Actor BeginPlay/Tick 空骨架。
- 即使未配置 LLM，也应返回可读的 Enhanced Input Character 草稿。
- local grep 应命中 Enhanced Input 相关 knowledge 文件。
- 用户问“交互组件怎么写”“射线交互组件怎么写”“全局管理器子系统怎么写”时，应返回对应 UE 基类的草稿，而不是普通 Actor 空骨架。
- 前端不需要新增主 UI；如要联调，只需要确认 `generated_items[].code` 能正常预览。

### UE 前端回传状态

状态：已记录。

- UE 前端已确认第 24 节 Code Generate 虚拟草稿展示完成：`generated_items` 作为代码草稿按钮 / Tab，点击后展示 `generated_items[].code`。
- 前端已把 `file_path` 作为建议路径展示，并把 `write_status=not_written`、`is_virtual=true` 视为正常草稿状态。
- 后端暂不需要为这部分展示契约继续改接口。
- 下一次联调重点转向本节第一批常用 UE 场景，确认 Enhanced Input Character、Interaction Component、LineTrace Interaction、GameInstanceSubsystem 的完整代码正文是否都能在前端展开查看。

## 2026-04-26 Agent Chat 知识库问答收口

状态：已实现。

触发问题：

- Code Generate 当前实测基本可用，阶段通过。
- Agent Chat 询问“知识库有哪些内容”时，普通检索会把命中的源码片段展开到回答里，用户体验像是在直接吐文件内容。
- 用户问“actor的生命周期是什么”时，虽然 LLM 能回答，但用户不容易判断知识库是否真正参与；同时中文问题检索英文知识文档的 lexical 命中需要增强。

### 开发边界

- 不做复杂知识库管理 UI，不新增企业级搜索系统。
- 不把所有中文 query 都翻译成英文，只做常用 UE 术语的轻量 query 扩展。
- 不阻止 LLM 使用通用 UE 知识；但需要通过 `citations` / `debug_view.retrieval` 让用户知道知识库是否参与。
- “知识库有哪些内容”这类元问题返回目录摘要，不返回源码正文。

### 本轮完成

- 新增 `knowledge_catalog` 回答模式。
- `data.answer_mode=knowledge_catalog`、`data.catalog`、`debug_view.retrieval.mode=knowledge_catalog` 可用于 Debug View。
- 知识库目录回答按 domain 汇总文档，只列标题、路径、类型，不展开 `.h/.cpp` 内容。
- local grep 和 lexical RAG query 侧增加中英扩展词，例如“生命周期” -> `lifecycle / constructor / BeginPlay / Tick / EndPlay`。
- 增加测试覆盖“知识库有哪些内容”不返回源码正文、“actor的生命周期是什么”能命中 `ue-actor-lifecycle.md`。

### 验收标准

- 用户问“知识库有哪些内容”时，回答应是目录概览，不应出现 `#include`、`UCLASS(` 这类源码正文。
- 用户问“actor的生命周期是什么”时，`data.retrieved_docs` 或 Debug View 中应能看到 `knowledge/engine-notes/ue-actor-lifecycle.md`。
- 如果 LLM 可用，最终回答可以由 LLM 综合表达，但 Debug View 必须能解释检索证据来源。
