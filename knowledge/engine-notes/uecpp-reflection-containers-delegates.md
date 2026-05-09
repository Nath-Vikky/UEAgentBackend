# UE C++ Reflection, Containers, Delegates, And Text Types

source_note: distilled from local UE C++ course notes and rewritten for this project knowledge base
scope: local UE knowledge base
license_check: source repository says course materials are for purchased learners; this file is an original summary, not a copied chapter
domain: engine_notes
topic: reflection, UObject, containers, delegates, strings, timers, gameplay tags
use_for: Project QA, Code Generate, Code Review

## Retrieval Aliases

reflection, UCLASS, USTRUCT, UENUM, UPROPERTY, UFUNCTION, UObject, CDO, GC, TArray, TMap, TSet, delegate, multicast delegate, dynamic delegate, FString, FName, FText, GameplayTag, FGameplayTag, timer, FTimerManager

## Reflection Boundary

Use UE reflection macros when data must be visible to the editor, Blueprint, serialization, garbage collection, networking, or asset references.

- `UCLASS` is for UObject-derived types such as Actor, Component, Subsystem, DataAsset, and Blueprint-facing objects.
- `USTRUCT` is good for value data, config rows, replicated payloads, and compact editor-editable records.
- `UENUM` is good for finite user-facing options; prefer Gameplay Tags when designers need a large extensible taxonomy.
- `UPROPERTY` is required for UObject references that must be tracked by GC, edited in the editor, serialized, or replicated.
- `UFUNCTION` is required for Blueprint-callable functions, RPC, reflected delegates, and editor-exposed commands.
- `CDO` stores class defaults; avoid treating defaults as per-instance runtime state.

## Container Selection

- Choose `TArray` by default when order matters or the collection is small enough for linear search.
- Choose `TMap` when lookup by key is the main operation.
- Choose `TSet` for uniqueness and membership checks.
- For UObject references in reflected containers, prefer `TObjectPtr<T>` in UE5 code when possible.
- For assets that should not be loaded immediately, prefer `TSoftObjectPtr` or `TSoftClassPtr`.

## Delegates

- Native single-cast delegates are best for one C++ callback owner.
- Native multicast delegates are good for internal C++ event fan-out.
- Dynamic delegates are serializable and Blueprint-friendly, but slower and require reflected function signatures.
- Dynamic multicast delegates are appropriate for Blueprint event dispatchers and async Blueprint nodes.
- Always unbind delegates when the lifetime owner can disappear before the broadcaster.

## Strings And Text

- `FString` is mutable text and works well for parsing, formatting, and transport payloads.
- `FName` is an immutable identifier and works well for asset names, row names, gameplay tags internals, and reflection names.
- `FText` is localized display text; use it for UI, not as a stable key.
- Use UTF-8/TCHAR conversion helpers at module boundaries rather than mixing `std::string` and `FString` freely.

## Timer And Gameplay Tag Notes

- Use `FTimerManager` for delayed or repeated gameplay actions instead of enabling Tick for simple polling.
- Store the `FTimerHandle` when a timer may need to be cancelled.
- `FGameplayTag` is better than raw strings for gameplay state labels, ability categories, item tags, and filtering.
- Define tags in Project Settings or tag tables; code should request and validate tags rather than inventing ad-hoc strings.
