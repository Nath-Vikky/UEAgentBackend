# Blueprint And Asset Inspection Checklist

domain: asset_rules
topic: Blueprint asset inspection, naming, dependencies, settings
use_for: Assets Inspect, Project QA

## Blueprint Checklist

- Check whether the Blueprint parent class is appropriate for its gameplay role.
- Confirm Tick is disabled unless the asset truly needs per-frame behavior.
- Review important components such as mesh, collision, camera, movement, and ability components.
- Check dependencies and referencers to understand whether the asset is isolated, reused, or tightly coupled.
- Verify naming prefixes are consistent with project conventions, such as `BP_`, `WBP_`, `ABP_`, `M_`, `MI_`, `SM_`, and `SK_`.

## Static Mesh Checklist

- Check Nanite state, LOD count, collision complexity, material slot count, and approximate triangle count when metadata is available.
- Collision should be explicit for gameplay-relevant meshes.
- Material slots should be intentional and not inflated by import mistakes.

## User-Facing Guidance

Assets Inspect should explain selected assets. Agent Chat project-level questions such as “当前项目有哪些蓝图资产” should query Project Inventory, not the selected asset payload.

