# UE Static Mesh Nanite LOD Collision Notes

source_url: https://dev.epicgames.com/documentation/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
created_on: 2026-04-25
domain: engine_notes
topic: static mesh, Nanite, LOD, collision, material slots
use_for: Assets Inspect, Project QA

## Summary

Static Mesh review should consider rendering settings, collision behavior, material slots, platform needs, and whether Nanite is appropriate. Nanite can reduce manual LOD work for many high-detail meshes, but collision, fallback, material behavior, and unsupported cases still need review.

## Key Points

- Nanite is intended for high-detail geometry and can handle automatic detail reduction for rendering.
- Traditional LOD and fallback mesh behavior still matter for compatibility and special cases.
- Collision should be reviewed separately from visual mesh detail.
- Material slot count affects draw complexity and should stay intentional.
- Not every mesh should automatically enable Nanite; consider deformation, target platform, and content type.

## Asset Inspection Heuristics

- For `StaticMesh`, report `nanite_enabled`, `lod_count`, `collision_complexity`, material slot count, and triangle count if available.
- Warn when a gameplay collision mesh is missing or unclear.
- Warn when material slot count is high without an obvious reason.
- Treat Nanite as a setting to explain, not as an automatic pass/fail rule.

