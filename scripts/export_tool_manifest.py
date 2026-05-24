from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.tool_manifest_service import build_tool_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ToolSpec registry as an MCP-compatible manifest.")
    parser.add_argument("--output", default="docs/tool-registry-manifest.json", help="Output JSON file path.")
    parser.add_argument("--category", default="", help="Optional ToolSpec category filter.")
    parser.add_argument("--side-effect-level", default="", help="Optional side_effect_level filter.")
    parser.add_argument("--transport", default="", help="Optional transport filter.")
    parser.add_argument("--enabled-only", action="store_true", help="Exclude disabled tools.")
    args = parser.parse_args()

    manifest = build_tool_manifest(
        include_disabled=not args.enabled_only,
        category=args.category or None,
        side_effect_level=args.side_effect_level or None,
        transport=args.transport or None,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
