from __future__ import annotations

import json
import queue
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TextIO


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


@dataclass(slots=True)
class MCPTcpClient:
    host: str = "127.0.0.1"
    port: int = 8765
    timeout_ms: int = 3000
    protocol_version: str = "2024-11-05"

    _socket: socket.socket | None = field(default=None, init=False, repr=False)
    _reader: TextIO | None = field(default=None, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)

    def __enter__(self) -> MCPTcpClient:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start(self) -> None:
        if self._socket:
            return
        timeout_seconds = max(self.timeout_ms / 1000, 0.1)
        try:
            self._socket = socket.create_connection((self.host, self.port), timeout=timeout_seconds)
            self._socket.settimeout(timeout_seconds)
            self._reader = self._socket.makefile("r", encoding="utf-8", newline="\n")
        except OSError as exc:
            self.close()
            raise MCPClientError(
                "mcp_tcp_connect_failed",
                f"Failed to connect to MCP TCP endpoint {self.host}:{self.port}: {exc}",
                {"host": self.host, "port": self.port},
            ) from exc

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
        reader = self._reader
        self._reader = None
        if reader:
            try:
                reader.close()
            except OSError:
                pass
        connection = self._socket
        self._socket = None
        if connection:
            try:
                connection.close()
            except OSError:
                pass

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, payload: dict[str, Any]) -> None:
        connection = self._require_socket()
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            connection.sendall(line.encode("utf-8"))
        except OSError as exc:
            raise MCPClientError(
                "mcp_tcp_write_failed",
                f"Failed to write MCP TCP request: {exc}",
                {"host": self.host, "port": self.port},
            ) from exc

    def _read_response(self, request_id: int) -> dict[str, Any]:
        reader = self._require_reader()
        deadline = time.monotonic() + max(self.timeout_ms / 1000, 0.1)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPTimeoutError(
                    "mcp_tcp_timeout",
                    "Timed out waiting for MCP TCP response.",
                    {"request_id": request_id, "host": self.host, "port": self.port},
                )
            self._require_socket().settimeout(max(remaining, 0.1))
            try:
                line = reader.readline()
            except TimeoutError as exc:
                raise MCPTimeoutError(
                    "mcp_tcp_timeout",
                    "Timed out waiting for MCP TCP response.",
                    {"request_id": request_id, "host": self.host, "port": self.port},
                ) from exc
            except OSError as exc:
                raise MCPClientError(
                    "mcp_tcp_read_failed",
                    f"Failed to read MCP TCP response: {exc}",
                    {"request_id": request_id, "host": self.host, "port": self.port},
                ) from exc
            if not line:
                raise MCPClientError(
                    "mcp_tcp_closed",
                    "MCP TCP endpoint closed the connection before completing the request.",
                    {"request_id": request_id, "host": self.host, "port": self.port},
                )
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                return message

    def _require_socket(self) -> socket.socket:
        if not self._socket:
            self.start()
        assert self._socket is not None
        return self._socket

    def _require_reader(self) -> TextIO:
        if not self._reader:
            self.start()
        assert self._reader is not None
        return self._reader
