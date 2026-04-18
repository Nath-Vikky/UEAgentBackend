# 版本变更记录

## Phase 1

- 建立统一 `/api/v1/*` 接口命名空间
- 建立统一响应契约和双视图结构
- 建立基础系统接口、任务查询和快照落库

## Phase 2

- 新增语言识别与输出语言统一策略
- 新增意图识别与项目相关性判定
- 新增项目问答 RAG 路径
- 新增知识库刷新、导入和导入任务查询

## Phase 3

- 新增显式工程任务接口
- 新增工作流执行与单工具路径
- 新增 Artifact 查询
- 新增任务事件与 SSE 事件回放

## Phase 4

- 统一聊天入口补齐完整 run 查询与取消
- Proposal 从“仅响应字段”升级为：
  - 待审批列表
  - Proposal 详情
  - 决策提交
  - 决策详情
- `config-generate` 进入 `waiting_confirmation`
- 新增 `/metrics`
- 新增 `/api/v1/system/alerts`

## Phase 5

- 新增多能力评测数据集与通用评测脚本
- 新增回归套件脚本
- 新增知识库维护接口：
  - `POST /api/v1/knowledge-base/reindex`
  - `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry`
  - `GET /api/v1/knowledge-base/documents`
  - `GET /api/v1/knowledge-base/documents/{doc_id}`
  - `DELETE /api/v1/knowledge-base/documents/{doc_id}`
- 新增成本/延迟/失败率告警快照字段与阈值配置
- 新增最终交付、前端最终交接包、评测验收和版本文档
