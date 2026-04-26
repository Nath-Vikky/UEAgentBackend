# UE Code Review Rules

domain: team_rules
topic: code review, Unreal C++, Tick, UObject lifetime, module dependencies
use_for: Code Review

## Rules

- Do not perform synchronous asset loading in `Tick`, animation update, input handlers, or other hot paths.
- Prefer `TObjectPtr`, `TWeakObjectPtr`, `TSoftObjectPtr`, or documented ownership over ambiguous raw `UObject*` fields.
- Use `UPROPERTY` for UObject references that must be tracked by garbage collection.
- Keep editor-only dependencies out of runtime modules unless the module is explicitly editor-only.
- Prefer `PrivateDependencyModuleNames` unless a public header exposes the dependency.
- Keep Blueprint-exposed APIs intentional; do not expose internal implementation details just for convenience.
- If an Actor enables Tick, the code review should explain why event-driven, timer-driven, or async behavior is not enough.

## Debug View Notes

When these rules are used by Code Review, show the matched rule IDs and the source document path in Debug View. The user-facing panel should show natural language findings, not raw JSON or raw prompt text.

