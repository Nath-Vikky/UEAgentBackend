# UE Editor Operation Troubleshooting

source_url: local_distilled_note
created_on: 2026-06-04
domain: troubleshooting
topic: editor operation diagnostics, blueprint graph, UMG, material, repair advice
keywords: operation diagnostics, repair advice, widget_not_found, graph_not_found, pin_resolution_failed, compile_failed, material_parameter_missing
use_for: Project QA, Editor Operation Planning, Editor Operation Results, Logs Analyze

## Summary

Editor operations should return structured diagnostics that can be translated into plain repair advice. The user should
not have to read raw JSON to understand why an operation failed.

## Common Error Codes

- `blueprint_not_found`: the requested blueprint asset path or name cannot be resolved.
- `graph_not_found`: the blueprint exists but the requested graph is missing or not editable.
- `source_node_not_found`: the operation needs an existing event or selected node but cannot find it.
- `pin_resolution_failed`: a node was found but the expected execution or data pin could not be matched.
- `widget_blueprint_not_found`: the requested widget blueprint cannot be resolved.
- `widget_not_found`: the target UMG widget does not exist in the Widget Tree.
- `unsupported_slot_type`: the parent slot does not support the requested layout fields.
- `material_instance_not_found`: the requested material instance asset cannot be resolved.
- `material_parameter_missing`: the parameter name is not exposed by the material instance or its parent.
- `compile_failed`: the editor operation changed the asset but blueprint or material compilation failed.

## Repair Advice Pattern

For each failed operation, return:

- What was requested.
- What was actually found in Project Inventory.
- Which field or target failed.
- The safest next action, such as selecting the correct asset, naming the parent widget, choosing an existing graph, or
  checking the parameter list.

## User-Facing Tone

- Use direct language and avoid dumping raw JSON in the main result card.
- Include raw details only in Debug View or an expandable diagnostics block.
- If the operation partially succeeded, separate "applied changes" from "remaining issues".
- If the failure is due to missing context, ask for the smallest next input instead of guessing.
