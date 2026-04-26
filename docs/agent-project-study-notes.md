# Agent 项目学习复盘

本文用于自学和面试复盘，解释本项目涉及的 AI Agent 应用开发知识点。

## 1. Agent 的基本循环

本项目的 Agent loop 是：

```text
理解输入
-> 判断意图和工具
-> 组织上下文
-> 检索知识或项目事实
-> 调用 Skill / LLM
-> 投影成用户视图和调试视图
-> 保存历史、任务、trace
```

关键点：

- `Router` 决定是自由聊天、项目问答还是工具任务。
- `Context Manager` 决定本轮 LLM 能看到什么。
- `Skill` 执行具体研发任务。
- `RAG / Inventory` 提供外部事实。
- `Debug View` 解释决策链。

## 2. Context 与 Memory

上下文不是越多越好。当前做法是 `Context Bundle v1`：

- 最新用户问题。
- 最近几轮聊天。
- 编辑器上下文。
- 最近工具任务摘要。
- 会话 memory summary。
- 字符预算和截断说明。

记忆不是长期用户画像，而是轻量会话记忆：

- 短期：最近消息。
- 中期：`memory_summary_v1` 压缩旧消息。
- 工具任务不污染聊天历史，只进入 `tool_context` 摘要。

这样能解释“为什么 LLM 知道刚才做过什么”，也能避免无限上下文膨胀。

## 3. RAG 与 Local Grep

当前检索有三层：

- lexical RAG：数据库 chunk 的词法检索。
- local grep：直接搜索 `knowledge/` 下 markdown/code 文件。
- vector RAG：接入 embedding + Qdrant 后可用。

为什么保留 local grep：

- 不依赖向量模型。
- 代码生成对精确代码片段更敏感。
- 个人项目更容易调试和展示。

为什么还保留向量接口：

- 中文问题和英文文档存在语义鸿沟。
- 同义表达靠词法检索不稳定。
- 后续接入 embedding 后能提升 Project QA 的召回质量。

## 4. Skill 架构

本项目使用固定内置 Skill：

- `ProjectQASkill`
- `CodeReviewSkill`
- `CodeGenerateSkill`
- `LogsAnalyzeSkill`
- `AssetsInspectSkill`

每个 Skill 可以拆成：

- collector：采集输入，例如源码、日志、资产元数据。
- rules：确定性规则。
- retrieval：知识库或本地文件检索。
- llm_analyzer：可选 LLM 综合解释。
- projector：输出 `user_view` 和 `debug_view`。

为什么不做动态 Skill：

- 个人作品级不需要插件市场。
- 固定 Skill 更容易测试、演示和维护。
- 面试更看重能否说清楚边界和请求生命周期。

## 5. User View 与 Debug View

这是项目里很重要的设计：

- `user_view` 给普通用户看，只放自然语言结果和稳定结构块。
- `debug_view` 给开发者看，放 route、retrieval、tools、raw result、trace。

这样避免两个问题：

- 普通 UI 误展示 raw JSON。
- Debug 时找不到“为什么没走 RAG / 为什么 LLM skipped”。

## 6. Validation Advisor

Validation Advisor 是把 Agent 和游戏研发管线连接起来的一步：

- Code Review 后给修复草稿和验证清单。
- Code Generate 后提醒编译、Build.cs、PIE、输入资产配置。
- Logs Analyze 后给复现和排查步骤。
- Assets Inspect 后给 Redirector、蓝图编译、Reference Viewer 检查。

它不自动执行测试，但能体现岗位职责里的“自动化测试和优化”方向：先把验证知识结构化，后续才考虑接入自动执行。

## 7. Project Inventory

知识库回答“规则和知识”，Project Inventory 回答“当前工程事实”。

例如：

- 当前项目有哪些蓝图资产。
- 某个 StaticMesh 是否开了 Nanite。
- 当前工程有哪些 C++ 文件。

后端不解析 `.uasset`，而是让 UE 插件通过 Asset Registry / Editor API 采集摘要并提交。这是合理边界：后端做 AI 推理和检索，编辑器侧做真实引擎数据采集。

## 8. 面试表达重点

可以重点讲：

- 我没有把它做成普通 LLM wrapper。
- 我做了 route、context、memory、RAG、Skill、debug trace。
- 我把功能收缩到游戏研发管线里的代码、资产、日志、知识库、验证建议。
- 我明确限制后端不自动改工程，所有生成和修复都是非破坏性草稿。
- 我保留扩展方向，但没有过度做企业级系统。

## 9. 后续可以继续优化

最值得继续做的是：

- 把 Validation Advisor 接入更具体的 UE 自动化测试命令建议。
- 补更高质量的 UE 知识库小样本。
- 给 Debug View 做更直观的 decision timeline。
- 准备一套真实 Demo 项目输入，用于面试现场演示。
