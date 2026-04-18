# RAG 评测说明文档

Phase 2 已提供一版最小可运行的评测集骨架和基础评测脚本，用于验证项目问答路径没有明显退化。

## 当前文件

- 数据集：`tests/eval/rag_project_qa_dataset.jsonl`
- 脚本：`scripts/run_rag_eval.py`

## 数据集字段

每条样例当前支持：

- `case_id`
- `query`
- `expected_route`
- `expected_language`
- `expected_sources`
- `domain_filters`
- `current_file`
- `notes`

## 指标

- `recall@k`
  - Top-k 结果里命中了多少期望来源
- `precision@k`
  - Top-k 结果里相关来源占比
- `hit@k`
  - Top-k 中是否至少命中一个相关来源
- `mrr`
  - 第一个相关来源出现得越靠前越好
- `ndcg@k`
  - 兼顾命中与排序位置
- `route_accuracy`
  - 是否正确走到 `project_qa`
- `language_accuracy`
  - 输出语言是否符合期望
- `citation_coverage`
  - 结果中是否带引用

## 运行方式

```bash
python scripts/run_rag_eval.py --dataset tests/eval/rag_project_qa_dataset.jsonl
```

也可以指定知识源：

```bash
python scripts/run_rag_eval.py ^
  --dataset tests/eval/rag_project_qa_dataset.jsonl ^
  --source-path ../backend.md ^
  --source-path ./docs
```

## 输出结果

默认写入：

- `storage/artifacts/evals/*.json`

报告里包含：

- 总体摘要
- 每条 case 的命中来源
- 置信度
- citation 数量
- route / language 是否正确

## 当前定位

- 这是一版 Phase 2 的基础评测，不是最终交付版
- 重点用于发现：
  - 项目问答被误判成普通聊天
  - 语言输出偏离用户输入
  - 检索命中为空
  - citation 丢失

## 当前局限

- 样例数量仍较少，主要用于烟雾验证
- 相关性判断当前是基于 `expected_sources`
- 等进入后续阶段后，会继续扩充多领域、多格式、多失败样例
