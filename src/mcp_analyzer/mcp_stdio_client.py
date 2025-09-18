"""STDIO-based MCP client for direct subprocess communication."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .npx_launcher import is_npx_command, parse_npx_command

logger = logging.getLogger(__name__)


class MCPMessage(BaseModel):
    """MCP protocol message."""

    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class MCPStdioClient:
    """MCP client that communicates via STDIO with subprocess."""

    def __init__(self, command: str, timeout: int = 30, **kwargs: Any) -> None:
        """
        Initialize STDIO MCP client.

        Args:
            command: NPX command or executable path
            timeout: Request timeout in seconds
            **kwargs: Additional arguments (env_vars, working_dir, etc.)
        """
        self.command = command
        self.timeout = timeout
        self.kwargs = kwargs
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._is_npx = is_npx_command(command)
        self._response_queue: Queue[MCPMessage] = Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

    async def __aenter__(self) -> MCPStdioClient:
        """Async context manager entry."""
        await self._start_process()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _start_process(self) -> None:
        """Start the MCP server process."""
        if self._is_npx:

            npx_command, env_vars = parse_npx_command(self.command)
            cmd_parts = npx_command.split()

            env = self.kwargs.get("env_vars", {})
            env.update(env_vars)
        else:
            cmd_parts = self.command.split()
            env = self.kwargs.get("env_vars", {})

        full_env = dict(os.environ)
        full_env.update(env)

        logger.info(f"Starting MCP server process: {' '.join(cmd_parts)}")

        self.process = subprocess.Popen(
            cmd_parts,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=self.kwargs.get("working_dir"),
            env=full_env,
        )

        logger.info(f"MCP server process started with PID: {self.process.pid}")

        self._running = True
        self._reader_thread = threading.Thread(target=self._read_messages, daemon=True)
        self._reader_thread.start()

        await self._initialize_connection()

    def _read_messages(self) -> None:
        """Read messages from subprocess in a separate thread."""
        try:
            while self._running and self.process and self.process.stdout:
                try:
                    line = self.process.stdout.readline()
                    if not line:

                        break

                    line = line.strip()
                    if not line:
                        continue

                    logger.debug(f"Received raw message: {line}")

                    try:
                        message_data = json.loads(line)
                        message = MCPMessage(**message_data)
                        self._response_queue.put(message)
                        logger.debug(f"Queued message: {message}")
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Failed to parse message: {e}")
                        continue

                except Exception as e:
                    logger.error(f"Error reading from process: {e}")
                    break

        except Exception as e:
            logger.error(f"Reader thread error: {e}")
        finally:
            logger.debug("Reader thread stopped")

    async def _initialize_connection(self) -> None:
        """Initialize MCP protocol connection."""
        logger.info("Initializing MCP connection...")

        init_request = MCPMessage(
            id=self._next_id(),
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "mcp-analyzer", "version": "0.1.0"},
            },
        )

        response = await self._send_request(init_request)
        if response.error:
            raise Exception(f"Failed to initialize MCP connection: {response.error}")

        logger.info("MCP connection initialized successfully")

        initialized_notification = MCPMessage(method="notifications/initialized")
        await self._send_notification(initialized_notification)

    def _next_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def _send_request(self, message: MCPMessage) -> MCPMessage:
        """Send a request and wait for response."""
        if not self.process or not self.process.stdin:
            raise Exception("Process not started")

        request_json = message.model_dump(exclude_none=True)
        request_line = json.dumps(request_json) + "\n"

        logger.debug(f"Sending MCP request: {request_line.strip()}")
        self.process.stdin.write(request_line)
        self.process.stdin.flush()

        if message.id is not None:
            response = await self._wait_for_response(message.id)
            return response
        else:
            return MCPMessage()

    async def _send_notification(self, message: MCPMessage) -> None:
        """Send a notification (no response expected)."""
        await self._send_request(message)

    async def _wait_for_response(self, request_id: int) -> MCPMessage:
        """Wait for a response with the given request ID."""
        start_time = time.time()

        while time.time() - start_time < self.timeout:

            if self.process and self.process.poll() is not None:
                stderr_output = ""
                if self.process.stderr:
                    try:
                        stderr_output = self.process.stderr.read()
                    except Exception:
                        pass
                raise Exception(
                    f"MCP process terminated unexpectedly (exit code: {self.process.returncode}). Stderr: {stderr_output}"
                )

            try:

                message = self._response_queue.get(timeout=0.1)

                if message.id == request_id:
                    logger.debug(f"Found matching response for request {request_id}")
                    return message
                else:

                    self._response_queue.put(message)
                    logger.debug(
                        f"Received response ID {message.id}, still waiting for {request_id}"
                    )
                    await asyncio.sleep(0.01)
                    continue

            except Empty:

                await asyncio.sleep(0.01)
                continue

        raise asyncio.TimeoutError(
            f"Request {request_id} timed out after {self.timeout}s"
        )

    async def get_server_info(self) -> Dict[str, Any]:
        """Get server information."""

        return {
            "protocol_version": "2024-11-05",
            "server_name": "MCP Server",
            "server_version": "unknown",
            "capabilities": {},
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools."""
        request = MCPMessage(id=self._next_id(), method="tools/list")

        response = await self._send_request(request)

        if response.error:
            raise Exception(f"Failed to list tools: {response.error}")

        tools = response.result.get("tools", []) if response.result else []
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool."""
        request = MCPMessage(
            id=self._next_id(),
            method="tools/call",
            params={"name": name, "arguments": arguments},
        )

        response = await self._send_request(request)

        if response.error:
            raise Exception(f"Failed to call tool {name}: {response.error}")

        return response.result or {}

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources."""
        request = MCPMessage(id=self._next_id(), method="resources/list")

        response = await self._send_request(request)

        if response.error:
            raise Exception(f"Failed to list resources: {response.error}")

        resources = response.result.get("resources", []) if response.result else []
        return resources

    async def close(self) -> None:
        """Close the MCP connection and terminate process."""

        self._running = False

        if self.process:
            try:

                self.process.terminate()

                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(self.process.wait), timeout=5.0
                    )
                except asyncio.TimeoutError:

                    logger.warning("Graceful shutdown timed out, force killing process")
                    self.process.kill()

                self.process = None
                logger.info("MCP server process terminated")

            except Exception as e:
                logger.error(f"Error closing MCP connection: {e}")

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)
