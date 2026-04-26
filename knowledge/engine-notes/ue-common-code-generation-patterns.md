# UE Common Code Generation Patterns

source_url_subsystems: https://dev.epicgames.com/documentation/en-us/unreal-engine/programming-subsystems-in-unreal-engine
source_url_actor_components: https://dev.epicgames.com/documentation/en-us/unreal-engine/components-in-unreal-engine
source_url_traces: https://dev.epicgames.com/documentation/en-us/unreal-engine/traces-in-unreal-engine-overview
created_on: 2026-04-26
domain: engine_notes
topic: Actor Component, Line Trace Interaction, GameInstanceSubsystem, DataAsset, Gameplay Tags
keywords: actor component, UActorComponent, overlap, line trace, LineTraceSingleByChannel, subsystem, GameInstanceSubsystem, DataAsset, GameplayTag, 交互组件, 射线交互, 子系统, 数据资产, 玩法标签
use_for: Code Generate, Project QA, Code Review

## Summary

The local code generation knowledge base should prefer small, reusable Unreal patterns instead of large project templates. For portfolio-level generation, the most useful patterns are interaction components, line trace helpers, subsystem managers, and data-driven configuration notes.

## Pattern Boundaries

- Actor Component: good for reusable behavior attached to actors. Keep it independent from one specific pawn or level.
- Line Trace Interaction: good for first-person or third-person interaction queries. Return the hit actor, then let project code decide what interface or action to call.
- GameInstanceSubsystem: good for app/session-wide managers that survive map travel. Avoid holding strong references to level actors unless cleanup is explicit.
- DataAsset: good for designer-authored configuration. Generated code should define shape and usage, not create assets on disk.
- Gameplay Tags: good for stable labels and filtering. Generated snippets should remind users to define tags in project settings or tag tables.

## Code Generation Hints

- Prefer `Source/<Module>/Public` for headers and `Source/<Module>/Private` for implementation files.
- Include concrete method bodies and TODO comments for project-specific hooks.
- Explain required editor setup separately from generated C++.
- Do not claim the backend writes files or modifies the project.

