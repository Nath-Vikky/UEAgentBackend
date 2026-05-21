from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from app.services.editor_operation_service import EditorOperationService


def _format_list(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "-"


def render_editor_operation_catalog(catalog: dict[str, Any] | None = None) -> str:
    capabilities = catalog or EditorOperationService.supported_operations()
    summary = dict(capabilities.get("summary") or {})
    safety_policy = dict(capabilities.get("safety_policy") or {})
    items = [dict(item) for item in capabilities.get("items") or []]
    read_only_items = [dict(item) for item in capabilities.get("read_only_items") or []]
    roadmap_items = [dict(item) for item in capabilities.get("roadmap_items") or []]
    items_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        items_by_group.setdefault(str(item.get("group") or "misc"), []).append(item)
    read_only_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in read_only_items:
        read_only_by_group.setdefault(str(item.get("group") or "misc"), []).append(item)
    roadmap_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in roadmap_items:
        roadmap_by_group.setdefault(str(item.get("group") or "misc"), []).append(item)

    lines = [
        "# Editor Operation Catalog",
        "",
        "This catalog is generated from the backend editor operation registry.",
        "",
        "## Summary",
        "",
        f"- Operation count: `{summary.get('operation_count', len(items))}`",
        f"- Implemented frontend count: `{summary.get('implemented_frontend_count', 0)}`",
        f"- Read-only inspection count: `{summary.get('read_only_operation_count', len(read_only_items))}`",
        f"- Transport: `{capabilities.get('transport')}`",
        f"- Proposal type: `{capabilities.get('proposal_type')}`",
        f"- Requires confirmation: `{safety_policy.get('requires_frontend_confirmation')}`",
        f"- LLM direct execution: `{safety_policy.get('llm_direct_execution')}`",
        f"- Auto execute follow-ups: `{safety_policy.get('auto_execute_follow_ups')}`",
        f"- Auto save: `{safety_policy.get('auto_save')}`",
        f"- Roadmap operation count: `{summary.get('roadmap_operation_count', len(roadmap_items))}`",
        "",
        "## Groups",
        "",
    ]

    for group in capabilities.get("groups") or []:
        group_id = str(group.get("group_id") or "misc")
        group_items = items_by_group.get(group_id, [])
        lines.extend(
            [
                f"### {group.get('title') or group_id}",
                "",
                str(group.get("summary") or ""),
                "",
                "| Operation | Risk | Required Fields | Result Fields |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in group_items:
            lines.append(
                "| "
                f"`{item.get('operation_type')}` | "
                f"`{item.get('risk_flags')}` | "
                f"{_format_list(list(item.get('required_fields') or []))} | "
                f"{_format_list(list(item.get('result_contract_fields') or []))} |"
            )
        lines.append("")

        group_read_only = read_only_by_group.get(group_id, [])
        if group_read_only:
            lines.extend(
                [
                    "Read-only inspections:",
                    "",
                    "| Inspection | Endpoint | Required Fields | Boundary |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for item in group_read_only:
                lines.append(
                    "| "
                    f"`{item.get('operation_type')}` | "
                    f"`{item.get('endpoint')}` | "
                    f"{_format_list(list(item.get('required_fields') or []))} | "
                    f"{item.get('boundary') or ''} |"
                )
            lines.append("")

        group_roadmap = roadmap_by_group.get(group_id, [])
        if group_roadmap:
            lines.extend(
                [
                    "Roadmap:",
                    "",
                    "| Planned Operation | Side Effect | Required Fields | Boundary |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for item in group_roadmap:
                lines.append(
                    "| "
                    f"`{item.get('operation_type')}` | "
                    f"`{item.get('side_effect_level')}` | "
                    f"{_format_list(list(item.get('required_fields') or []))} | "
                    f"{item.get('boundary') or ''} |"
                )
            lines.append("")

    lines.extend(
        [
            "## Safety Boundary",
            "",
            "- The backend only creates confirmed-write proposals.",
            "- UEAgentTool executes Unreal Editor APIs only after user confirmation.",
            "- Follow-up candidates are drafts and are never auto-executed.",
            "- Packages are marked dirty but not auto-saved by default.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export backend editor operation catalog as Markdown.")
    parser.add_argument(
        "--output",
        default="docs/editor-operation-catalog.md",
        help="Markdown output path. Use '-' to print to stdout.",
    )
    args = parser.parse_args()

    markdown = render_editor_operation_catalog()
    if args.output == "-":
        print(markdown)
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
