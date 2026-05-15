from __future__ import annotations

import argparse
import json
import sys

from app.core.settings import Settings
from app.services.web_search_service import WebSearchService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a manual Controlled Web Search smoke test.")
    parser.add_argument(
        "--query",
        default="Unreal Engine Enhanced Input official docs",
        help="Search query to run through the configured provider.",
    )
    parser.add_argument(
        "--language",
        default="en-US",
        help="Language hint passed to the provider.",
    )
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="Exit 0 when Web Search is intentionally disabled.",
    )
    args = parser.parse_args()

    service = WebSearchService(Settings())
    status = service.status()
    result = service.search(
        query=args.query,
        language=args.language,
        trigger_reason="manual_smoke",
    )
    print(
        json.dumps(
            {
                "status": status,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if result.get("status") == "completed" and result.get("items"):
        return 0
    if args.allow_disabled and result.get("status") == "skipped":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
