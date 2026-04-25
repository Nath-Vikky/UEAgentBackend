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
