# 项目问答与语言策略说明文档

本文档对应 `backend.md` 的 Phase 2，说明统一聊天入口如何区分普通聊天、项目问答和工程任务，以及语言输出如何统一。

## 目标

- 用户用什么语言提问，系统主要就用什么语言回答
- 普通闲聊不要误拉进知识库
- 项目相关问题优先走 `project_qa`
- 明确工程动作优先走任务路由

## 当前意图类型

- `casual_chat`
- `project_qa`
- `task_request`

## 当前知识相关性

- `strong`
- `possible`
- `none`

## 路由规则

### 1. `direct_answer`

满足以下特征时优先进入：

- 没有明显工程上下文
- 没有项目知识关键词
- 没有工具动作词

### 2. `project_qa`

满足以下任一条件时优先进入：

- 命中工程上下文
- 当前文件 / 当前模块明显和项目知识相关
- 用户问题命中项目文档、配置、接口、规范、日志等术语

### 3. `single_tool`

满足以下特征时优先进入：

- 明确的工具动作词
- 确定性功能面板
- 前端直接传了非 `agent_chat` / `project_qa` 的任务类型

## 语言策略

### 自动判定

- 默认 `preferred_output_language = auto`
- 以最新一轮用户输入为主
- 当前实现中，只要文本包含 CJK，就会判成 `zh-CN`
- 否则判成 `en-US`

### 显式覆盖

以下情况会覆盖自动判定：

- 用户消息包含“用英文回答”
- 用户消息包含“用中文回答”
- `runtime_options.preferred_output_language` 显式不是 `auto`

## 必落字段

- `locale.detected_input_language`
- `locale.preferred_output_language`
- `locale.final_output_language`
- `locale.language_source`

## 当前前端联调建议

- UI 主文案以 `user_view` 为准
- 当前最终输出语言以 `locale.final_output_language` 为准
- 调试界面必须展示 `intent`、`locale` 和 `retrieval_trace`

## 当前已知边界

- 当前 `direct_answer` 已优先走已配置的在线 LLM；如果 LLM 不可用，会返回结构化降级回复而不是抛出不兼容结果
- 语言识别当前是轻量规则，不是统计模型
- 更复杂的中英混输和会话级语言记忆，会在后续阶段继续增强
