"""FastMCP-based OAuth client for MCP servers."""

import logging
from typing import Any, Dict, List, Optional

from fastmcp import Client as FastMCPClient

from .mcp_client import MCPTool

logger = logging.getLogger(__name__)


class FastMCPOAuthClient:
    """Wrapper around FastMCP client with OAuth support for MCP servers."""

    def __init__(self, server_url: str, timeout: int = 30):
        """
        Initialize FastMCP OAuth client.

        Args:
            server_url: MCP server URL (http://... or https://...)
            timeout: Request timeout in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[FastMCPClient] = None

    async def __aenter__(self) -> "FastMCPOAuthClient":
        """Async context manager entry."""
        logger.info(f"Initializing OAuth connection to {self.server_url}")

        self._client = FastMCPClient(self.server_url, auth="oauth")
        await self._client.__aenter__()

        logger.info("✅ OAuth authentication successful!")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
            self._client = None

    async def get_server_info(self) -> Dict[str, Any]:
        """
        Fetch server information.

        Returns:
            Server information dictionary
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        init_result = self._client.initialize_result
        if not init_result:
            raise RuntimeError("Client not properly initialized")

        return {
            "protocol_version": init_result.protocolVersion,
            "server_name": init_result.serverInfo.name if init_result.serverInfo else "FastMCP Server",
            "server_version": init_result.serverInfo.version if init_result.serverInfo else "unknown",
            "capabilities": init_result.capabilities.model_dump() if init_result.capabilities else {},
            "transport": "sse-oauth",
        }

    async def get_tools(self) -> List[MCPTool]:
        """
        Fetch all available tools from the MCP server.

        Returns:
            List of MCPTool objects
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        tools_list = await self._client.list_tools()

        tools = []
        for tool in tools_list:
            input_schema = tool.inputSchema
            if hasattr(input_schema, 'model_dump'):
                input_schema = input_schema.model_dump()
            elif input_schema is None:
                input_schema = {}
            
            mcp_tool = MCPTool(
                name=tool.name,
                description=tool.description,
                input_schema=input_schema,
            )
            tools.append(mcp_tool)

        return tools

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
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        result = await self._client.call_tool(tool_name, arguments=arguments)

        return result.content[0].model_dump() if result.content else {}

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    def get_server_url(self) -> str:
        """Get the server URL."""
        return self.server_url

