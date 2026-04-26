# 面试演示脚本

本文用于 5-8 分钟快速讲清楚 UE Agent Backend。目标不是逐个读接口，而是展示“这是一个能服务游戏研发流程的 Agent 后端”。

## 1. 开场定位

一句话：

> 这是一个配合 Unreal Editor 插件使用的本地 AI Agent 后端，目标是把代码、资产、日志、项目知识库和 LLM 组织成一个可解释的游戏研发辅助工具链。

项目边界：

- 个人作品级，不做企业部署、多租户权限、复杂云监控。
- 后端不直接修改 UE 工程文件，不自动保存资产。
- 所有生成和修复都是草稿或建议，用户在编辑器里确认后再采纳。

## 2. 架构主线

可以按这条链路讲：

```text
UE Plugin
-> FastAPI
-> Router / Intent
-> Context Bundle / Memory Summary
-> Skill / Tool
-> RAG / Local Grep / Project Inventory / LLM
-> User View + Debug View
```

重点解释：

- Router 判断自由聊天、项目问答、具体工具任务。
- Context Bundle 控制每轮给 LLM 的上下文，不把所有历史无限塞进去。
- Memory Summary 压缩长会话，只保留最近消息和摘要。
- Skill 是固定内置的，不做动态插件市场，便于作品级稳定展示。
- Debug View 能解释为什么走这条路、用了哪些知识库和工具。

## 3. Demo 路线

### Demo A：Agent Chat / Project QA

问题：

```text
知识库有哪些内容
```

展示点：

- 后端走 `knowledge_catalog`，返回知识库目录，不展开源码正文。
- Debug View 能看到 `data.catalog`。

问题：

```text
actor的生命周期是什么
```

展示点：

- 中文问题能通过轻量中英扩展命中英文 UE 笔记。
- 看 `data.retrieved_docs` / `data.citations` 证明知识库参与。

### Demo B：Code Generate

问题：

```text
角色增强输入代码怎么写
```

展示点：

- 命中本地 `knowledge/code-reference` 和 `engine-notes`。
- 返回 `.h/.cpp` 虚拟草稿，不写入磁盘。
- `validation_plan` 提醒检查 Build.cs、Input Action、Mapping Context、PIE。

### Demo C：Code Review Agent Workflow

操作：

- 前端扫描 C++ 文件。
- 选择一个 `.cpp`。
- 点击 Code Review。

展示点：

- 前 6 个块仍是稳定 Code Review 输出。
- 后面追加 `agent_workflow`、`fix_draft`、`validation_plan`。
- Debug View 里有 `draft_fix_plan` 和 `build_validation_plan`。
- 这体现 Agent 不只是审查，还能把修复建议和验证步骤串起来。

### Demo D：Assets Inspect

操作：

- 选择 `NewMap` 或命名不规范资产。
- 点击 Assets Inspect。

展示点：

- 规则检查给出命名问题。
- LLM 可用时给综合解释；不可用时稳定降级。
- `validation_plan` 提醒 Fix Up Redirectors、Reference Viewer、蓝图编译。

### Demo E：Logs Analyze

输入：

```text
LogTemp: Error: Access violation
Callstack: 0x0001 Demo!MyModule
LogStreaming: Warning: Failed to load /Game/Maps/TestMap
```

展示点：

- 识别 access violation、asset load failure。
- 输出复现、日志窗口、资产路径和模块排查清单。
- 后续可以把日志结论再带回 Agent Chat。

## 4. 面试问答提示

问：为什么这是 Agent，不是普通 ChatBot？

答：它有路由、上下文管理、记忆压缩、工具调用、知识检索、项目快照、可解释 Trace 和结构化结果投影，不只是把用户消息发给 LLM。

问：为什么不用复杂多 Agent？

答：个人作品级项目优先稳定和可解释。当前用固定内置 Skill 表达能力边界，避免动态插件和多 Agent 调度带来的复杂性。

问：没有向量模型时 RAG 怎么办？

答：使用 lexical RAG 和 local grep；代码生成优先查 markdown/code 知识文件。接入 embedding + Qdrant 后语义召回会更好。

问：怎么保证不误改工程？

答：后端所有生成、修复、验证都是建议或虚拟草稿，`written_to_disk=false`。真正采纳由用户在 UE 编辑器里完成。

## 5. 最后总结

收尾可以这样说：

> 这个项目的核心价值不是做一个全能聊天机器人，而是把 AI Agent 放进 UE 研发管线里，让它能理解项目上下文、查知识库、调用固定工具、给出可解释结果，并把代码、资产、日志和验证步骤串成一个稳定的个人作品级闭环。
