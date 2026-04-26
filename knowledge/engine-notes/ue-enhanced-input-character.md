# UE Enhanced Input Character Notes

source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input-in-unreal-engine
created_on: 2026-04-26
domain: engine_notes
topic: Enhanced Input, Character, Input Action, Input Mapping Context, UEnhancedInputComponent
keywords: enhanced input, EnhancedInput, UInputAction, UInputMappingContext, UEnhancedInputComponent, UEnhancedInputLocalPlayerSubsystem, 角色增强输入, 增强输入代码, 输入动作, 映射上下文
use_for: Code Generate, Project QA, Code Review

## Summary

Enhanced Input code for a playable `ACharacter` normally has three parts: asset references on the Character class, a mapping context added for the local player, and action bindings in `SetupPlayerInputComponent`. The C++ module also needs the `EnhancedInput` module dependency.

## Common Structure

- Header includes `GameFramework/Character.h` and `InputActionValue.h`.
- Header declares `UInputMappingContext` and `UInputAction` references, usually `EditDefaultsOnly` so the Blueprint subclass can assign assets.
- `BeginPlay` gets the `APlayerController`, then the `ULocalPlayer`, then `UEnhancedInputLocalPlayerSubsystem`, and calls `AddMappingContext(DefaultMappingContext, Priority)`.
- `SetupPlayerInputComponent` casts `UInputComponent` to `UEnhancedInputComponent`.
- Movement and look actions usually bind to `ETriggerEvent::Triggered`.
- Jump can bind `Started` to `ACharacter::Jump` and `Completed` to `ACharacter::StopJumping`.

## Build.cs Note

Add `EnhancedInput` to the target module dependency list. In a normal game module this is usually placed in `PublicDependencyModuleNames` or `PrivateDependencyModuleNames` with `Core`, `CoreUObject`, `Engine`, and `InputCore`.

## Code Generation Hints

- Prefer `Source/<Module>/Public/<CharacterName>.h` and `Source/<Module>/Private/<CharacterName>.cpp`.
- Use `ACharacter`, not a plain `AActor`, when the user asks for 角色, player character, movement, jump, or Enhanced Input character code.
- Return the generated code as a draft only; do not claim that files were written to disk.
- Remind the user to create and assign Input Action assets and an Input Mapping Context asset in the editor.

