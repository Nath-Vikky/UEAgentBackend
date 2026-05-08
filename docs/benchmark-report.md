# UE Agent Backend Benchmark Report

## Summary

- Generated at: `2026-05-08T09:37:46.504520+00:00`
- Source paths: `./README.md, ./docs, ./knowledge`
- RAG datasets: `tests/eval/rag_project_qa_dataset.jsonl, tests/eval/rag_ue_knowledge_dataset.jsonl`
- Task datasets: `tests/eval/intent_language_dataset.jsonl, tests/eval/code_generate_dataset.jsonl, tests/eval/code_review_dataset.jsonl, tests/eval/logs_analyze_dataset.jsonl, tests/eval/config_task_dataset.jsonl`
- LLM mode: `offline_fallback`

## RAG Retrieval Quality

| Metric | Value | Meaning |
| --- | ---: | --- |
| `cases` | 8 | Evaluation case count. |
| `recall_at_k` | 0.9375 | How many expected sources were recovered in top-k. |
| `precision_at_k` | 0.2500 | How many top-k results were relevant. |
| `hit_at_k` | 1.0000 | Whether each case hit at least one expected source. |
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
| `p50_ms` | 42.5600 |
| `p95_ms` | 79.7500 |
| `max_ms` | 82.8200 |
| `kb_refresh_ms` | 143.8900 |

## Endpoint Latency

| Endpoint | Requests | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
| `/api/v1/chat/runs` | 3 | 20.8600 | 43.1600 | 43.1600 |
| `/api/v1/tasks/code-generate` | 3 | 79.7500 | 82.8200 | 82.8200 |
| `/api/v1/tasks/code-review` | 2 | 47.2100 | 52.4600 | 52.4600 |
| `/api/v1/tasks/config-generate` | 1 | 64.3500 | 64.3500 | 64.3500 |
| `/api/v1/tasks/config-validate` | 1 | 13.0300 | 13.0300 | 13.0300 |
| `/api/v1/tasks/logs-analyze` | 2 | 63.4600 | 64.3100 | 64.3100 |
| `/api/v1/tasks/project-qa` | 8 | 34.2500 | 54.4000 | 54.4000 |

## Knowledge Base Snapshot

- Documents: `33`
- Chunks: `46`
- Effective mode: `lexical`
- Searchable local files: `34`

## Notes

- Recall and precision are computed from expected source files in eval datasets.
- This report is a local benchmark for portfolio/interview demonstration, not a production SLA.
- Use it as a baseline before and after RAG, routing, context, or performance optimizations.
