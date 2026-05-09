# UE Agent Backend Benchmark Report

## Summary

- Generated at: `2026-05-09T04:18:02.196918+00:00`
- Source paths: `./README.md, ./docs, ./knowledge`
- RAG datasets: `tests/eval/rag_project_qa_dataset.jsonl, tests/eval/rag_ue_knowledge_dataset.jsonl`
- Task datasets: `tests/eval/intent_language_dataset.jsonl, tests/eval/code_generate_dataset.jsonl, tests/eval/code_review_dataset.jsonl, tests/eval/logs_analyze_dataset.jsonl, tests/eval/config_task_dataset.jsonl`
- Hallucination dataset: `tests/eval/hallucination_guard_dataset.jsonl`
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
| `mrr` | 0.9375 | How early the first relevant source appeared. |
| `ndcg_at_k` | 0.9234 | Ranking quality with position discount. |
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

## Hallucination Guard Quality

| Metric | Value | Meaning |
| --- | ---: | --- |
| `cases` | 5 | Hallucination guard case count. |
| `grounding_accuracy` | 1.0000 | Expected grounding behavior: grounded answer, abstention, or catalog answer. |
| `route_accuracy` | 1.0000 | Route matched expected workflow. |
| `unsupported_answer_rate` | 0.0000 | No-evidence cases that still made unsupported claims. |
| `abstention_accuracy` | 1.0000 | No-evidence cases that refused or asked for more evidence. |
| `grounded_answer_accuracy` | 1.0000 | Evidence-backed cases with citations and expected sources. |
| `knowledge_catalog_accuracy` | 1.0000 | Catalog questions answered as catalog, not raw file dumps. |
| `citation_coverage` | 0.6000 | Cases with citation objects. |

## Runtime Performance

| Metric | Value |
| --- | ---: |
| `requests` | 25 |
| `p50_ms` | 40.6500 |
| `p95_ms` | 108.8900 |
| `max_ms` | 118.4100 |
| `kb_refresh_ms` | 137.4300 |

## Endpoint Latency

| Endpoint | Requests | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
| `/api/v1/chat/runs` | 3 | 17.8300 | 40.6500 | 40.6500 |
| `/api/v1/tasks/code-generate` | 3 | 108.8900 | 118.4100 | 118.4100 |
| `/api/v1/tasks/code-review` | 2 | 48.8700 | 51.0700 | 51.0700 |
| `/api/v1/tasks/config-generate` | 1 | 54.5900 | 54.5900 | 54.5900 |
| `/api/v1/tasks/config-validate` | 1 | 14.2300 | 14.2300 | 14.2300 |
| `/api/v1/tasks/logs-analyze` | 2 | 52.1600 | 53.6000 | 53.6000 |
| `/api/v1/tasks/project-qa` | 13 | 30.2300 | 54.3500 | 54.3500 |

## Knowledge Base Snapshot

- Documents: `32`
- Chunks: `45`
- Effective mode: `lexical`
- Searchable local files: `33`

## Notes

- Recall and precision are computed from expected source files in eval datasets.
- Precision@K is strict: with one expected file and top_k=4, its ceiling is 0.25 even for a perfect top-1 hit.
- For sparse labels, read Top1, MRR, Hit@K, and normalized_precision_at_k together with Precision@K.
- This report is a local regression benchmark for project quality checks, not a production SLA.
- Use it as a baseline before and after RAG, routing, context, or performance optimizations.
