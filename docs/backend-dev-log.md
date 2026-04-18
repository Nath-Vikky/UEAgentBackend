# 后端开发日志

## Phase 1

- 建立 `backend/` 工程骨架、统一 `/api/v1/*` 命名空间与基础异常处理
- 完成配置层、运行时 Profile、SQLAlchemy 模型与 Alembic 初始迁移
- 完成统一响应契约、`user_view` / `debug_view` / `presentation`

## Phase 2

- 建立语言识别与统一输出字段
- 建立意图识别、项目相关性判定和 `project_qa` 路由
- 打通知识库导入、切片、检索、citation 与 fallback
- 新增 Phase 2 RAG 评测脚本和样例数据

## Phase 3

- 建立显式工具注册表与核心工程任务接口
- 打通代码审查、日志分析、配置生成、性能分析工作流
- 新增代码草稿、配置校验、资产检查的单工具路径
- 新增 Artifact 查询、任务事件与 SSE 事件回放

## Phase 4

- 统一聊天入口补齐 run 查询与取消
- Proposal 从响应字段升级为完整审批闭环
- `config-generate` 进入 `waiting_confirmation`
- 新增 `/metrics`、`/api/v1/system/alerts` 基础观测面
- 新增审计日志与更完整的调试字段

## Phase 5

### 已完成

- 新增多能力评测数据集：
  - `intent_language_dataset.jsonl`
  - `logs_analyze_dataset.jsonl`
  - `code_review_dataset.jsonl`
  - `config_task_dataset.jsonl`
- 新增通用多能力评测脚本：
  - `scripts/run_task_eval.py`
- 新增一键回归套件：
  - `scripts/run_regression_suite.py`
- 新增知识库稳定化接口：
  - `POST /api/v1/knowledge-base/reindex`
  - `POST /api/v1/knowledge-base/import-jobs/{job_id}/retry`
  - `GET /api/v1/knowledge-base/documents`
  - `GET /api/v1/knowledge-base/documents/{doc_id}`
  - `DELETE /api/v1/knowledge-base/documents/{doc_id}`
- 新增成本/延迟/失败率告警快照：
  - `GET /api/v1/system/alerts`
- 新增最终交付文档：
  - 后端最终交付文档
  - 前端最终交接包
  - 评测与验收报告
  - 版本变更记录

### 关键决策

- 把 Phase 5 的重点放在“可交付性”而不是继续扩能力面
- 评测分成：
  - RAG 评测
  - 多能力任务评测
  - 回归套件
- 告警先做成“本地快照 + 阈值配置”，保证本地可调试、可验证
- 知识库维护优先补重建、失败重试和文档管理，而不是继续扩更多推理能力

### 实际验证结果

- `pytest -q -p no:cacheprovider`
  - `25 passed`
- `ruff check app tests scripts --no-cache`
  - 通过
- `python scripts/run_rag_eval.py --dataset tests/eval/rag_project_qa_dataset.jsonl`
  - 报告：`storage/artifacts/evals/rag-eval-20260418T043006Z.json`
- `python scripts/run_task_eval.py`
  - 报告：`storage/artifacts/evals/task-eval-20260418T043007Z.json`
- `python scripts/run_regression_suite.py`
  - 报告：`storage/artifacts/regression/regression-suite-20260418T043008Z.json`

### 当前已知限制

- `LangSmith` 与 `OTel` 仍是本地 stub 元数据，不是远端真实导出
- `direct_answer` 已接入在线 LLM 直答，并保留无 API Key / 调用失败时的结构化降级路径
- 审批后的真实工程写入执行桥尚未接入
- RAG 当前仍存在 miss case，需要继续优化检索质量

## 当前结论

后端已经具备：

- 前后端联调能力
- 项目组演示能力
- 自动化回归能力
- 阶段性交付能力

下一步如果继续推进，就不再是“Phase 1-5 能力搭建”，而会进入更偏生产化的真实执行桥、远端观测与部署治理阶段。
