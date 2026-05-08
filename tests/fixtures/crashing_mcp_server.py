from __future__ import annotations

import json
import sys


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    if not line.strip():
        continue
    request = json.loads(line)
    request_id = request.get("id")
    method = request.get("method")
    if request_id is None:
        continue
    if method == "initialize":
        _write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "crashing-fixture", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        )
    elif method == "tools/call":
        sys.stderr.write("fixture crash during tools/call\n")
        sys.stderr.flush()
        raise SystemExit(42)
    elif method == "tools/list":
        _write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "crash_tool",
                            "description": "Crash after receiving tools/call.",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ]
                },
            }
        )
