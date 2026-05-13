# Code Review Benchmark Report

- Generated at: `2026-05-13T13:16:19.535715+00:00`
- Dataset: `tests\eval\code_review_benchmark_dataset.jsonl`
- Cases: `24`
- LLM mode: `disabled/offline`

## Aggregate Metrics

| Metric | Single Review | Multi-Agent Review Phase |
| --- | ---: | ---: |
| Recall | 0.8621 | 0.8621 |
| Precision | 1.0 | 1.0 |
| False positive rate | 0.0 | 0.0 |
| Clean-case accuracy | 1.0 | 1.0 |

## Known Limitations Included

- Cases: `4`
- Single-review missing expected rule families in known limitations: `4`
- Multi-agent missing expected rule families in known limitations: `4`
- Note: Known limitation cases are intentionally included to make the benchmark reflect current lightweight-rule boundaries.

## Chain Value

- Review detection ratio: `1.0`
- Generated draft case rate: `0.3333`
- Validation issues per generated file: `1.5`
- Note: The chain intentionally reuses the same review detector; extra value is measured by fix-draft and validation coverage.

## Latency

| Metric | Single Review | Multi-Agent Chain |
| --- | ---: | ---: |
| Average latency ms | 33.53 | 39.89 |
| Max latency ms | 156.87 | 75.58 |

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
| known-gap-constructorhelpers-fobjectfinder | known_limitation | hardcoded_asset_path, sync_load_usage | hardcoded_asset_path | 0.5/1.0 | hardcoded_asset_path | 0.5/1.0 | completed |
| known-gap-loadclass-blueprint | known_limitation | hardcoded_asset_path, raw_pointer_ownership, sync_load_usage | hardcoded_asset_path, raw_pointer_ownership | 0.6667/1.0 | hardcoded_asset_path, raw_pointer_ownership | 0.6667/1.0 | completed |
| known-gap-missing-super-beginplay | known_limitation | lifecycle_super_call | - | 0.0/0.0 | - | 0.0/0.0 | completed |
| known-gap-delegate-bind-without-unbind | known_limitation | delegate_lifetime | - | 0.0/0.0 | - | 0.0/0.0 | completed |

## Known Limitation Case Notes

- `known-gap-constructorhelpers-fobjectfinder` missing `sync_load_usage`: The current lightweight detector catches the /Game path but does not classify ConstructorHelpers as sync_load_usage yet.
- `known-gap-loadclass-blueprint` missing `sync_load_usage`: The current detector flags the raw UClass pointer and hardcoded path, but LoadClass is not yet mapped to sync_load_usage.
- `known-gap-missing-super-beginplay` missing `lifecycle_super_call`: Lifecycle super-call checks are intentionally not implemented in the current regex rule set.
- `known-gap-delegate-bind-without-unbind` missing `delegate_lifetime`: Delegate lifetime analysis requires cross-function or lifecycle context and is tracked as a future rule family.

## Interpretation

- This benchmark is designed for local, deterministic regression checks and does not require an API key.
- Recall/precision measure rule-family detection against synthetic UE C++ snippets.
- Multi-agent detection is expected to match single review because the chain reuses the same reviewer before fix generation and validation.
