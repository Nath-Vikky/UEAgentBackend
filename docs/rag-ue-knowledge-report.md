# RAG Eval Report

## Summary

- Generated at: `2026-06-04T15:47:52.133743+00:00`
- Dataset: `tests\eval\rag_ue_knowledge_dataset.jsonl`
- Source paths: `./knowledge`
- Top K: `4`

| Metric | Value |
| --- | ---: |
| `cases` | 9 |
| `recall_at_k` | 0.9444 |
| `precision_at_k` | 0.2778 |
| `precision_at_retrieved` | 0.4167 |
| `labeled_precision_ceiling` | 0.3056 |
| `normalized_precision_at_k` | 0.9444 |
| `hit_at_k` | 1.0000 |
| `top1_accuracy` | 0.8889 |
| `mrr` | 0.9444 |
| `ndcg_at_k` | 0.9319 |
| `route_accuracy` | 1.0000 |
| `language_accuracy` | 1.0000 |
| `citation_coverage` | 1.0000 |
| `low_confidence_ratio` | 0.0000 |
| `no_result_ratio` | 0.0000 |

## Cases

| Case | Route | Language | Confidence | Hit@K | Top1 | MRR | Matched Sources |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `ue-gas-zh` | ok | ok | 0.6590 | 1.0000 | 1.0000 | 1.0000 | uecpp-async-networking-gas.md |
| `ue-threading-zh` | ok | ok | 0.6900 | 1.0000 | 1.0000 | 1.0000 | uecpp-async-networking-gas.md |
| `ue-reflection-zh` | ok | ok | 0.6500 | 1.0000 | 1.0000 | 1.0000 | uecpp-reflection-containers-delegates.md |
| `ue-http-zh` | ok | ok | 0.6950 | 1.0000 | 0.0000 | 0.5000 | uecpp-http-websocket-asyncaction-note.md |
| `ue-enhanced-input-en` | ok | ok | 0.7040 | 1.0000 | 1.0000 | 1.0000 | ue-enhanced-input-character.md, enhanced-input-character-example.cpp |
| `ue-umg-layout-en` | ok | ok | 0.7140 | 1.0000 | 1.0000 | 1.0000 | ue-umg-widget-layout-patterns.md |
| `ue-blueprint-graph-template-en` | ok | ok | 0.6970 | 1.0000 | 1.0000 | 1.0000 | ue-blueprint-graph-safe-templates.md |
| `ue-material-instance-parameters-en` | ok | ok | 0.7500 | 1.0000 | 1.0000 | 1.0000 | ue-material-instance-parameters.md |
| `ue-editor-operation-troubleshooting-en` | ok | ok | 0.5930 | 1.0000 | 1.0000 | 1.0000 | ue-editor-operation-troubleshooting.md |

## Notes

- This is an offline local evaluation for regression and project quality checks.
- Metrics focus on retrieval hit quality, routing correctness, citation coverage, and low-confidence detection.
- It is not an online production monitoring or A/B testing system.
