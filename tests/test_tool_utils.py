"""Tests for tool utility helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcp_analyzer.mcp_client import MCPTool
from mcp_analyzer.tool_utils import DatasetGenerationError, fetch_tools_for_dataset, load_tools_from_file


class DummyConsole:
    """Minimal console stub capturing messages."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    class _Status:
        def __init__(self, outer: "DummyConsole", message: str) -> None:
            self.outer = outer
            self.message = message

        def __enter__(self) -> "DummyConsole._Status":
            self.outer.messages.append(f"enter:{self.message}")
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            self.outer.messages.append(f"exit:{self.message}")

    def status(self, message: str) -> "DummyConsole._Status":
        return DummyConsole._Status(self, message)

    def print(self, message: Any) -> None:
        self.messages.append(str(message))


class FakeClient:
    """Fake MCP client capturing interactions."""

    last_instance: "FakeClient | None" = None

    def __init__(self, target: str, timeout: int, **kwargs: Any) -> None:
        self.target = target
        self.timeout = timeout
        self.kwargs = kwargs
        self.closed = False
        FakeClient.last_instance = self

    async def get_server_info(self) -> Any:
        return type("Info", (), {"server_name": "Fake Server"})()

    async def get_tools(self) -> list[MCPTool]:
        return [
            MCPTool(name="alpha", description="first"),
            MCPTool(name="beta", description="second"),
        ]

    def get_server_url(self) -> str:
        return "http://localhost:4545"

    async def close(self) -> None:
        self.closed = True


def test_load_tools_from_file_supports_strings_and_dicts(tmp_path: Path) -> None:
    """Loader should accept string and object definitions."""

    payload = [
        "simple-tool",
        {"name": "structured", "description": "detailed"},
    ]
    tools_file = tmp_path / "tools.json"
    tools_file.write_text(json.dumps(payload), encoding="utf-8")

    tools = load_tools_from_file(tools_file)

    assert [tool.name for tool in tools] == ["simple-tool", "structured"]


def test_load_tools_from_file_rejects_invalid_payload(tmp_path: Path) -> None:
    """Invalid JSON payloads should raise the dataset error."""

    tools_file = tmp_path / "bad.json"
    tools_file.write_text("{}", encoding="utf-8")

    with pytest.raises(DatasetGenerationError):
        load_tools_from_file(tools_file)

    with pytest.raises(DatasetGenerationError):
        load_tools_from_file(tmp_path / "missing.json")


@pytest.mark.asyncio
@pytest.mark.parametrize("is_npx", [True, False])
async def test_fetch_tools_for_dataset_uses_client(monkeypatch: pytest.MonkeyPatch, is_npx: bool) -> None:
    """Fetcher should proxy through the MCP client and provide feedback."""

    from mcp_analyzer import tool_utils as module

    dummy_console = DummyConsole()
    monkeypatch.setattr(module, "console", dummy_console)
    monkeypatch.setattr(module, "MCPClient", FakeClient)
    monkeypatch.setattr(module, "is_npx_command", lambda target: is_npx)

    tools = await fetch_tools_for_dataset(
        target="npx something" if is_npx else "http://localhost:9999/mcp",
        timeout=15,
        npx_kwargs={"env_vars": {"TOKEN": "abc"}},
    )

    assert len(tools) == 2

    if is_npx:
        assert any("NPX server launched" in message for message in dummy_console.messages)
    else:
        assert any("Connected to MCP server" in message for message in dummy_console.messages)

    assert any(message.startswith("enter:") for message in dummy_console.messages)

    assert FakeClient.last_instance is not None
    assert FakeClient.last_instance.timeout == 15
    assert FakeClient.last_instance.closed is True
    assert FakeClient.last_instance.kwargs.get("env_vars") == {"TOKEN": "abc"}

