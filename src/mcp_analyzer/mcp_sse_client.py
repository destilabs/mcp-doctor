"""SSE-based MCP client for Server-Sent Events transport."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urljoin, urlparse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MCPMessage(BaseModel):
    """MCP protocol message."""

    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class MCPSSEClient:
    """MCP client that communicates via Server-Sent Events."""

    def __init__(
        self,
        sse_url: str,
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize SSE MCP client.

        Args:
            sse_url: SSE endpoint URL
            timeout: Request timeout in seconds
        """
        self.sse_url = sse_url
        self.timeout = timeout
        self._session: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
        self._messages_url: Optional[str] = None
        self._request_id = 0
        self._pending_requests: Dict[str, asyncio.Future[MCPMessage]] = {}
        self._running = False
        self._sse_listener_task: Optional[asyncio.Task] = None
        self._endpoint_event: Optional[asyncio.Event] = None
        self._protocol_version: Optional[str] = None
        self._server_capabilities: Dict[str, Any] = {}
        self._server_info: Dict[str, Any] = {}
        self._instructions: Optional[str] = None
        self._custom_headers = headers or {}

    async def __aenter__(self) -> MCPSSEClient:
        """Async context manager entry."""
        await self._connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _connect(self) -> None:
        """Connect to the SSE endpoint and establish session."""
        logger.info(f"Connecting to SSE endpoint: {self.sse_url}")

        timeout_config = httpx.Timeout(self.timeout, read=None)
        self._session = httpx.AsyncClient(timeout=timeout_config)

        self._running = True
        self._endpoint_event = asyncio.Event()
        self._sse_listener_task = asyncio.create_task(self._listen_to_sse_stream())

        try:
            await asyncio.wait_for(self._endpoint_event.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise Exception("Timed out waiting for SSE endpoint from server")

        await self._initialize_mcp_connection()

        logger.info("SSE MCP connection established successfully")

    async def _initialize_mcp_connection(self) -> None:
        """Initialize MCP protocol over SSE."""
        logger.info("Initializing MCP protocol over SSE...")

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

        if response.result:
            self._protocol_version = response.result.get("protocolVersion")
            self._server_capabilities = response.result.get("capabilities", {})
            self._server_info = response.result.get("serverInfo", {})
            self._instructions = response.result.get("instructions")

        logger.info("MCP connection initialized over SSE")

        initialized_notification = MCPMessage(method="notifications/initialized")
        await self._send_notification(initialized_notification)

    def _next_id(self) -> str:
        """Get next request ID."""
        return str(uuid.uuid4())

    async def _send_request(self, message: MCPMessage) -> MCPMessage:
        """Send a request over SSE and wait for response."""
        if not self._messages_url:
            raise Exception("SSE connection not established")

        request_data = message.model_dump(exclude_none=True)
        logger.debug(f"Sending SSE request: {json.dumps(request_data)}")

        try:
            headers = {"Content-Type": "application/json"}
            if self._protocol_version:
                headers["mcp-protocol-version"] = self._protocol_version
            headers.update(self._custom_headers)

            response = await self._session.post(
                self._messages_url,
                json=request_data,
                headers=headers,
            )

            logger.debug(f"SSE POST response: {response.status_code}")

            if response.status_code in (200, 202, 204):
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        logger.debug(f"Immediate SSE response: {response_data}")
                        return MCPMessage(**response_data)
                    except Exception:
                        pass

                if message.id is not None:
                    logger.debug(f"Waiting for SSE response for ID: {message.id}")
                    return await self._wait_for_sse_response(message.id)
                return MCPMessage()

            error_text = await self._safe_read_text(response)
            raise Exception(
                f"SSE request failed with status {response.status_code}: {error_text}"
            )
        except Exception as e:
            raise Exception(f"Failed to send SSE request: {e}")

    async def _send_notification(self, message: MCPMessage) -> None:
        """Send a notification over SSE."""
        await self._send_request(message)

    async def _listen_to_sse_stream(self) -> None:
        """Listen for SSE responses in the background."""
        try:
            logger.info("Starting SSE response listener...")

            while self._running:
                try:
                    async with self._session.stream(
                        "GET",
                        self.sse_url,
                        headers=self._sse_headers(),
                    ) as response:
                        if response.status_code != 200:
                            text = await self._safe_read_text(response)
                            logger.warning(
                                "SSE listener connection failed: %s (%s)",
                                response.status_code,
                                text,
                            )
                            await asyncio.sleep(1.0)
                            continue

                        logger.info("SSE stream connected")

                        async for event_name, data in self._iter_sse_events(response):
                            if not self._running:
                                break

                            if event_name == "endpoint":
                                self._handle_endpoint_event(data)
                            elif event_name == "message":
                                await self._handle_message_event(data)
                            else:
                                logger.debug(
                                    "Ignoring SSE event %s with data: %s",
                                    event_name,
                                    data,
                                )

                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if self._running:
                        logger.warning(f"SSE listener error: {e}")
                        await asyncio.sleep(1.0)
                    else:
                        break
        except Exception as e:
            logger.error(f"SSE listener failed: {e}")
        finally:
            logger.debug("SSE listener stopped")

    async def _wait_for_sse_response(self, request_id: str) -> MCPMessage:
        """Wait for SSE response with specific request ID."""
        # Create a future for this request
        future: asyncio.Future[MCPMessage] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            response = await asyncio.wait_for(future, timeout=self.timeout)
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise asyncio.TimeoutError(
                f"SSE request {request_id} timed out after {self.timeout}s"
            )

    async def get_server_info(self) -> Dict[str, Any]:
        """Get server information."""

        info = {
            "protocol_version": self._protocol_version,
            "server_name": self._server_info.get("name", "SSE MCP Server"),
            "server_version": self._server_info.get("version", "unknown"),
            "capabilities": self._server_capabilities,
            "transport": "sse",
        }
        if self._instructions:
            info["instructions"] = self._instructions
        return info

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools via SSE."""
        request = MCPMessage(id=self._next_id(), method="tools/list")

        response = await self._send_request(request)

        if response.error:
            raise Exception(f"Failed to list tools: {response.error}")

        tools = response.result.get("tools", []) if response.result else []
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via SSE."""
        request = MCPMessage(
            id=self._next_id(),
            method="tools/call",
            params={"name": name, "arguments": arguments},
        )

        response = await self._send_request(request)

        if response.error:
            raise Exception(f"Failed to call tool {name}: {response.error}")

        return response.result or {}

    async def close(self) -> None:
        """Close the SSE connection."""
        self._running = False

        # Cancel the SSE listener task
        if self._sse_listener_task and not self._sse_listener_task.done():
            self._sse_listener_task.cancel()
            try:
                await self._sse_listener_task
            except asyncio.CancelledError:
                pass

        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        if self._session:
            await self._session.aclose()
            self._session = None

        logger.info("SSE MCP connection closed")

    async def _handle_message_event(self, data: str) -> None:
        if not data:
            return

        try:
            message_data = json.loads(data)
            message = MCPMessage(**message_data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug(f"Failed to parse SSE data as MCP message: {exc}")
            return

        if message.id and message.id in self._pending_requests:
            future = self._pending_requests.pop(message.id)
            if not future.done():
                future.set_result(message)
                logger.debug(f"Resolved pending request {message.id}")
        else:
            logger.debug(f"Received unsolicited SSE message: {message}")

    def _handle_endpoint_event(self, data: str) -> None:
        if not data:
            return

        try:
            messages_url = urljoin(self.sse_url, data.strip())
        except Exception as exc:
            logger.error(f"Invalid endpoint data from SSE stream: {exc}")
            return

        parsed = urlparse(messages_url)
        if parsed.scheme not in {"http", "https"}:
            logger.error(f"Unsupported SSE endpoint URL: {messages_url}")
            return

        self._messages_url = messages_url
        if parsed.query:
            query_parts = dict(parse_qsl(parsed.query, keep_blank_values=True))
            self._session_id = query_parts.get("session_id")

        logger.info(f"Received SSE messages endpoint: {self._messages_url}")

        if self._endpoint_event and not self._endpoint_event.is_set():
            self._endpoint_event.set()

    async def _iter_sse_events(
        self, response: httpx.Response
    ) -> AsyncIterator[Tuple[str, str]]:
        event_name = "message"
        data_lines: List[str] = []

        async for raw_line in response.aiter_lines():
            if raw_line is None:
                continue

            line = raw_line.strip("\r")

            if line == "":
                if data_lines:
                    data = "\n".join(data_lines)
                    yield event_name or "message", data
                event_name = "message"
                data_lines = []
                continue

            if line.startswith(":"):
                continue

            field, _, value = line.partition(":")
            value = value.lstrip(" ")

            if field == "event":
                event_name = value or "message"
            elif field == "data":
                data_lines.append(value)

        if data_lines:
            data = "\n".join(data_lines)
            yield event_name or "message", data

    def _sse_headers(self) -> Dict[str, str]:
        headers = {"Accept": "text/event-stream"}
        if self._protocol_version:
            headers["mcp-protocol-version"] = self._protocol_version
        headers.update(self._custom_headers)
        return headers

    @staticmethod
    async def _safe_read_text(response: httpx.Response) -> str:
        try:
            raw = await response.aread()
            return raw.decode()
        except Exception:
            try:
                return response.text
            except Exception:
                return "Unable to read response body"
