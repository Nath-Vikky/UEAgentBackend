# UE Agent Backend Benchmark Report

## Summary

- Generated at: `2026-05-08T11:40:16.120758+00:00`
- Source paths: `./README.md, ./docs, ./knowledge`
- RAG datasets: `tests/eval/rag_project_qa_dataset.jsonl, tests/eval/rag_ue_knowledge_dataset.jsonl`
- Task datasets: `tests/eval/intent_language_dataset.jsonl, tests/eval/code_generate_dataset.jsonl, tests/eval/code_review_dataset.jsonl, tests/eval/logs_analyze_dataset.jsonl, tests/eval/config_task_dataset.jsonl`
- LLM mode: `offline_fallback`

## RAG Retrieval Quality

| Metric | Value | Meaning |
| --- | ---: | --- |
| `cases` | 8 | Evaluation case count. |
| `recall_at_k` | 0.9375 | How many expected sources were recovered in top-k. |
| `precision_at_k` | 0.2500 | Relevant hits divided by configured top-k; intentionally strict for sparse labels. |
| `precision_at_retrieved` | 0.6250 | Relevant hits divided by unique retrieved source count. |
| `labeled_precision_ceiling` | 0.2812 | Maximum possible Precision@K for the current label density. |
| `normalized_precision_at_k` | 0.9375 | Precision@K normalized by the label-density ceiling. |
| `hit_at_k` | 1.0000 | Whether each case hit at least one expected source. |
| `top1_accuracy` | 0.8750 | Whether the first retrieved source was expected. |
| `mrr` | 0.9167 | How early the first relevant source appeared. |
| `ndcg_at_k` | 0.9133 | Ranking quality with position discount. |
| `route_accuracy` | 1.0000 | Whether route_type matched expectation. |
| `language_accuracy` | 1.0000 | Whether output language matched expectation. |
| `citation_coverage` | 1.0000 | Whether responses included citations. |
| `no_result_ratio` | 0.0000 | Share of cases without a relevant hit. |

## Task Workflow Quality

| Metric | Value | Meaning |
| --- | ---: | --- |
| `cases` | 12 | Task evaluation case count. |
| `success_rate` | 1.0000 | Responses with success=true. |
| `route_accuracy` | 1.0000 | Route matched expected workflow/single_tool/direct route. |
| `language_accuracy` | 1.0000 | Output language matched expected locale. |
| `field_coverage` | 1.0000 | Required response fields were present. |
| `semantic_accuracy` | 1.0000 | Rule/issue/value checks matched expectations. |
| `error_rate` | 0.0000 | Responses containing errors. |

## Runtime Performance

| Metric | Value |
| --- | ---: |
| `requests` | 20 |
| `p50_ms` | 41.0000 |
| `p95_ms` | 86.5900 |
| `max_ms` | 87.0900 |
| `kb_refresh_ms` | 146.8300 |

## Endpoint Latency

| Endpoint | Requests | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
| `/api/v1/chat/runs` | 3 | 18.1300 | 40.4400 | 40.4400 |
| `/api/v1/tasks/code-generate` | 3 | 86.5900 | 87.0900 | 87.0900 |
| `/api/v1/tasks/code-review` | 2 | 45.0600 | 48.5600 | 48.5600 |
| `/api/v1/tasks/config-generate` | 1 | 60.3000 | 60.3000 | 60.3000 |
| `/api/v1/tasks/config-validate` | 1 | 14.1000 | 14.1000 | 14.1000 |
| `/api/v1/tasks/logs-analyze` | 2 | 54.6100 | 55.2800 | 55.2800 |
| `/api/v1/tasks/project-qa` | 8 | 33.4700 | 52.0700 | 52.0700 |

## Knowledge Base Snapshot

- Documents: `33`
- Chunks: `46`
- Effective mode: `lexical`
- Searchable local files: `34`

## Notes

- Recall and precision are computed from expected source files in eval datasets.
- Precision@K is strict: with one expected file and top_k=4, its ceiling is 0.25 even for a perfect top-1 hit.
- For sparse labels, read Top1, MRR, Hit@K, and normalized_precision_at_k together with Precision@K.
- This report is a local benchmark for portfolio/interview demonstration, not a production SLA.
- Use it as a baseline before and after RAG, routing, context, or performance optimizations.
