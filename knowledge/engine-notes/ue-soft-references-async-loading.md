# UE Soft References And Async Loading Notes

source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/asynchronous-asset-loading-in-unreal-engine
source_url_asset_references: https://dev.epicgames.com/documentation/en-us/unreal-engine/referencing-assets-in-unreal-engine
source_url_api_load_async: https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/CoreUObject/UObject/FSoftObjectPath/LoadAsync
created_on: 2026-04-25
domain: engine_notes
topic: soft object reference, TSoftObjectPtr, FSoftObjectPath, async asset loading
use_for: Code Review, Code Generate, Project QA

## Summary

Hard references can cause assets to load as soon as the owning object loads. Soft references store an indirect reference and let gameplay code decide when to load the asset. For runtime loading, prefer asynchronous loading when a blocking load could cause hitches.

## Key Points

- `UPROPERTY` hard object pointers are convenient but can pull referenced assets into memory early.
- `TSoftObjectPtr` and `FSoftObjectPath` are useful when designers need to assign assets without forcing immediate load.
- Blocking load helpers are simple but can hitch if called during gameplay or editor interaction.
- Async loading should update state through a completion callback and handle failure paths.

## Code Review Heuristics

- Flag synchronous loads inside `Tick`, input handlers, animation update paths, or frequently called UI code.
- Prefer soft references for configurable assets that do not need to be loaded with the owner.
- Keep loaded asset references as `UPROPERTY` or managed pointers when they must stay alive.
- Document intentional blocking loads and keep them outside hot paths.

## Code Generation Guidance

- For a generated Actor that references optional content, expose `TSoftObjectPtr<UObject>` or a typed soft pointer.
- Start async load in `BeginPlay` or a deliberate initialization method, not the constructor.
- Include a clear callback path for success and failure.

