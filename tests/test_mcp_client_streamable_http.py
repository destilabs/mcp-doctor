from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest

from mcp_analyzer.mcp_client import MCPClient


class DummyResponse:
    status_code = 405
    headers: Dict[str, str] = {}
    text = "Method Not Allowed"

    async def aread(self) -> bytes:
        return self.text.encode()

    def json(self) -> Dict[str, Any]:
        raise ValueError("No JSON body")


class DummySession:
    def __init__(self) -> None:
        self.closed = False
        self.requested_urls: list[str] = []

    async def get(self, url: str) -> DummyResponse:
        self.requested_urls.append(url)
        return DummyResponse()

    async def aclose(self) -> None:
        self.closed = True


class DummyCapabilities:
    def model_dump(self) -> Dict[str, Any]:
        return {"tools": {"supported": True}}


class DummyCallResult:
    isError = False
    content: list[Any] = []
    structuredContent: Any = None

    def __init__(self, name: str, arguments: Dict[str, Any]) -> None:
        self._payload = {"name": name, "arguments": arguments}

    def model_dump(
        self, mode: str | None = None, exclude_none: bool | None = None
    ) -> Dict[str, Any]:
        return self._payload


class DummyFastMCPClient:
    latest: "DummyFastMCPClient | None" = None

    def __init__(self, transport: Any, timeout: int | None = None) -> None:
        self.transport = transport
        self.timeout = timeout
        self.initialize_result = SimpleNamespace(
            protocolVersion="2025-06-18",
            serverInfo=SimpleNamespace(name="Streamable Server", version="1.2.3"),
            capabilities=DummyCapabilities(),
        )
        self.closed = False
        DummyFastMCPClient.latest = self

    async def __aenter__(self) -> "DummyFastMCPClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    async def list_tools(self):
        return [
            SimpleNamespace(
                name="demo_tool",
                description="Demo description",
                inputSchema={"type": "object"},
            )
        ]

    async def call_tool_mcp(self, name: str, arguments: Dict[str, Any], **_: Any):
        return DummyCallResult(name, arguments)


class DummyStreamableHttpTransport:
    def __init__(self, url: str, headers: Dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_mcp_client_falls_back_to_streamable_http(monkeypatch) -> None:
    dummy_session = DummySession()

    async def fake_get_session(self: MCPClient) -> DummySession:
        if not getattr(self, "_session", None):
            self._session = dummy_session
        return dummy_session

    async def fake_probe(self: MCPClient, url: str) -> str:
        return "http"

    monkeypatch.setattr(MCPClient, "_get_session", fake_get_session)
    monkeypatch.setattr(MCPClient, "_probe_http_endpoint", fake_probe)
    monkeypatch.setattr(
        "mcp_analyzer.mcp_client.StreamableHttpTransport",
        DummyStreamableHttpTransport,
    )
    monkeypatch.setattr(
        "mcp_analyzer.mcp_client.FastMCPClient", DummyFastMCPClient
    )

    client = MCPClient("https://example.com/mcp", timeout=2, headers={"X": "Y"})

    info = await client.get_server_info()
    assert info.server_name == "Streamable Server"
    assert client._transport == "streamable_http"
    assert client._streamable_client is not None

    tools = await client.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "demo_tool"

    result = await client.call_tool("demo_tool", {"foo": "bar"})
    assert result["arguments"] == {"foo": "bar"}

    await client.close()

    assert DummyFastMCPClient.latest is not None
    assert DummyFastMCPClient.latest.closed is True
    assert dummy_session.closed is True
