# DataAsset And Gameplay Tag Code Generation Note

domain: examples
topic: DataAsset, Gameplay Tags, data driven configuration
keywords: UDataAsset, UPrimaryDataAsset, GameplayTag, FGameplayTag, data driven, 数据资产, 玩法标签, 配置驱动
use_for: Code Generate, Project QA, Code Review

## Minimal Guidance

Use a `UPrimaryDataAsset` or `UDataAsset` when designers need to edit reusable configuration in the editor. Use `FGameplayTag` when gameplay code needs stable semantic labels instead of string comparisons or enum sprawl.

## Code Generation Hints

- Generate a small data shape first: asset id, display name, gameplay tag, icon/mesh/soft references, and numeric tuning values.
- Prefer `TSoftObjectPtr` for optional assets that do not need to load immediately.
- Remind the user to create the DataAsset asset in the editor; the backend should not create `.uasset` files.
- Remind the user to define gameplay tags in Project Settings or a tag table before using them heavily.

