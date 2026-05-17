# Code Review Benchmark Report

- Generated at: `2026-05-17T04:22:20.279046+00:00`
- Dataset: `tests\eval\code_review_benchmark_dataset.jsonl`
- Cases: `26`
- LLM mode: `disabled/offline`

## Aggregate Metrics

| Metric | Single Review | Multi-Agent Review Phase |
| --- | ---: | ---: |
| Recall | 0.9355 | 0.9355 |
| Precision | 1.0 | 1.0 |
| False positive rate | 0.0 | 0.0 |
| Clean-case accuracy | 1.0 | 1.0 |

## Known Limitations Included

- Cases: `2`
- Single-review missing expected rule families in known limitations: `2`
- Multi-agent missing expected rule families in known limitations: `2`
- Note: Known limitation cases are intentionally included to make the benchmark reflect current lightweight-rule boundaries.

## Chain Value

- Review detection ratio: `1.0`
- Generated draft case rate: `0.3077`
- Validation issues per generated file: `1.5`
- Note: The chain intentionally reuses the same review detector; extra value is measured by fix-draft and validation coverage.

## Latency

| Metric | Single Review | Multi-Agent Chain |
| --- | ---: | ---: |
| Average latency ms | 32.29 | 41.88 |
| Max latency ms | 152.81 | 82.02 |

## LLM Hallucination

- Rate: `None`
- Note: Offline benchmark disables LLM calls; use a separate live LLM eval set to measure hallucination.

## Per-Case Details

| Case | Type | Expected | Single actual | Single R/P | Chain actual | Chain R/P | Chain status |
| --- | --- | --- | --- | ---: | --- | ---: | --- |
| raw-pointer-tick-load | regression | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage, tick_hot_path | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage, tick_hot_path | 1.0/1.0 | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage, tick_hot_path | 1.0/1.0 | completed |
| background-thread-uobject | regression | raw_pointer_ownership, thread_context | raw_pointer_ownership, thread_context | 1.0/1.0 | raw_pointer_ownership, thread_context | 1.0/1.0 | completed |
| blueprint-api-surface | regression | blueprint_surface | blueprint_surface | 1.0/1.0 | blueprint_surface | 1.0/1.0 | completed |
| include-pollution | regression | include_pollution | include_pollution | 1.0/1.0 | include_pollution | 1.0/1.0 | completed |
| hardcoded-path-only | regression | hardcoded_asset_path | hardcoded_asset_path | 1.0/1.0 | hardcoded_asset_path | 1.0/1.0 | completed |
| tryload-sync-reference | regression | raw_pointer_ownership, sync_load_usage | raw_pointer_ownership, sync_load_usage | 1.0/1.0 | raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| clean-helper | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| std-thread-risk | regression | raw_pointer_ownership, thread_context | raw_pointer_ownership, thread_context | 1.0/1.0 | raw_pointer_ownership, thread_context | 1.0/1.0 | completed |
| static-load-object | regression | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| tick-config-only | regression | tick_hot_path | tick_hot_path | 1.0/1.0 | tick_hot_path | 1.0/1.0 | completed |
| clean-uproperty-uobject-pointer | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-tobjectptr-array | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-soft-reference-dataasset | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-gamethread-async-task | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-comments-with-rule-words | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-small-include-surface | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-blueprint-readonly-config | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| clean-data-table-row | regression | - | - | 1.0/1.0 | - | 1.0/1.0 | completed |
| frunnable-thread-review | regression | thread_context | thread_context | 1.0/1.0 | thread_context | 1.0/1.0 | completed |
| blueprint-callable-load-path | regression | blueprint_surface, hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | blueprint_surface, hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | blueprint_surface, hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| constructorhelpers-fobjectfinder | regression_from_known_gap | hardcoded_asset_path, sync_load_usage | hardcoded_asset_path, sync_load_usage | 1.0/1.0 | hardcoded_asset_path, sync_load_usage | 1.0/1.0 | completed |
| loadclass-blueprint | regression_from_known_gap | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | 1.0/1.0 | completed |
| missing-super-beginplay | regression_from_known_gap | lifecycle_super_call | lifecycle_super_call | 1.0/1.0 | lifecycle_super_call | 1.0/1.0 | completed |
| delegate-bind-without-unbind | regression_from_known_gap | delegate_lifetime | delegate_lifetime | 1.0/1.0 | delegate_lifetime | 1.0/1.0 | completed |
| known-gap-request-sync-load | known_limitation | sync_load_usage | - | 0.0/0.0 | - | 0.0/0.0 | completed |
| known-gap-replicated-property-no-lifetime | known_limitation | replication_lifetime | - | 0.0/0.0 | - | 0.0/0.0 | completed |

## Known Limitation Case Notes

- `known-gap-request-sync-load` missing `sync_load_usage`: The lightweight detector currently catches common LoadObject/LoadClass/TryLoad/ConstructorHelpers patterns but does not classify RequestSyncLoad yet.
- `known-gap-replicated-property-no-lifetime` missing `replication_lifetime`: Replication lifetime validation needs class-level context and is intentionally tracked as a future rule family.

## Interpretation

- This benchmark is designed for local, deterministic regression checks and does not require an API key.
- Recall/precision measure rule-family detection against synthetic UE C++ snippets.
- Multi-agent detection is expected to match single review because the chain reuses the same reviewer before fix generation and validation.
