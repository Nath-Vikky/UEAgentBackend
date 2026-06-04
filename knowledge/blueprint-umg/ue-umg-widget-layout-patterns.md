# UE UMG Widget Layout Patterns

source_url: local_distilled_note
created_on: 2026-06-04
domain: blueprint_umg
topic: UMG, Widget Tree, CanvasPanel, HorizontalBox, VerticalBox, TextBlock, Image, Button
keywords: UMG, WidgetTree, CanvasPanel, CanvasPanelSlot, HorizontalBox, VerticalBox, TextBlock, Image, Button, layout, anchors, alignment, padding, brush
use_for: Project QA, Code Generate, Editor Operation Planning

## Summary

UMG automation should treat the Widget Tree as an editor asset graph. The safe pattern is to locate the target
`UWidgetBlueprint`, find or create a parent panel, create the requested widget, attach it to the panel slot, then apply
layout properties based on the slot type.

## Common Safe Flow

- Open the target `UWidgetBlueprint` and use its `WidgetTree`.
- Prefer a named root or parent panel when the user gives one.
- If no parent is provided, use the root widget only when it is a panel.
- For `CanvasPanel`, apply anchors, offsets, alignment, and Z order through `UCanvasPanelSlot`.
- For `HorizontalBox` and `VerticalBox`, apply padding, size rule, alignment, and fill value through their slot types.
- For `TextBlock`, set text, color, font size, wrapping, and justification after creation.
- For `Image`, set brush tint, desired size, and optional texture brush.
- For `Button`, attach a child widget such as `TextBlock` when the user wants a labeled button.
- Mark the blueprint modified and compile only after all widget and slot changes are applied.

## Agent Planning Notes

- Do not assume every widget blueprint has a `CanvasPanel` root.
- Ask for or infer a parent panel before creating layout-sensitive widgets.
- Return a proposal when the operation writes to a blueprint; do not apply silently.
- Keep operation results human-readable: added widget, parent widget, slot type, layout fields, compile status, and warnings.

## Typical Failure Reasons

- `widget_blueprint_not_found`: the selected or named widget blueprint cannot be resolved.
- `parent_widget_not_found`: the requested parent widget is missing from the Widget Tree.
- `unsupported_slot_type`: the parent exists but does not expose the requested layout fields.
- `widget_name_conflict`: a widget with the requested variable name already exists.
- `compile_failed`: the widget tree changed but blueprint compilation failed.
