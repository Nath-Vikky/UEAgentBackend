# Editor Operation Catalog

This catalog is generated from the backend editor operation registry.

## Summary

- Operation count: `20`
- Implemented frontend count: `20`
- Read-only inspection count: `2`
- Transport: `http`
- Proposal type: `editor_operation`
- Requires confirmation: `True`
- LLM direct execution: `False`
- Auto execute follow-ups: `False`
- Auto save: `False`
- Roadmap operation count: `5`

## Groups

### Asset Operations

Rename, move, and apply safe asset settings.

| Operation | Risk | Required Fields | Result Fields |
| --- | --- | --- | --- |
| `rename_selected_asset` | `MEDIUM` | `asset_path`, `new_name` | `final_asset_path`, `dirty`, `dirty_packages` |
| `apply_static_mesh_basic_settings` | `MEDIUM` | `asset_path`, `settings` | `dirty`, `dirty_packages`, `applied_fields`, `failed_fields` |
| `batch_rename_assets` | `HIGH` | `renames` | `renamed_assets`, `dirty_packages`, `failed_items` |
| `move_assets` | `HIGH` | `asset_paths`, `target_folder` | `moved_assets`, `dirty_packages`, `failed_items` |

### Blueprint Operations

Create Blueprint assets and perform bounded Blueprint graph edits.

| Operation | Risk | Required Fields | Result Fields |
| --- | --- | --- | --- |
| `create_blueprint_asset` | `MEDIUM` | `parent_class`, `target_folder`, `asset_name` | `asset_path`, `dirty`, `dirty_packages` |
| `add_blueprint_variable` | `MEDIUM` | `blueprint_path`, `variable_name`, `variable_type` | `blueprint_path`, `variable_name`, `dirty`, `dirty_packages` |
| `add_blueprint_component` | `MEDIUM` | `blueprint_path`, `component_name`, `component_class` | `blueprint_path`, `component_name`, `dirty`, `dirty_packages` |
| `create_blueprint_event_stub` | `MEDIUM` | `blueprint_path`, `event_name` | `blueprint_path`, `event_name`, `dirty`, `dirty_packages` |
| `add_blueprint_node_template` | `MEDIUM` | `blueprint_path`, `template_id` | `blueprint_path`, `template_id`, `graph_name`, `entry_event`, `branch_path`, `condition_default`, `sequence_output_count`, `messages`, `variable_name`, `variable_scope`, `variable_value`, `function_name`, `function_target`, `input_action_path`, `input_action_name`, `created_nodes`, `linked_nodes`, `linked_pins`, `compile_status`, `dirty`, `dirty_packages` |
| `connect_blueprint_nodes` | `MEDIUM` | `blueprint_path`, `graph_name`, `source_node_id`, `source_pin_name`, `target_node_id`, `target_pin_name` | `blueprint_path`, `graph_name`, `source_node_id`, `source_pin_name`, `target_node_id`, `target_pin_name`, `linked_pins`, `compile_status`, `dirty`, `dirty_packages` |
| `compile_blueprint` | `MEDIUM` | `blueprint_path` | `blueprint_path`, `compile_status`, `messages` |

### UMG Operations

Inspect and edit simple Widget Blueprint structure and properties.

| Operation | Risk | Required Fields | Result Fields |
| --- | --- | --- | --- |
| `add_umg_widget` | `MEDIUM` | `widget_blueprint_path`, `widget_name`, `widget_class` | `widget_blueprint_path`, `widget_name`, `dirty`, `dirty_packages` |
| `set_umg_widget_text` | `MEDIUM` | `widget_blueprint_path`, `widget_name`, `text` | `widget_blueprint_path`, `widget_name`, `dirty`, `dirty_packages` |
| `set_umg_widget_layout` | `MEDIUM` | `widget_blueprint_path`, `widget_name`, `layout` | `widget_blueprint_path`, `widget_name`, `dirty`, `dirty_packages` |
| `set_umg_widget_visibility` | `MEDIUM` | `widget_blueprint_path`, `widget_name`, `visibility` | `widget_blueprint_path`, `widget_name`, `dirty`, `dirty_packages` |

Roadmap:

| Planned Operation | Side Effect | Required Fields | Boundary |
| --- | --- | --- | --- |
| `set_umg_widget_appearance` | `confirmed_write` | `widget_blueprint_path`, `widget_name`, `appearance` | No animation editing, binding generation, or complex style inheritance. |
| `set_umg_widget_brush` | `confirmed_write` | `widget_blueprint_path`, `widget_name`, `brush` | No dynamic binding, no atlas editing, and no bulk widget tree rewrite. |
| `set_umg_slot_layout_v2` | `confirmed_write` | `widget_blueprint_path`, `widget_name`, `slot_type`, `layout` | No responsive layout generation and no complex container restructuring. |

### Level Operations

Place actors and adjust transforms in the current editor level.

| Operation | Risk | Required Fields | Result Fields |
| --- | --- | --- | --- |
| `place_actor_in_level` | `MEDIUM` | `actor_class` | `actor_label`, `actor_path`, `level_dirty`, `dirty_packages` |
| `set_actor_transform` | `MEDIUM` | `actor_reference`, `transform_mode` | `actor_reference`, `transform_mode`, `level_dirty`, `dirty_packages` |

Read-only inspections:

| Inspection | Endpoint | Required Fields | Boundary |
| --- | --- | --- | --- |
| `inspect_level_actors` | `/api/v1/editor-operations/inspect/level-actors` | - | Read-only inventory; no level streaming, World Partition editing, or Actor mutation. |

Roadmap:

| Planned Operation | Side Effect | Required Fields | Boundary |
| --- | --- | --- | --- |
| `set_actor_metadata` | `confirmed_write` | `actor_reference`, `metadata` | No actor deletion and no hidden batch edits. |
| `arrange_actors_pattern` | `confirmed_write` | `actor_references`, `pattern` | Batch operations require preview, item limits, and user confirmation. |

### Material Operations

Edit safe Material Instance parameters.

| Operation | Risk | Required Fields | Result Fields |
| --- | --- | --- | --- |
| `set_material_instance_parameter` | `MEDIUM` | `material_instance_path`, `parameter_name`, `parameter_type`, `value` | `material_instance_path`, `parameter_name`, `dirty`, `dirty_packages` |
| `set_material_instance_texture_parameter` | `MEDIUM` | `material_instance_path`, `parameter_name`, `texture_path` | `material_instance_path`, `parameter_name`, `texture_path`, `dirty`, `dirty_packages` |
| `set_material_instance_static_switch` | `MEDIUM` | `material_instance_path`, `parameter_name`, `value` | `material_instance_path`, `parameter_name`, `value`, `dirty`, `dirty_packages` |

Read-only inspections:

| Inspection | Endpoint | Required Fields | Boundary |
| --- | --- | --- | --- |
| `inspect_material_instance_parameters` | `/api/v1/editor-operations/inspect/material-instance-parameters` | `material_instance_path` | Read-only inspection; parent Material graph editing remains out of scope. |

## Safety Boundary

- The backend only creates confirmed-write proposals.
- UEAgentTool executes Unreal Editor APIs only after user confirmation.
- Follow-up candidates are drafts and are never auto-executed.
- Packages are marked dirty but not auto-saved by default.
