# Code Review Benchmark Report

- Generated at: `2026-05-08T07:08:02.826668+00:00`
- Dataset: `tests\eval\code_review_benchmark_dataset.jsonl`
- Cases: `10`
- LLM mode: `disabled/offline`

## Aggregate Metrics

| Metric | Single Review | Multi-Agent Review Phase |
| --- | ---: | ---: |
| Recall | 1.0 | 1.0 |
| Precision | 0.9444 | 0.9444 |
| False positive rate | 0.0556 | 0.0556 |
| Clean-case accuracy | 1.0 | 1.0 |

## Chain Value

- Review detection ratio: `1.0`
- Generated draft case rate: `0.6`
- Validation issues per generated file: `1.5`
- Note: The chain intentionally reuses the same review detector; extra value is measured by fix-draft and validation coverage.

## Latency

| Metric | Single Review | Multi-Agent Chain |
| --- | ---: | ---: |
| Average latency ms | 67.74 | 85.83 |
| Max latency ms | 284.7 | 146.46 |

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
| hardcoded-path-only | hardcoded_asset_path | hardcoded_asset_path, raw_pointer_ownership | 1.0/0.5 | hardcoded_asset_path, raw_pointer_ownership | 1.0/0.5 | completed |
| tryload-sync-reference | raw_pointer_ownership, sync_load_usage | raw_pointer_ownership, sync_load_usage | 1.0/1.0 | raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| clean-helper | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| std-thread-risk | raw_pointer_ownership, thread_context | raw_pointer_ownership, thread_context | 1.0/1.0 | raw_pointer_ownership, thread_context | 1.0/1.0 | completed |
| static-load-object | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| tick-config-only | tick_hot_path | tick_hot_path | 1.0/1.0 | tick_hot_path | 1.0/1.0 | completed |

## Interpretation

- This benchmark is designed for local, deterministic regression checks and does not require an API key.
- Recall/precision measure rule-family detection against synthetic UE C++ snippets.
- Multi-agent detection is expected to match single review because the chain reuses the same reviewer before fix generation and validation.
