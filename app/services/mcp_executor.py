from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.mcp_tool_adapter import MCPToolAdapter


class MCPToolExecutor:
    def __init__(self, settings: Settings):
        self.adapter = MCPToolAdapter(settings)

    def discover_tools(self) -> dict[str, Any]:
        return self.adapter.discover_tools()

    def call_readonly_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.adapter.call_readonly_tool(tool_name, arguments or {})
        transport = self._transport_from_result(result)
        if not result.get("ok"):
            return {
                "ok": False,
                "status": result.get("status") or "error",
                "reason": result.get("reason") or "mcp_call_failed",
                "tool_name": tool_name,
                "transport": transport,
                "result": {},
                "errors": [result],
            }
        return {
            "ok": True,
            "status": "completed",
            "reason": "mcp_tool_call_completed",
            "tool_name": tool_name,
            "transport": transport,
            "result": result.get("result") or {},
            "errors": [],
            "debug": result.get("debug") or {},
        }

    @staticmethod
    def _transport_from_result(result: dict[str, Any]) -> str:
        debug = result.get("debug") if isinstance(result.get("debug"), dict) else {}
        adapter = debug.get("adapter") if isinstance(debug.get("adapter"), dict) else {}
        return str(result.get("transport") or adapter.get("transport") or "mcp_stdio")
