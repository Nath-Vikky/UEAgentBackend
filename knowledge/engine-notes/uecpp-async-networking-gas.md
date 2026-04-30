# UE C++ Async, Networking, Replication, And GAS Notes

source_note: distilled from local UE C++ course notes and rewritten for this portfolio knowledge base
scope: portfolio knowledge base
license_check: source repository says course materials are for purchased learners; this file is an original summary, not a copied chapter
domain: engine_notes
topic: async, threading, HTTP, WebSocket, TCP, replication, RPC, GAS
use_for: Project QA, Code Generate, Code Review, Logs Analyze

## Retrieval Aliases

async, AsyncTask, Async, TFuture, FRunnable, FRunnableThread, FGraphEvent, ParallelFor, HTTP, FHttpModule, WebSocket, IWebSocket, TCP, FSocket, replication, RPC, DOREPLIFETIME, Gameplay Ability System, GAS, AbilitySystemComponent, AttributeSet, GameplayAbility, GameplayEffect

## Async Mode Selection

- Use `AsyncTask(ENamedThreads::GameThread, ...)` to jump back to the game thread after background work.
- Use `Async()` and `TFuture` for short calculations that need a result.
- Use `FRunnable` when the task owns a long-lived loop, socket, microphone stream, or background worker.
- Use `ParallelFor` for data-parallel loops, not for UObject-heavy logic.
- Do not block the TaskGraph or GameThread with long sleeps, synchronous IO, or network polling.
- UObject access from background threads should be avoided; marshal data back to GameThread before touching actors, components, widgets, or assets.

## HTTP / WebSocket / TCP Selection

- HTTP is best for request-response APIs, file upload, JSON payloads, and AI model calls.
- WebSocket is best for real-time bidirectional streams such as chat, voice recognition, push messages, and editor monitor channels.
- TCP is best when a custom application protocol is required and the project accepts manual framing, reconnection, and byte-buffer handling.
- HTTP code usually needs `HTTP`, `Json`, and `JsonUtilities` module dependencies.
- WebSocket code usually needs `WebSockets`.
- TCP code usually needs `Sockets` and `Networking`.

## Replication And RPC Boundaries

- Replicated properties must be registered in `GetLifetimeReplicatedProps`.
- `OnRep_` handlers are for client-side reaction to replicated state, not for authoritative game rules.
- Server RPC should validate caller authority and input trust boundaries.
- Multicast RPC is for transient events that every relevant client must observe; do not use it as a substitute for state replication.
- Keep replicated payloads compact and prefer stable ids/tags over large UObject graphs.

## GAS Minimal Mental Model

- `UAbilitySystemComponent` is the runtime ability owner.
- `UAttributeSet` stores replicated gameplay attributes such as health, mana, stamina, attack, defense, or speed.
- `UGameplayAbility` contains activation logic and cost/cooldown checks.
- `UGameplayEffect` changes attributes, applies buffs/debuffs, and describes duration policies.
- Gameplay Tags are the glue for ability categories, blocking rules, cooldown tags, and state queries.
- For multiplayer, initialize ASC on the server and ensure clients receive the replicated ASC and attributes before UI queries them.

## Code Review Red Flags

- Background thread touches `UObject` or `AActor` directly.
- `TFuture.Get()` is called on GameThread before the task is known to be completed.
- Socket loops have no stop flag, timeout, or shutdown path.
- RPC accepts client-provided damage, inventory, or position values without validation.
- GAS ability activation bypasses tags, costs, cooldowns, or authority checks.

