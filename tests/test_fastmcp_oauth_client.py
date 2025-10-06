"""Tests for FastMCPOAuthClient wrapper without real network/auth."""

from __future__ import annotations

import types
from typing import Any

import pytest

import mcp_analyzer.fastmcp_oauth_client as oauth_mod


class _DummyInitResult:
    def __init__(self) -> None:
        self.protocolVersion = "2024-10-01"

        class _ServerInfo:
            name = "Dummy Server"
            version = "1.0"

        self.serverInfo = _ServerInfo()

        class _Caps:
            def model_dump(self) -> dict:
                return {"dummy": True}

        self.capabilities = _Caps()


class _DummyTool:
    def __init__(
        self, name: str, description: str, input_schema: dict | None = None
    ) -> None:
        self.name = name
        self.description = description
        self.inputSchema = types.SimpleNamespace(model_dump=lambda: input_schema or {})


class _DummyFastMCPClient:
    def __init__(self, server_url: str, auth: str | None = None) -> None:
        self.server_url = server_url
        self.auth = auth
        self.initialize_result = _DummyInitResult()
        self._entered = False

    async def __aenter__(self) -> "_DummyFastMCPClient":
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._entered = False

    async def list_tools(self) -> list[_DummyTool]:
        return [_DummyTool("t1", "desc", {"type": "object", "properties": {}})]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        class _Content:
            def model_dump(self_inner) -> dict:
                return {"tool": tool_name, "args": arguments}

        class _Result:
            content = [_Content()]

        return _Result()


@pytest.mark.asyncio
async def test_fastmcp_oauth_client_happy_path(monkeypatch) -> None:
    # Patch the underlying FastMCP client class used by our wrapper
    monkeypatch.setattr(oauth_mod, "FastMCPClient", _DummyFastMCPClient)

    async with oauth_mod.FastMCPOAuthClient("http://server") as client:
        # server URL preserved
        assert client.get_server_url() == "http://server"

        # server info marshalled from dummy init result
        info = await client.get_server_info()
        assert info["protocol_version"] == "2024-10-01"
        assert info["server_name"] == "Dummy Server"
        assert info["transport"] == "sse-oauth"

        # tools converted to MCPTool instances
        tools = await client.get_tools()
        assert tools and tools[0].name == "t1"

        # tool call returns converted content
        result = await client.call_tool("t1", {"a": 1})
        assert result == {"tool": "t1", "args": {"a": 1}}
