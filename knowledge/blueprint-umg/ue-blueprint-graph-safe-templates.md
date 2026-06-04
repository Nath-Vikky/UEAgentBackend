# UE Blueprint Graph Safe Templates

source_url: local_distilled_note
created_on: 2026-06-04
domain: blueprint_umg
topic: Blueprint graph automation, EventGraph, Print String, Enhanced Input, node connection
keywords: Blueprint, EventGraph, K2Node, BeginPlay, PrintString, EnhancedInputAction, execution pin, data pin, compile
use_for: Project QA, Code Generate, Editor Operation Planning, Editor Operation Troubleshooting

## Summary

Blueprint graph automation should use small, predictable templates instead of free-form node spawning. A template should
declare the graph, required event node, created nodes, pin matching rules, and compile behavior. This makes an agent
operation easier to validate before it reaches the editor.

## Minimal Print String Template

Target graph:

- Prefer the current focused graph from Project Inventory.
- If no graph is focused and the user mentions `EventGraph`, resolve the blueprint's event graph.
- If the blueprint has no event graph, return a repairable diagnostic instead of creating disconnected nodes.

Required nodes:

- Event node: `ReceiveBeginPlay`, `ActorBeginOverlap`, custom event, or an explicit selected source node.
- Action node: `PrintString`.

Connection rules:

- Connect event execution output to `PrintString` execution input.
- Set the `InString` pin to the requested text.
- Do not create a second event node if a compatible event already exists.
- If a pin cannot be matched by exact name, try display name aliases such as `Exec`, `Then`, `InString`, `Message`, or
  `String`.

## Enhanced Input Template

Use this only when the blueprint already has Enhanced Input context in the project, or when the user explicitly asks for
an Enhanced Input action event.

- Resolve the `InputAction` asset.
- Create an `EnhancedInputAction` event node.
- Connect the `Triggered` execution pin to the requested action chain.
- If the input action asset is missing, return a proposal with missing-asset diagnostics instead of inventing one.

## Agent Safety Notes

- Every graph write should be represented as a proposal first.
- The backend should include expected graph, node template id, source node, target node, and pin aliases in the proposal.
- The frontend should execute the concrete Unreal Editor API calls and return structured result diagnostics.
- The backend should translate diagnostics into user-facing repair suggestions.
