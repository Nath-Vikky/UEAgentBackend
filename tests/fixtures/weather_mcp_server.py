from __future__ import annotations

import json
import sys


TOOLS = [
    {
        "name": "get_weather",
        "description": "Return deterministic weather for a city.",
        "inputSchema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
        },
    },
    {
        "name": "delete_weather_cache",
        "description": "Unsafe fixture tool that should be blocked by allow-list tests.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _result(request_id: int, result: dict) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if request_id is None:
            continue
        if method == "initialize":
            _result(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "serverInfo": {"name": "weather-fixture", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            )
        elif method == "tools/list":
            _result(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name == "get_weather":
                city = arguments.get("city") or "Unknown"
                _result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": f"{city}: sunny, 24C",
                            }
                        ],
                        "isError": False,
                    },
                )
            else:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"Unknown tool: {name}"},
                    }
                )
        else:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"},
                }
            )


if __name__ == "__main__":
    main()
