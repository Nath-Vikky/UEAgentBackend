from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.editor_operations.catalog import (
    EDITOR_OPERATION_PROPOSAL_TYPE,
    EDITOR_OPERATION_PROTOCOL_VERSION,
    OPERATION_GROUPS,
    OPERATION_ROADMAP,
    OPERATION_SPECS,
    READ_ONLY_INSPECTION_SPECS,
)
from app.services.editor_operations.result_contracts import expected_result_contract


def operation_group(operation_type: str) -> str:
    for group_id, group in OPERATION_GROUPS.items():
        if operation_type in set(group["operation_types"]):
            return group_id
    return "misc"


def supported_operations() -> dict[str, Any]:
    risk_counts = Counter(str(spec["risk_flags"]) for spec in OPERATION_SPECS.values())
    frontend_status_counts = Counter(str(spec["frontend_status"]) for spec in OPERATION_SPECS.values())
    group_counts = Counter(operation_group(operation_type) for operation_type in OPERATION_SPECS)
    read_only_group_counts = Counter(str(item["group"]) for item in READ_ONLY_INSPECTION_SPECS.values())
    read_only_status_counts = Counter(str(item["frontend_status"]) for item in READ_ONLY_INSPECTION_SPECS.values())
    roadmap_group_counts = Counter(str(item["group"]) for item in OPERATION_ROADMAP.values())
    roadmap_status_counts = Counter(str(item["frontend_status"]) for item in OPERATION_ROADMAP.values())
    groups = [
        {
            "group_id": group_id,
            "title": group["title"],
            "summary": group["summary"],
            "operation_count": sum(1 for item in group["operation_types"] if item in OPERATION_SPECS),
            "read_only_count": read_only_group_counts.get(group_id, 0),
            "roadmap_count": roadmap_group_counts.get(group_id, 0),
            "operation_types": [item for item in group["operation_types"] if item in OPERATION_SPECS],
            "read_only_operation_types": [
                operation_type
                for operation_type, item in READ_ONLY_INSPECTION_SPECS.items()
                if item["group"] == group_id
            ],
            "roadmap_operation_types": [
                operation_type
                for operation_type, item in OPERATION_ROADMAP.items()
                if item["group"] == group_id
            ],
        }
        for group_id, group in OPERATION_GROUPS.items()
    ]
    return {
        "protocol_version": EDITOR_OPERATION_PROTOCOL_VERSION,
        "proposal_type": EDITOR_OPERATION_PROPOSAL_TYPE,
        "transport": "http",
        "mcp_like": True,
        "summary": {
            "operation_count": len(OPERATION_SPECS),
            "implemented_frontend_count": frontend_status_counts.get("implemented_v1", 0),
            "risk_flag_counts": dict(risk_counts),
            "frontend_status_counts": dict(frontend_status_counts),
            "group_counts": dict(group_counts),
            "group_count": len(groups),
            "read_only_operation_count": len(READ_ONLY_INSPECTION_SPECS),
            "read_only_group_counts": dict(read_only_group_counts),
            "read_only_status_counts": dict(read_only_status_counts),
            "roadmap_operation_count": len(OPERATION_ROADMAP),
            "roadmap_group_counts": dict(roadmap_group_counts),
            "roadmap_status_counts": dict(roadmap_status_counts),
        },
        "safety_policy": {
            "side_effect_level": "confirmed_write",
            "llm_direct_execution": False,
            "requires_frontend_confirmation": True,
            "ue_plugin_executes_editor_api": True,
            "auto_execute_follow_ups": False,
            "auto_save": False,
        },
        "groups": groups,
        "items": [
            {
                "operation_type": operation_type,
                "group": operation_group(operation_type),
                "tool_id": spec["tool_id"],
                "title": spec["title"],
                "summary": spec["summary"],
                "risk_flags": spec["risk_flags"],
                "required_fields": spec["required_fields"],
                "frontend_status": spec["frontend_status"],
                "side_effect_level": "confirmed_write",
                "requires_confirmation": True,
                "auto_save": False,
                "result_contract_fields": expected_result_contract(operation_type)["operation_result_fields"],
            }
            for operation_type, spec in OPERATION_SPECS.items()
        ],
        "read_only_items": [
            {
                "operation_type": operation_type,
                "group": item["group"],
                "tool_id": item["tool_id"],
                "title": item["title"],
                "summary": item["summary"],
                "required_fields": item["required_fields"],
                "frontend_status": item["frontend_status"],
                "side_effect_level": "read_only",
                "requires_confirmation": False,
                "auto_save": False,
                "proposal_enabled": False,
                "endpoint": item["endpoint"],
                "boundary": item["boundary"],
            }
            for operation_type, item in READ_ONLY_INSPECTION_SPECS.items()
        ],
        "roadmap_items": [
            {
                "operation_type": operation_type,
                "group": item["group"],
                "title": item["title"],
                "summary": item["summary"],
                "required_fields": item["required_fields"],
                "frontend_status": item["frontend_status"],
                "side_effect_level": item["side_effect_level"],
                "requires_confirmation": item["side_effect_level"] != "read_only",
                "auto_save": False,
                "proposal_enabled": False,
                "boundary": item["boundary"],
            }
            for operation_type, item in OPERATION_ROADMAP.items()
        ],
    }

