from __future__ import annotations

import json
import sys


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _spam_stderr() -> None:
    for index in range(200):
        sys.stderr.write(f"stderr-line-{index}\n")
    sys.stderr.flush()


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
        _spam_stderr()
        _write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "stderr-spam-fixture", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        )
    elif method == "tools/list":
        _spam_stderr()
        _write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo_tool",
                            "description": "Echo the provided text.",
                            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                        }
                    ]
                },
            }
        )
    elif method == "tools/call":
        _spam_stderr()
        text = (params.get("arguments") or {}).get("text") or "ok"
        _write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": str(text)}], "isError": False},
            }
        )
