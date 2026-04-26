# UE Actor Lifecycle Notes

source_url: https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-actor-lifecycle
source_url_api_begin_play: https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/GameFramework/AActor/BeginPlay
created_on: 2026-04-25
domain: engine_notes
topic: actor lifecycle, BeginPlay, Tick, EndPlay, garbage collection
use_for: Code Review, Code Generate, Project QA

## Summary

Actor lifecycle review should separate construction-time setup, runtime initialization, per-frame work, and teardown. In code review, be cautious when constructors touch runtime-only world state, when `Tick` performs heavy work, and when `EndPlay` cleanup assumes the object is immediately destroyed.

## Key Points

- `BeginPlay` is the usual place for runtime initialization once play begins.
- `Tick` can run every frame, so asset loading, expensive searches, synchronous IO, and repeated allocation should be challenged.
- `EndPlay` can happen for several reasons, including explicit destroy, level transitions, PIE ending, streaming unload, lifetime expiry, or shutdown.
- An Actor may be marked for garbage collection after its ending path; use weak references when another object may outlive it.
- Constructor code should focus on default subobject creation and defaults, not runtime lookups that require a fully active world.

## Review Heuristics

- Flag `LoadObject`, `StaticLoadObject`, `TryLoad`, or heavy iteration inside `Tick`.
- Ask whether `PrimaryActorTick.bCanEverTick = true` is necessary.
- Prefer event-driven or timer-driven logic when work does not need every-frame updates.
- Confirm `EndPlay` cleanup is idempotent and safe across streaming or PIE transitions.

