# UE Agent Backend Benchmark Report

## Summary

- Generated at: `2026-04-30T06:50:45.065524+00:00`
- Source paths: `../backend.md, ./docs, ./knowledge`
- RAG datasets: `tests/eval/rag_project_qa_dataset.jsonl, tests/eval/rag_ue_knowledge_dataset.jsonl`
- Task datasets: `tests/eval/intent_language_dataset.jsonl, tests/eval/code_generate_dataset.jsonl, tests/eval/code_review_dataset.jsonl, tests/eval/logs_analyze_dataset.jsonl, tests/eval/config_task_dataset.jsonl`
- LLM mode: `offline_fallback`

## RAG Retrieval Quality

| Metric | Value | Meaning |
| --- | ---: | --- |
| `cases` | 8 | Evaluation case count. |
| `recall_at_k` | 0.6875 | How many expected sources were recovered in top-k. |
| `precision_at_k` | 0.1875 | How many top-k results were relevant. |
| `hit_at_k` | 0.7500 | Whether each case hit at least one expected source. |
| `mrr` | 0.6667 | How early the first relevant source appeared. |
| `ndcg_at_k` | 0.6633 | Ranking quality with position discount. |
| `route_accuracy` | 1.0000 | Whether route_type matched expectation. |
| `language_accuracy` | 1.0000 | Whether output language matched expectation. |
| `citation_coverage` | 1.0000 | Whether responses included citations. |
| `no_result_ratio` | 0.2500 | Share of cases without a relevant hit. |

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
| `p50_ms` | 2505.1800 |
| `p95_ms` | 2872.0300 |
| `max_ms` | 2889.8300 |
| `kb_refresh_ms` | 3246.9200 |

## Endpoint Latency

| Endpoint | Requests | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
| `/api/v1/chat/runs` | 3 | 15.8000 | 2489.1100 | 2489.1100 |
| `/api/v1/tasks/code-generate` | 3 | 2872.0300 | 2889.8300 | 2889.8300 |
| `/api/v1/tasks/code-review` | 2 | 2497.2600 | 2499.8100 | 2499.8100 |
| `/api/v1/tasks/config-generate` | 1 | 2655.0300 | 2655.0300 | 2655.0300 |
| `/api/v1/tasks/config-validate` | 1 | 14.2400 | 14.2400 | 14.2400 |
| `/api/v1/tasks/logs-analyze` | 2 | 2671.1100 | 2680.9400 | 2680.9400 |
| `/api/v1/tasks/project-qa` | 8 | 2505.1800 | 2526.2200 | 2526.2200 |

## Knowledge Base Snapshot

- Documents: `42`
- Chunks: `90`
- Effective mode: `lexical`
- Searchable local files: `304`

## Notes

- Recall and precision are computed from expected source files in eval datasets.
- This report is a local benchmark for portfolio/interview demonstration, not a production SLA.
- Use it as a baseline before and after RAG, routing, context, or performance optimizations.
