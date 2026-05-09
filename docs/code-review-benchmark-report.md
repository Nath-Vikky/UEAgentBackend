# Code Review Benchmark Report

- Generated at: `2026-05-09T05:32:55.805010+00:00`
- Dataset: `tests\eval\code_review_benchmark_dataset.jsonl`
- Cases: `20`
- LLM mode: `disabled/offline`

## Aggregate Metrics

| Metric | Single Review | Multi-Agent Review Phase |
| --- | ---: | ---: |
| Recall | 1.0 | 1.0 |
| Precision | 1.0 | 1.0 |
| False positive rate | 0.0 | 0.0 |
| Clean-case accuracy | 1.0 | 1.0 |

## Chain Value

- Review detection ratio: `1.0`
- Generated draft case rate: `0.35`
- Validation issues per generated file: `1.5`
- Note: The chain intentionally reuses the same review detector; extra value is measured by fix-draft and validation coverage.

## Latency

| Metric | Single Review | Multi-Agent Chain |
| --- | ---: | ---: |
| Average latency ms | 34.47 | 42.69 |
| Max latency ms | 154.12 | 87.26 |

## LLM Hallucination

- Rate: `None`
- Note: Offline benchmark disables LLM calls; use a separate live LLM eval set to measure hallucination.

## Per-Case Details

| Case | Expected | Single actual | Single R/P | Chain actual | Chain R/P | Chain status |
| --- | --- | --- | ---: | --- | ---: | --- |
| raw-pointer-tick-load | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage, tick_hot_path | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage, tick_hot_path | 1.0/1.0 | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage, tick_hot_path | 1.0/1.0 | completed |
| background-thread-uobject | raw_pointer_ownership, thread_context | raw_pointer_ownership, thread_context | 1.0/1.0 | raw_pointer_ownership, thread_context | 1.0/1.0 | completed |
| blueprint-api-surface | blueprint_surface | blueprint_surface | 1.0/1.0 | blueprint_surface | 1.0/1.0 | completed |
| include-pollution | include_pollution | include_pollution | 1.0/1.0 | include_pollution | 1.0/1.0 | completed |
| hardcoded-path-only | hardcoded_asset_path | hardcoded_asset_path | 1.0/1.0 | hardcoded_asset_path | 1.0/1.0 | completed |
| tryload-sync-reference | raw_pointer_ownership, sync_load_usage | raw_pointer_ownership, sync_load_usage | 1.0/1.0 | raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| clean-helper | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| std-thread-risk | raw_pointer_ownership, thread_context | raw_pointer_ownership, thread_context | 1.0/1.0 | raw_pointer_ownership, thread_context | 1.0/1.0 | completed |
| static-load-object | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| tick-config-only | tick_hot_path | tick_hot_path | 1.0/1.0 | tick_hot_path | 1.0/1.0 | completed |
| clean-uproperty-uobject-pointer | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-tobjectptr-array | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-soft-reference-dataasset | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-gamethread-async-task | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-comments-with-rule-words | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-small-include-surface | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-blueprint-readonly-config | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-data-table-row | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| frunnable-thread-review | thread_context | thread_context | 1.0/1.0 | thread_context | 1.0/1.0 | completed |
| blueprint-callable-load-path | blueprint_surface, hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | blueprint_surface, hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | blueprint_surface, hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |

## Interpretation

- This benchmark is designed for local, deterministic regression checks and does not require an API key.
- Recall/precision measure rule-family detection against synthetic UE C++ snippets.
- Multi-agent detection is expected to match single review because the chain reuses the same reviewer before fix generation and validation.
