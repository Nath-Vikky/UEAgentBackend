# UE Agent Backend Benchmark Report

## Summary

- Generated at: `2026-05-09T05:32:55.928720+00:00`
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
| `cases` | 15 | Hallucination guard case count. |
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
| `requests` | 35 |
| `p50_ms` | 39.4000 |
| `p95_ms` | 108.3000 |
| `max_ms` | 115.9200 |
| `kb_refresh_ms` | 141.5900 |

## Endpoint Latency

| Endpoint | Requests | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
| `/api/v1/chat/runs` | 3 | 18.2000 | 41.8800 | 41.8800 |
| `/api/v1/tasks/code-generate` | 3 | 108.3000 | 115.9200 | 115.9200 |
| `/api/v1/tasks/code-review` | 2 | 44.5300 | 46.0200 | 46.0200 |
| `/api/v1/tasks/config-generate` | 1 | 53.0500 | 53.0500 | 53.0500 |
| `/api/v1/tasks/config-validate` | 1 | 15.4500 | 15.4500 | 15.4500 |
| `/api/v1/tasks/logs-analyze` | 2 | 53.9400 | 54.1500 | 54.1500 |
| `/api/v1/tasks/project-qa` | 23 | 32.7000 | 54.9400 | 88.3800 |

## Knowledge Base Snapshot

- Documents: `33`
- Chunks: `47`
- Effective mode: `lexical`
- Searchable local files: `34`

## Notes

- Recall and precision are computed from expected source files in eval datasets.
- Precision@K is strict: with one expected file and top_k=4, its ceiling is 0.25 even for a perfect top-1 hit.
- For sparse labels, read Top1, MRR, Hit@K, and normalized_precision_at_k together with Precision@K.
- This report is a local regression benchmark for project quality checks, not a production SLA.
- Use it as a baseline before and after RAG, routing, context, or performance optimizations.
