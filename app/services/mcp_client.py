from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any


class MCPClientError(RuntimeError):
    def __init__(self, reason: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


class MCPTimeoutError(MCPClientError):
    pass


@dataclass(slots=True)
class MCPStdioClient:
    command: str
    args: list[str] = field(default_factory=list)
    timeout_ms: int = 3000
    protocol_version: str = "2024-11-05"

    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _stdout_queue: queue.Queue[str] = field(default_factory=queue.Queue, init=False, repr=False)
    _stderr_lines: list[str] = field(default_factory=list, init=False, repr=False)
    _reader_threads: list[threading.Thread] = field(default_factory=list, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)

    def __enter__(self) -> MCPStdioClient:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start(self) -> None:
        if self._process:
            return
        try:
            self._process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise MCPClientError(
                "mcp_stdio_start_failed",
                f"Failed to start MCP stdio server: {exc}",
                {"command": self.command, "args": self.args},
            ) from exc
        self._reader_threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for thread in self._reader_threads:
            thread.start()

    def initialize(self) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "UEAgentBackend", "version": "0.1.0"},
            },
        )
        self.notify("notifications/initialized", {})
        return result

    def list_tools(self) -> dict[str, Any]:
        return self.request("tools/list", {})

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_request_id()
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        response = self._read_response(request_id)
        if "error" in response:
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            raise MCPClientError(
                "mcp_jsonrpc_error",
                str(error.get("message") or "MCP JSON-RPC error."),
                {"code": error.get("code"), "data": error.get("data"), "method": method},
            )
        result = response.get("result")
        return result if isinstance(result, dict) else {"value": result}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        process = self._process
        self._process = None
        if not process:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=max(self.timeout_ms / 1000, 0.5))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    @property
    def stderr_excerpt(self) -> str:
        return "\n".join(self._stderr_lines[-10:])

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, payload: dict[str, Any]) -> None:
        process = self._require_process()
        if not process.stdin:
            raise MCPClientError("mcp_stdio_closed", "MCP stdio stdin is closed.")
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            process.stdin.write(line + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise MCPClientError(
                "mcp_stdio_write_failed",
                f"Failed to write MCP request: {exc}",
                {"stderr": self.stderr_excerpt},
            ) from exc

    def _read_response(self, request_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + max(self.timeout_ms / 1000, 0.1)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPTimeoutError(
                    "mcp_stdio_timeout",
                    "Timed out waiting for MCP response.",
                    {"request_id": request_id, "stderr": self.stderr_excerpt},
                )
            try:
                line = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise MCPTimeoutError(
                    "mcp_stdio_timeout",
                    "Timed out waiting for MCP response.",
                    {"request_id": request_id, "stderr": self.stderr_excerpt},
                ) from exc
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._stderr_lines.append(f"non_json_stdout: {line[:300]}")
                continue
            if message.get("id") == request_id:
                return message

    def _require_process(self) -> subprocess.Popen[str]:
        if not self._process:
            self.start()
        assert self._process is not None
        if self._process.poll() is not None:
            raise MCPClientError(
                "mcp_stdio_process_exited",
                "MCP stdio server exited before completing the request.",
                {"returncode": self._process.returncode, "stderr": self.stderr_excerpt},
            )
        return self._process

    def _read_stdout(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            self._stdout_queue.put(line.rstrip("\r\n"))

    def _read_stderr(self) -> None:
        process = self._process
        if not process or not process.stderr:
            return
        for line in process.stderr:
            self._stderr_lines.append(line.rstrip("\r\n"))
            if len(self._stderr_lines) > 50:
                del self._stderr_lines[: len(self._stderr_lines) - 50]
