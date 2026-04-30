# UE C++ DeveloperSettings And Subsystem Example Notes

source_note: distilled from local UE C++ course notes and rewritten for this portfolio knowledge base
scope: portfolio knowledge base
license_check: source repository says course materials are for purchased learners; this file is an original summary, not a copied chapter
domain: examples
topic: UDeveloperSettings, config, INI, subsystem, dependency injection
use_for: Code Generate, Project QA, Code Review

## DeveloperSettings

Use `UDeveloperSettings` when project-wide settings should be edited in Project Settings and stored in config files.

Recommended shape:

- Derive from `UDeveloperSettings`.
- Use `UCLASS(Config=Game, DefaultConfig)`.
- Use `UPROPERTY(Config, EditAnywhere, Category="...")`.
- Read settings with `GetDefault<UMySettings>()`.
- Write editor-time settings with `GetMutableDefault<UMySettings>()` only when the workflow clearly requires it.

Typical fields:

- API endpoint URL
- feature toggles
- soft references to default assets
- gameplay tuning values
- editor-only tool preferences

Avoid storing secrets in committed config files. Keep API keys in local config, environment variables, or a user-only settings file.

## Subsystem

Use `UGameInstanceSubsystem` for runtime managers that live across map travel inside a game instance. Use `UWorldSubsystem` when the data should be per-world or per-PIE instance.

Recommended shape:

- Override `Initialize(FSubsystemCollectionBase& Collection)`.
- Override `Deinitialize()`.
- Hold UObject references with `UPROPERTY` when GC must track them.
- Clean timers, delegates, sockets, threads, and asset handles in `Deinitialize`.

## Pairing Pattern

DeveloperSettings often acts as the configuration source, while a Subsystem acts as the runtime owner:

```text
Project Settings -> UDeveloperSettings -> UGameInstanceSubsystem.Initialize -> runtime service
```

This pattern is useful for HTTP endpoints, WebSocket URLs, feature flags, default DataAssets, and editor assistant tools.

