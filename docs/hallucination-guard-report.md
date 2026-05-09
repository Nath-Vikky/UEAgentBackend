# Hallucination Guard Eval Report

## Summary

- Generated at: `2026-05-09T05:32:43.163326+00:00`
- Dataset: `tests/eval/hallucination_guard_dataset.jsonl`
- Source paths: `./README.md, ./docs, ./knowledge`
- LLM mode: `offline_fallback`

| Metric | Value | Meaning |
| --- | ---: | --- |
| `cases` | 15 | Evaluation case count. |
| `grounding_accuracy` | 1.0000 | Share of cases that followed the expected grounding behavior. |
| `route_accuracy` | 1.0000 | Share of cases routed to the expected task route. |
| `unsupported_answer_rate` | 0.0000 | Share of abstention cases that still made unsupported claims. |
| `abstention_accuracy` | 1.0000 | Share of no-evidence cases that clearly refused or asked for more evidence. |
| `grounded_answer_accuracy` | 1.0000 | Share of evidence-backed cases with citations and expected sources. |
| `knowledge_catalog_accuracy` | 1.0000 | Share of catalog questions answered as catalog, not raw file dumps. |
| `citation_coverage` | 0.6000 | Share of all cases with citation objects. |

## Cases

| Case | Expected | OK | Confidence | Grounding | Sources | Failed checks |
| --- | --- | ---: | ---: | --- | --- | --- |
| `unsupported-current-blueprint-zh` | `abstain` | yes | 0.1200 | `insufficient_evidence` | - | - |
| `unsupported-unknown-ue-api-zh` | `abstain` | yes | 0.1200 | `insufficient_evidence` | - | - |
| `grounded-actor-lifecycle-zh` | `grounded_answer` | yes | 0.7160 | `project_grounded` | `ue-actor-lifecycle.md` | - |
| `grounded-enhanced-input-code-zh` | `grounded_answer` | yes | 0.7400 | `project_grounded` | `ue-enhanced-input-character.md`, `enhanced-input-character-example.h`, `enhanced-input-character-example.cpp` | - |
| `knowledge-catalog-no-raw-code-zh` | `knowledge_catalog` | yes | 0.8200 | `insufficient_evidence` | - | - |
| `unsupported-current-material-textures-zh` | `abstain` | yes | 0.1200 | `insufficient_evidence` | - | - |
| `unsupported-selected-staticmesh-nanite-zh` | `abstain` | yes | 0.1200 | `insufficient_evidence` | - | - |
| `unsupported-unknown-replication-api-zh` | `abstain` | yes | 0.1200 | `insufficient_evidence` | - | - |
| `unsupported-specific-team-rule-zh` | `abstain` | yes | 0.1200 | `insufficient_evidence` | - | - |
| `grounded-gas-core-zh` | `grounded_answer` | yes | 0.6600 | `project_grounded` | `uecpp-async-networking-gas.md` | - |
| `grounded-threading-choice-zh` | `grounded_answer` | yes | 0.6900 | `project_grounded` | `uecpp-async-networking-gas.md`, `uecpp-review-threading-networking-rules.md` | - |
| `grounded-http-modules-zh` | `grounded_answer` | yes | 0.7010 | `project_grounded` | `uecpp-http-websocket-asyncaction-note.md` | - |
| `grounded-soft-reference-loading-zh` | `grounded_answer` | yes | 0.6840 | `project_grounded` | `async-asset-loading-example.md`, `ue-soft-references-async-loading.md` | - |
| `knowledge-catalog-code-reference-zh` | `knowledge_catalog` | yes | 0.8200 | `insufficient_evidence` | - | - |
| `knowledge-catalog-documents-en` | `knowledge_catalog` | yes | 0.8200 | `insufficient_evidence` | - | - |

## Notes

- This eval focuses on whether the backend refuses unsupported project facts, preserves catalog answers, and uses citations for grounded answers.
- It is deterministic by default: live LLM calls are disabled unless `--use-live-llm` is passed.
- Read this report together with `docs/benchmark-report.md` for recall, precision, routing, task success, and latency metrics.
