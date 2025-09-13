"""MCP server client for fetching tool information."""

import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, ValidationError

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
        **npx_kwargs,
    ):
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
        self._is_npx_server = is_npx_command(server_target)
        self._actual_server_url: Optional[str] = None

        # Determine transport type
        self._transport = self._detect_transport_type(transport)

        if not self._is_npx_server and self._transport == "http":
            # Traditional HTTP URL
            self._actual_server_url = server_target.rstrip("/")

    def _detect_transport_type(self, transport: str) -> str:
        """Detect the appropriate transport type."""
        if transport != "auto":
            return transport

        if self.server_target.startswith(("http://", "https://")):
            return "http"
        elif self._is_npx_server:
            return "stdio"
        else:
            return "stdio"

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_server_ready()

        if self._transport == "http":
            self._session = httpx.AsyncClient(timeout=self.timeout)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.aclose()
        if self._npx_manager:
            await self._npx_manager.stop_all_servers()
        if self._stdio_client:
            await self._stdio_client.close()

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if not self._session:
            self._session = httpx.AsyncClient(timeout=self.timeout)
        return self._session

    async def _ensure_server_ready(self) -> None:
        """Ensure the server is running and ready for communication."""
        if self._transport == "stdio":
            self._stdio_client = MCPStdioClient(
                self.server_target, timeout=self.timeout, **self.npx_kwargs
            )
            await self._stdio_client.__aenter__()
            logger.info(f"STDIO MCP client connected to: {self.server_target}")

        elif self._transport == "http" and self._is_npx_server:
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

    def get_server_url(self) -> str:
        """Get the actual server URL (after NPX launch if applicable)."""
        if self._transport == "stdio":
            return f"stdio://{self.server_target}"

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
                info = await self._stdio_client.get_server_info()
                return MCPServerInfo(
                    protocol_version=info.get("protocol_version"),
                    server_name=info.get("server_name", "MCP Server"),
                    server_version=info.get("server_version"),
                    capabilities=info.get("capabilities", {}),
                )
            else:
                server_url = self.get_server_url()
                session = await self._get_session()
                response = await session.get(server_url)

                if response.status_code == 404:
                    raise MCPClientError(
                        f"MCP server not found at {server_url}. "
                        f"Make sure the server is running and MCP is mounted."
                    )

                if response.status_code != 200:
                    raise MCPClientError(
                        f"Server returned status {response.status_code}: {response.text}"
                    )

                try:
                    data = response.json()
                except Exception as e:
                    raise MCPClientError(f"Invalid JSON response from server: {e}")

                return MCPServerInfo(
                    protocol_version=data.get("protocol_version"),
                    server_name=data.get("server_name", "Unknown"),
                    server_version=data.get("server_version"),
                    capabilities=data.get("capabilities", {}),
                )

        except httpx.ConnectError:
            raise MCPClientError(
                "Cannot connect to MCP server. Make sure the server is running."
            )
        except httpx.TimeoutException:
            raise MCPClientError(f"Request timed out after {self.timeout} seconds")
        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Unexpected error: {e}")

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
                tools_data = await self._stdio_client.list_tools()
            else:
                server_url = self.get_server_url()
                session = await self._get_session()
                response = await session.get(server_url)

                if response.status_code != 200:
                    raise MCPClientError(
                        f"Cannot fetch tools: Server returned {response.status_code}"
                    )

                data = response.json()
                tools_data = data.get("tools", [])

            if not tools_data:
                logger.warning("No tools found in MCP server response")
                return []

            tools = []
            for tool_data in tools_data:
                try:
                    # Handle different possible tool data formats
                    if isinstance(tool_data, str):
                        # If tool is just a name string
                        tool = MCPTool(name=tool_data)
                    elif isinstance(tool_data, dict):
                        # If tool is a dictionary with schema
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
            # This would depend on the MCP server's specific endpoint structure
            # For now, we'll try common patterns
            session = await self._get_session()

            # Try different possible endpoints
            endpoints = [
                f"{server_url}/tools/{tool_name}",
                f"{server_url}/tool/{tool_name}",
                f"{server_url}/schema/{tool_name}",
            ]

            for endpoint in endpoints:
                try:
                    response = await session.get(endpoint)
                    if response.status_code == 200:
                        return response.json()
                except httpx.HTTPStatusError:
                    continue

            logger.warning(f"No detailed endpoint found for tool: {tool_name}")
            return None

        except Exception as e:
            logger.error(f"Error fetching tool details for {tool_name}: {e}")
            return None

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
