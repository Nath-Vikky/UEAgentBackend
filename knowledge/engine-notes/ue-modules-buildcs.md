# UE Modules And Build.cs Notes

source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-modules
source_url_ubt: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-build-tool-in-unreal-engine
created_on: 2026-04-25
domain: engine_notes
topic: Unreal modules, Build.cs, PublicDependencyModuleNames, PrivateDependencyModuleNames
use_for: Code Review, Code Generate

## Summary

Unreal modules organize code into compile units and dependency boundaries. A module usually lives under `Source/[ModuleName]`, has a `[ModuleName].Build.cs`, and keeps public headers separate from private implementation files.

## Key Points

- `Build.cs` declares module dependencies and build configuration for UnrealBuildTool.
- Public dependencies should be used when public headers expose types from another module.
- Private dependencies are preferred for implementation-only use because they reduce coupling.
- Forward declarations can help keep dependencies private and reduce compile cost.
- Public and Private folders in a module are about module visibility, not C++ access modifiers.

## Code Review Heuristics

- If a public header includes a heavy type only used by pointer or reference, consider forward declaration.
- If a dependency is only used in `.cpp`, prefer `PrivateDependencyModuleNames`.
- Keep editor-only dependencies out of runtime modules unless explicitly intended.
- In generated code, avoid assuming a module dependency has already been declared.

