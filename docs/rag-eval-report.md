# RAG Eval Report

## Summary

- Generated at: `2026-04-27T14:33:02.001022+00:00`
- Dataset: `tests\eval\rag_project_qa_dataset.jsonl`
- Source paths: `..\backend.md, .\docs, .\knowledge`
- Top K: `4`

| Metric | Value |
| --- | ---: |
| `cases` | 4 |
| `recall_at_k` | 0.5000 |
| `precision_at_k` | 0.1250 |
| `hit_at_k` | 0.5000 |
| `mrr` | 0.5000 |
| `ndcg_at_k` | 0.5000 |
| `route_accuracy` | 1.0000 |
| `language_accuracy` | 0.5000 |
| `citation_coverage` | 1.0000 |
| `low_confidence_ratio` | 0.0000 |
| `no_result_ratio` | 0.5000 |

## Cases

| Case | Route | Language | Confidence | Hit@K | MRR | Matched Sources |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `dual-views-zh` | ok | ok | 0.6240 | 1.0000 | 1.0000 | backend.md |
| `language-policy-en` | ok | expected en-US | 0.5050 | 1.0000 | 1.0000 | backend.md |
| `frontend-handoff-zh` | ok | ok | 0.5750 | 0.0000 | 0.0000 | - |
| `backend-guide-en` | ok | expected en-US | 0.8200 | 0.0000 | 0.0000 | - |

## Notes

- This is an offline local evaluation for portfolio/interview demonstration.
- Metrics focus on retrieval hit quality, routing correctness, citation coverage, and low-confidence detection.
- It is not an online production monitoring or A/B testing system.
