"""MCP server client for fetching tool information."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, cast

import httpx
from pydantic import BaseModel, ValidationError

from .mcp_sse_client import MCPSSEClient
from .mcp_stdio_client import MCPStdioClient
from .npx_launcher import NPXLauncherError, NPXServerManager, is_npx_command

logger = logging.getLogger(__name__)


class MCPServerInfo(BaseModel):
    """Information about the MCP server."""

    protocol_version: Optional[str] = None
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None


class MCPTool(BaseModel):
    """Representation of an MCP tool."""

    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None


class MCPClientError(Exception):
    """Custom exception for MCP client errors."""

    pass


class MCPClient:
    """Client for communicating with MCP servers."""

    def __init__(
        self,
        server_target: str,
        timeout: int = 30,
        transport: str = "auto",
        headers: Optional[Dict[str, str]] = None,
        **npx_kwargs: Any,
    ) -> None:
        """
        Initialize MCP client.

        Args:
            server_target: Either a URL (http://...) or NPX command (npx ...)
            timeout: Request timeout in seconds
            transport: Transport type ("auto", "http", "stdio")
            **npx_kwargs: Additional arguments for NPX server (env_vars, working_dir, etc.)
        """
        self.server_target = server_target
        self.timeout = timeout
        self.npx_kwargs = npx_kwargs
        self._session: Optional[httpx.AsyncClient] = None
        self._npx_manager: Optional[NPXServerManager] = None
        self._stdio_client: Optional[MCPStdioClient] = None
        self._sse_client: Optional[MCPSSEClient] = None
        self._is_npx_server = is_npx_command(server_target)
        self._actual_server_url: Optional[str] = None
        self._headers: Dict[str, str] = dict(headers or {})

        self._transport = self._detect_transport_type(transport)

        if not self._is_npx_server and self._transport == "http":

            self._actual_server_url = server_target.rstrip("/")

    def _detect_transport_type(self, transport: str) -> str:
        """Detect the appropriate transport type."""
        if transport != "auto":
            return transport

        if self.server_target.startswith(("http://", "https://")):
            return "http"  # Will probe for SSE vs REST during connection
        elif self._is_npx_server:
            return "stdio"
        else:
            return "stdio"

    async def _probe_http_endpoint(self, url: str) -> str:
        """Probe HTTP endpoint to determine if it's SSE or REST."""
        try:
            logger.info(f"Probing endpoint type for: {url}")

            async with httpx.AsyncClient(timeout=5.0, headers=self._headers) as client:
                try:
                    head_response = await client.head(url)
                    if head_response.status_code == 406:
                        logger.info(
                            "HEAD request returned 406 requiring text/event-stream; treating as SSE"
                        )
                        return "sse"
                    content_type = head_response.headers.get("content-type", "").lower()

                    if "text/event-stream" in content_type:
                        logger.info("Detected SSE endpoint (Server-Sent Events)")
                        return "sse"

                except httpx.HTTPStatusError:
                    pass

                try:
                    response = await asyncio.wait_for(client.get(url), timeout=3.0)

                    content_type = response.headers.get("content-type", "").lower()

                    if "text/event-stream" in content_type:
                        logger.info("Detected SSE endpoint via GET response")
                        return "sse"
                    elif response.status_code == 406:
                        logger.info(
                            "Endpoint returned 406 requiring text/event-stream; treating as SSE"
                        )
                        return "sse"
                    elif "application/json" in content_type:
                        logger.info("Detected REST API endpoint")
                        return "http"
                    else:
                        logger.info(
                            f"Unknown content type: {content_type}, defaulting to REST"
                        )
                        return "http"

                except asyncio.TimeoutError:
                    logger.warning("Quick probe timed out, might be SSE endpoint")
                    return "sse"

        except Exception as e:
            logger.warning(f"Failed to probe endpoint: {e}, defaulting to REST")
            return "http"

    async def _try_get_server_info_from_sse(self, sse_url: str) -> str:
        """Try to get server information from SSE endpoint or related paths."""
        try:
            if sse_url.endswith("/mcp"):
                base_url = sse_url[:-4]  # Remove '/mcp'
            else:
                base_url = sse_url.rstrip("/")

            info_paths = ["/", "/info", "/status", "/health"]

            async with httpx.AsyncClient(timeout=5.0, headers=self._headers) as client:
                for path in info_paths:
                    try:
                        test_url = f"{base_url}{path}"
                        logger.debug(f"Trying server info from: {test_url}")
                        response = await client.get(test_url)

                        if response.status_code == 200:
                            data = response.json()
                            if isinstance(data, dict):
                                name = data.get("message", data.get("name", "Unknown"))
                                version = data.get("version", "Unknown")

                                details = []
                                if "documentation" in data:
                                    details.append("Has API documentation")
                                if "endpoints" in data:
                                    endpoint_count = len(data["endpoints"])
                                    details.append(f"{endpoint_count} endpoints")
                                if "github" in data:
                                    details.append("Open source")

                                info_str = f"{name} v{version}"
                                if details:
                                    info_str += f" ({', '.join(details)})"

                                return info_str

                    except Exception as e:
                        logger.debug(f"Failed to get info from {test_url}: {e}")
                        continue

            return "Server information not available"

        except Exception as e:
            logger.debug(f"Error getting server info: {e}")
            return "Unable to retrieve server information"

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        await self._ensure_server_ready()

        if self._transport == "http":
            self._session = httpx.AsyncClient(
                timeout=self.timeout, headers=self._headers
            )

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._session:
            await self._session.aclose()
        if self._npx_manager:
            await self._npx_manager.stop_all_servers()
        if self._stdio_client:
            await self._stdio_client.close()
        if self._sse_client:
            await self._sse_client.close()

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if not self._session:
            self._session = httpx.AsyncClient(
                timeout=self.timeout, headers=self._headers
            )
        return self._session

    async def _ensure_server_ready(self) -> None:
        """Ensure the server is running and ready for communication."""
        if self._transport == "stdio":
            self._stdio_client = MCPStdioClient(
                self.server_target, timeout=self.timeout, **self.npx_kwargs
            )
            await self._stdio_client.__aenter__()
            logger.info(f"STDIO MCP client connected to: {self.server_target}")

        elif self._transport == "http":
            if self._is_npx_server:
                # Launch NPX server for HTTP transport
                if not self._npx_manager:
                    self._npx_manager = NPXServerManager()

                try:
                    logger.info(f"Launching NPX server: {self.server_target}")
                    self._actual_server_url = await self._npx_manager.launch_server(
                        self.server_target, timeout=self.timeout, **self.npx_kwargs
                    )
                    logger.info(f"NPX server ready at: {self._actual_server_url}")
                except NPXLauncherError as e:
                    raise MCPClientError(f"Failed to launch NPX server: {e}")
            else:
                # For HTTP URLs, probe to detect SSE vs REST
                actual_transport = await self._probe_http_endpoint(self.server_target)
                if actual_transport == "sse":
                    # Update transport type and try SSE connection
                    self._transport = "sse"
                    logger.info("Switching to SSE transport")

                    try:
                        self._sse_client = MCPSSEClient(
                            self.server_target,
                            timeout=self.timeout,
                            headers=self._headers,
                        )
                        await self._sse_client.__aenter__()
                        logger.info(
                            f"SSE MCP client connected to: {self.server_target}"
                        )
                    except Exception as e:
                        # If SSE connection fails, provide helpful guidance
                        server_info = await self._try_get_server_info_from_sse(
                            self.server_target
                        )

                        raise MCPClientError(
                            f"🌊 Detected SSE (Server-Sent Events) endpoint at {self.server_target}.\n\n"
                            f"📋 Server Info: {server_info}\n\n"
                            f"❌ SSE connection failed: {e}\n\n"
                            f"🔍 This endpoint might be:\n"
                            f"   • A non-standard MCP implementation\n"
                            f"   • An API proxy rather than a direct MCP server\n"
                            f"   • Using a custom SSE protocol\n\n"
                            f"💡 Try these alternatives:\n"
                            f"   1. Official MCP Inspector: npx @modelcontextprotocol/inspector --cli {self.server_target} --transport sse\n"
                            f"   2. Check server documentation for proper MCP endpoints\n"
                            f"   3. Contact the server maintainer for MCP compatibility details"
                        )

    def get_server_url(self) -> str:
        """Get the actual server URL (after NPX launch if applicable)."""
        if self._transport == "stdio":
            return f"stdio://{self.server_target}"
        elif self._transport == "sse":
            return f"sse://{self.server_target}"

        if not self._actual_server_url:
            raise MCPClientError(
                "Server URL not available. Call _ensure_server_ready() first."
            )
        return self._actual_server_url

    async def get_server_info(self) -> MCPServerInfo:
        """
        Fetch basic server information.

        Returns:
            Server information including protocol version and capabilities

        Raises:
            MCPClientError: If server is unreachable or invalid
        """
        await self._ensure_server_ready()

        try:
            if self._transport == "stdio":
                if not self._stdio_client:
                    raise MCPClientError("STDIO client not initialized")
                info = await self._stdio_client.get_server_info()
                return MCPServerInfo(
                    protocol_version=info.get("protocol_version"),
                    server_name=info.get("server_name", "MCP Server"),
                    server_version=info.get("server_version"),
                    capabilities=info.get("capabilities", {}),
                )
            elif self._transport == "sse":
                if not self._sse_client:
                    raise MCPClientError("SSE client not initialized")
                info = await self._sse_client.get_server_info()
                return MCPServerInfo(
                    protocol_version=info.get("protocol_version"),
                    server_name=info.get("server_name", "SSE MCP Server"),
                    server_version=info.get("server_version"),
                    capabilities=info.get("capabilities", {}),
                )
            else:
                # HTTP transport with enhanced debugging
                server_url = self.get_server_url()
                logger.info(f"Making HTTP request to: {server_url}")

                session = await self._get_session()

                try:
                    # Add explicit timeout wrapper
                    response = await asyncio.wait_for(
                        session.get(server_url), timeout=self.timeout
                    )
                    logger.info(f"HTTP response: {response.status_code}")

                except asyncio.TimeoutError:
                    raise MCPClientError(
                        f"HTTP request timed out after {self.timeout} seconds. "
                        f"The server at {server_url} is not responding."
                    )

                if response.status_code == 404:
                    raise MCPClientError(
                        f"MCP server not found at {server_url} (404). "
                        f"Make sure the server is running and MCP is mounted at the correct path."
                    )

                if response.status_code != 200:
                    # Include response body for better debugging
                    try:
                        error_body = response.text[:200]
                    except Exception:
                        error_body = "Unable to read response body"

                    raise MCPClientError(
                        f"Server returned status {response.status_code}. "
                        f"Response: {error_body}"
                    )

                try:
                    data = response.json()
                    logger.debug(
                        f"Server response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
                    )
                except Exception as e:
                    # Include response content for debugging
                    try:
                        content_preview = response.text[:200]
                    except Exception:
                        content_preview = "Unable to read response content"

                    raise MCPClientError(
                        f"Invalid JSON response from server: {e}. "
                        f"Response content: {content_preview}"
                    )

                return MCPServerInfo(
                    protocol_version=data.get("protocol_version"),
                    server_name=data.get("server_name", "Unknown"),
                    server_version=data.get("server_version"),
                    capabilities=data.get("capabilities", {}),
                )

        except httpx.ConnectError as e:
            raise MCPClientError(
                f"Cannot connect to MCP server at {self.get_server_url()}. "
                f"Connection error: {e}. Make sure the server is running and accessible."
            )
        except httpx.TimeoutException:
            raise MCPClientError(
                f"HTTP request timed out after {self.timeout} seconds. "
                f"The server at {self.get_server_url()} is taking too long to respond."
            )
        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Unexpected error connecting to HTTP server: {e}")

    async def get_tools(self) -> List[MCPTool]:
        """
        Fetch all available tools from the MCP server.

        Returns:
            List of tools with their schemas and descriptions

        Raises:
            MCPClientError: If tools cannot be fetched
        """
        await self._ensure_server_ready()

        try:
            if self._transport == "stdio":
                if not self._stdio_client:
                    raise MCPClientError("STDIO client not initialized")
                tools_data = await self._stdio_client.list_tools()
            elif self._transport == "sse":
                if not self._sse_client:
                    raise MCPClientError("SSE client not initialized")
                tools_data = await self._sse_client.list_tools()
            else:
                server_url = self.get_server_url()
                session = await self._get_session()

                try:
                    response = await asyncio.wait_for(
                        session.get(server_url), timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    raise MCPClientError(
                        f"HTTP request for tools timed out after {self.timeout} seconds. "
                        f"The server at {server_url} is not responding."
                    )

                if response.status_code != 200:
                    try:
                        error_body = response.text[:200]
                    except Exception:
                        error_body = "Unable to read response body"

                    raise MCPClientError(
                        f"Cannot fetch tools: Server returned {response.status_code}. "
                        f"Response: {error_body}"
                    )

                try:
                    data = response.json()
                except Exception as e:
                    try:
                        content_preview = response.text[:200]
                    except Exception:
                        content_preview = "Unable to read response content"

                    raise MCPClientError(
                        f"Invalid JSON response when fetching tools: {e}. "
                        f"Response content: {content_preview}"
                    )

                tools_data = data.get("tools", [])

            if not tools_data:
                logger.warning("No tools found in MCP server response")
                return []

            tools = []
            for tool_data in tools_data:
                try:

                    if isinstance(tool_data, str):

                        tool = MCPTool(name=tool_data)
                    elif isinstance(tool_data, dict):

                        tool = MCPTool(
                            name=tool_data.get("name", "unnamed_tool"),
                            description=tool_data.get("description"),
                            input_schema=tool_data.get("inputSchema"),
                            parameters=tool_data.get("parameters"),
                        )
                    else:
                        logger.warning(
                            f"Unexpected tool data format: {type(tool_data)}"
                        )
                        continue

                    tools.append(tool)

                except ValidationError as e:
                    logger.warning(f"Failed to parse tool data: {e}")
                    continue

            return tools

        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Failed to fetch tools: {e}")

    async def get_tool_details(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific tool.

        Args:
            tool_name: Name of the tool to get details for

        Returns:
            Detailed tool information if available
        """
        await self._ensure_server_ready()
        server_url = self.get_server_url()

        try:

            session = await self._get_session()

            endpoints = [
                f"{server_url}/tools/{tool_name}",
                f"{server_url}/tool/{tool_name}",
                f"{server_url}/schema/{tool_name}",
            ]

            for endpoint in endpoints:
                try:
                    response = await session.get(endpoint)
                    if response.status_code == 200:
                        return cast(Dict[str, Any], response.json())
                except httpx.HTTPStatusError:
                    continue

            logger.warning(f"No detailed endpoint found for tool: {tool_name}")
            return None

        except Exception as e:
            logger.error(f"Error fetching tool details for {tool_name}: {e}")
            return None

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool with the given arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result

        Raises:
            MCPClientError: If the tool call fails
        """
        await self._ensure_server_ready()

        try:
            if self._stdio_client:
                # Use STDIO client for NPX servers
                return await self._stdio_client.call_tool(tool_name, arguments)
            elif self._sse_client:
                # Use SSE client for SSE servers
                return await self._sse_client.call_tool(tool_name, arguments)
            else:
                raise NotImplementedError("HTTP transport not supported")
        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Failed to call tool {tool_name}: {e}")

    async def close(self) -> None:
        """Close connections and stop servers."""
        if self._session:
            await self._session.aclose()
            self._session = None
        if self._npx_manager:
            await self._npx_manager.stop_all_servers()
            self._npx_manager = None
        if self._stdio_client:
            await self._stdio_client.close()
            self._stdio_client = None
        if self._sse_client:
            await self._sse_client.close()
            self._sse_client = None
