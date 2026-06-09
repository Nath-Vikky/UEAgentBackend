from __future__ import annotations

from typing import Any

from app.agent.intent_models import ResolvedContext
from app.schemas.requests import UnifiedTaskRequest


def resolve_context(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
    intent_draft: dict[str, Any],
) -> dict[str, Any]:
    """Resolve short references such as "this asset" into a concrete UE target."""

    target_kind = str(intent_draft.get("target_kind") or "none")
    if target_kind in {"none", "knowledge_base", "project_inventory", "project_file"}:
        return ResolvedContext(
            target_kind=target_kind,
            target_id="",
            target_display_name="",
            source="not_required",
            status="not_required",
        ).model_dump()

    active_targets = dict((context_bundle.get("agent_turn_context") or {}).get("active_targets") or {})
    inventory = dict(context_bundle.get("project_inventory_context") or {})
    active_context = dict(context_bundle.get("active_context") or {})

    resolver = {
        "selected_context": _resolve_selected_context,
        "selected_asset": _resolve_asset,
        "asset": _resolve_asset,
        "current_blueprint": _resolve_blueprint,
        "blueprint": _resolve_blueprint,
        "widget": _resolve_widget,
        "selected_actor": _resolve_actor,
        "level_actor": _resolve_actor,
        "selected_material_instance": _resolve_material,
        "material": _resolve_material,
        "current_code_file": _resolve_code,
        "current_log": _resolve_log,
    }.get(target_kind)
    if resolver is None:
        return _missing(target_kind, "unsupported_target_kind")

    resolved = resolver(
        request=request,
        active_targets=active_targets,
        active_context=active_context,
        inventory=inventory,
    )
    if resolved["status"] == "resolved":
        resolved["target_kind"] = target_kind
    return resolved


def _resolve_selected_context(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    for resolver in (
        _resolve_asset,
        _resolve_blueprint,
        _resolve_widget,
        _resolve_actor,
        _resolve_material,
        _resolve_code,
        _resolve_log,
    ):
        resolved = resolver(
            request=request,
            active_targets=active_targets,
            active_context=active_context,
            inventory=inventory,
        )
        if resolved["status"] == "resolved":
            resolved["target_kind"] = "selected_context"
            return resolved
    return _missing("selected_context", "selected_context_not_available")


def _resolve_asset(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    asset_target = dict(active_targets.get("asset") or {})
    selected_assets = [str(item).strip() for item in list(asset_target.get("selected_assets") or []) if str(item).strip()]
    inventory_assets = [item for item in list(inventory.get("selected_assets") or []) if isinstance(item, dict)]
    if inventory_assets:
        item = dict(inventory_assets[0])
        asset_path = _first_non_empty(item.get("asset_path"), selected_assets[0] if selected_assets else "")
        return _resolved(
            target_kind="selected_asset",
            target_id=asset_path,
            target_display_name=_first_non_empty(item.get("asset_name"), _tail(asset_path)),
            source="project_inventory_selected_asset",
            available_fields=item,
            required_fields=("asset_path", "asset_name", "asset_type"),
        )
    if selected_assets:
        asset_path = selected_assets[0]
        return _resolved(
            target_kind="selected_asset",
            target_id=asset_path,
            target_display_name=_tail(asset_path),
            source="request_selected_asset",
            available_fields={"asset_path": asset_path},
            required_fields=("asset_path", "asset_name", "asset_type"),
        )
    request_assets = [str(item).strip() for item in list(request.context.selected_assets or []) if str(item).strip()]
    if request_assets:
        asset_path = request_assets[0]
        return _resolved(
            target_kind="selected_asset",
            target_id=asset_path,
            target_display_name=_tail(asset_path),
            source="request_context_selected_asset",
            available_fields={"asset_path": asset_path},
            required_fields=("asset_path", "asset_name", "asset_type"),
        )
    return _missing("selected_asset", "selected_asset_not_available")


def _resolve_blueprint(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    target = dict(active_targets.get("blueprint") or {})
    blueprint = inventory.get("current_blueprint") if isinstance(inventory.get("current_blueprint"), dict) else {}
    graph = inventory.get("current_blueprint_graph") if isinstance(inventory.get("current_blueprint_graph"), dict) else {}
    path = _first_non_empty(
        blueprint.get("asset_path"),
        target.get("current_blueprint_path"),
        (active_context.get("blueprint") or {}).get("current_blueprint_path")
        if isinstance(active_context.get("blueprint"), dict)
        else "",
    )
    graph_name = _first_non_empty(graph.get("graph_name"), target.get("current_graph_name"))
    if path or graph_name:
        available = {**blueprint, "asset_path": path, "graph_name": graph_name}
        return _resolved(
            target_kind="current_blueprint",
            target_id=path or graph_name,
            target_display_name=_tail(path) or graph_name,
            source="current_blueprint_context",
            available_fields=available,
            required_fields=("asset_path", "graph_name"),
        )
    return _missing("current_blueprint", "current_blueprint_not_available")


def _resolve_widget(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    widget = dict((active_context.get("widget") or {}) if isinstance(active_context.get("widget"), dict) else {})
    widget_blueprint = inventory.get("current_widget_blueprint")
    widget_blueprint = widget_blueprint if isinstance(widget_blueprint, dict) else {}
    path = _first_non_empty(widget_blueprint.get("asset_path"), widget.get("current_widget_blueprint_path"))
    name = _first_non_empty(widget.get("current_widget_name"), widget.get("selected_widget_name"), widget_blueprint.get("asset_name"))
    if path or name:
        return _resolved(
            target_kind="widget",
            target_id=path or name,
            target_display_name=name or _tail(path),
            source="current_widget_context",
            available_fields={**widget_blueprint, **widget, "asset_path": path, "widget_name": name},
            required_fields=("asset_path", "widget_name"),
        )
    return _missing("widget", "current_widget_not_available")


def _resolve_actor(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    target = dict(active_targets.get("level_actor") or {})
    actor = inventory.get("current_level_actor")
    actor = actor if isinstance(actor, dict) else {}
    refs = [str(item).strip() for item in list(target.get("selected_actor_references") or []) if str(item).strip()]
    actor_ref = _first_non_empty(actor.get("actor_path"), actor.get("actor_label"), target.get("current_actor_reference"), refs[0] if refs else "")
    if actor_ref:
        return _resolved(
            target_kind="selected_actor",
            target_id=actor_ref,
            target_display_name=_first_non_empty(actor.get("actor_label"), actor.get("actor_name"), actor_ref),
            source="current_level_actor_context" if actor else "request_selected_actor",
            available_fields={**actor, "actor_reference": actor_ref},
            required_fields=("actor_reference", "actor_class", "components"),
        )
    return _missing("selected_actor", "selected_actor_not_available")


def _resolve_material(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    target = dict(active_targets.get("material") or {})
    material = inventory.get("current_material_instance")
    material = material if isinstance(material, dict) else {}
    paths = [str(item).strip() for item in list(target.get("selected_material_instance_paths") or []) if str(item).strip()]
    path = _first_non_empty(material.get("material_instance_path"), target.get("current_material_instance_path"), paths[0] if paths else "")
    if path:
        return _resolved(
            target_kind="selected_material_instance",
            target_id=path,
            target_display_name=_first_non_empty(material.get("material_instance_name"), _tail(path)),
            source="current_material_context" if material else "request_selected_material",
            available_fields={**material, "material_instance_path": path},
            required_fields=("material_instance_path", "parent_material", "parameters"),
        )
    return _missing("selected_material_instance", "selected_material_not_available")


def _resolve_code(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    target = dict(active_targets.get("code") or {})
    files = [str(item).strip() for item in list(target.get("selected_files") or []) if str(item).strip()]
    path = _first_non_empty(target.get("current_file"), files[0] if files else "", request.context.current_file)
    if path:
        return _resolved(
            target_kind="current_code_file",
            target_id=path,
            target_display_name=_tail(path),
            source="current_code_context",
            available_fields={"file_path": path},
            required_fields=("file_path",),
        )
    return _missing("current_code_file", "current_code_file_not_available")


def _resolve_log(
    *,
    request: UnifiedTaskRequest,
    active_targets: dict[str, Any],
    active_context: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    target = dict(active_targets.get("log") or {})
    source = _first_non_empty(target.get("log_file_path"), target.get("source"))
    if source or target.get("log_text_chars"):
        return _resolved(
            target_kind="current_log",
            target_id=source or "pasted_log_text",
            target_display_name=source or "pasted_log_text",
            source="current_log_context",
            available_fields=dict(target),
            required_fields=("source", "log_file_path", "log_text_chars"),
        )
    return _missing("current_log", "current_log_not_available")


def _resolved(
    *,
    target_kind: str,
    target_id: str,
    target_display_name: str,
    source: str,
    available_fields: dict[str, Any],
    required_fields: tuple[str, ...],
) -> dict[str, Any]:
    missing = [field for field in required_fields if available_fields.get(field) in (None, "", [], {})]
    return ResolvedContext(
        target_kind=target_kind,
        target_id=str(target_id or ""),
        target_display_name=str(target_display_name or target_id or ""),
        source=source,
        status="resolved",
        available_fields=available_fields,
        missing_fields=missing,
    ).model_dump()


def _missing(target_kind: str, reason: str) -> dict[str, Any]:
    return ResolvedContext(
        target_kind=target_kind,
        target_id="",
        target_display_name="",
        source=reason,
        status="missing_active_context",
        missing_fields=[reason],
    ).model_dump()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _tail(path: str) -> str:
    text = str(path or "").strip().rstrip("/")
    if not text:
        return ""
    tail = text.rsplit("/", 1)[-1]
    if "." in tail:
        tail = tail.rsplit(".", 1)[-1]
    return tail


__all__ = ["resolve_context"]
