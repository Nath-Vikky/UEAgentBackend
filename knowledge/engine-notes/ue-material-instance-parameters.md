# UE Material Instance Parameter Editing

source_url: local_distilled_note
created_on: 2026-06-04
domain: engine_notes
topic: Material Instance, scalar parameter, vector parameter, texture parameter, static switch
keywords: MaterialInstanceConstant, MaterialInstance, scalar parameter, vector parameter, texture parameter, static switch, editor only, parent material
use_for: Project QA, Code Generate, Editor Operation Planning, Assets Inspect

## Summary

Material automation should distinguish runtime material changes from editor asset edits. Editing a `UMaterialInstanceConstant`
inside the editor is an asset write operation and should be proposed, confirmed, applied, marked dirty, and saved by the
editor-side tool.

## Parameter Types

- Scalar parameter: float values such as Roughness, Metallic, Opacity, EmissiveIntensity, or Tiling.
- Vector parameter: color or vector values such as BaseColor, Tint, EmissiveColor, or UV scale.
- Texture parameter: texture asset references such as BaseColorMap, NormalMap, ORM, or MaskTexture.
- Static switch parameter: compile-time feature toggles such as UseDetailNormal, UseClearCoat, or EnableDissolve.

## Safe Editing Flow

- Resolve the selected or named `UMaterialInstanceConstant`.
- Read its parent material and exposed parameter list before applying changes.
- Validate that the parameter exists or report a missing-parameter diagnostic.
- Convert the user value to the expected type.
- Apply the parameter through the editor-only material instance API.
- Mark the package dirty and report whether a save was requested or skipped.
- Recompile or refresh only when necessary; static switch changes are more expensive than scalar/vector changes.

## Agent Planning Notes

- Do not invent parameter names when the inventory does not show them.
- If the user asks for "make it red" and no parameter is selected, prefer likely names such as `BaseColor`, `Tint`, or
  `Color`, but return alternatives instead of forcing one.
- If the user asks about a material value, answer from Project Inventory first.
- If the user asks to change a value, generate a confirmed write proposal.
