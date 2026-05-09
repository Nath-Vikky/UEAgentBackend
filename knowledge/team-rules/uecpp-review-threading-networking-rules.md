# UE C++ Review Rules For Async, Networking, And GAS

source_note: distilled from local UE C++ course notes and rewritten for this project knowledge base
scope: local UE knowledge base
license_check: source repository says course materials are for purchased learners; this file is an original summary, not a copied chapter
domain: team_rules
topic: code review, threading, networking, replication, GAS, config, delegates
use_for: Code Review, Logs Analyze, Project QA

## Threading Rules

- Do not access Actor, Component, Widget, World, Asset Registry, or other UObject-heavy APIs from background threads unless the API is explicitly thread-safe.
- Use `AsyncTask(ENamedThreads::GameThread, ...)` before broadcasting Blueprint delegates or touching gameplay objects.
- Avoid `FPlatformProcess::Sleep` loops on GameThread and avoid blocking `TFuture.Get()` calls in frame code.
- Long-lived `FRunnable` classes need a stop flag, timeout-aware loops, and deterministic shutdown.

## Networking Rules

- HTTP callbacks must check success flag, response validity, response code, and body parse errors.
- WebSocket owners must close the socket and unbind callbacks when the owner deinitializes.
- TCP code must handle partial packets, reconnects, timeouts, and stop requests.
- Do not hard-code API keys, tokens, passwords, or secret URLs in source files.

## Replication Rules

- Do not trust client RPC payloads for damage, currency, inventory, or authority-only state.
- Register replicated properties with `DOREPLIFETIME` or the appropriate conditional macro.
- Keep replicated data compact and prefer ids/tags over large object graphs.
- Separate replicated persistent state from transient multicast events.

## GAS Rules

- ASC initialization should be explicit and documented for player-controlled and AI-controlled actors.
- AttributeSet values should be changed through Gameplay Effects when possible.
- Ability activation should respect authority, cost, cooldown, blocking tags, and prediction boundaries.
- UI should read attributes after ASC and AttributeSet are initialized and replicated.

## Config And Delegate Rules

- Use `UDeveloperSettings` for editable project-wide settings and avoid committed secrets.
- Dynamic multicast delegates exposed to Blueprint should be unbound or naturally owned by a safe lifetime object.
- Prefer `TWeakObjectPtr` or explicit unbinding when a callback may outlive the receiver.
