"""Tests for NPX launcher helpers."""

from __future__ import annotations

import pytest

from mcp_analyzer.npx_launcher import (
    NPXServerConfig,
    NPXServerManager,
    NPXServerProcess,
    _get_safe_env_summary,
    is_npx_command,
    parse_npx_command,
)


def test_get_safe_env_summary_masks_sensitive_keys() -> None:
    """Only non-sensitive keys should be shown explicitly."""

    summary = _get_safe_env_summary(
        {
            "API_KEY": "secret",
            "TOKEN": "hidden",
            "VISIBLE": "ok",
            "NAME": "demo",
            "DEBUG": "1",
        }
    )

    assert "VISIBLE" in summary
    assert "API_KEY" not in summary
    assert "TOKEN" not in summary
    assert "secret" not in summary
    assert "sensitive" in summary


def test_npx_process_command_parsing_and_env_merging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commands with exports should merge prepended env vars with provided ones."""

    config = NPXServerConfig(
        command="export API_KEY=abc && npx sample --flag",
        env_vars={"LOCAL_ONLY": "1"},
    )
    process = NPXServerProcess(config)

    assert process._parse_command() == ["npx", "sample", "--flag"]

    env = process._prepare_environment()
    assert env["API_KEY"] == "abc"
    assert env["LOCAL_ONLY"] == "1"

    parsed = process._parse_env_assignments("export FOO=bar OTHER=value")
    assert parsed == {"FOO": "bar", "OTHER": "value"}


def test_npx_process_extracts_urls_from_output() -> None:
    """URL extraction should handle both explicit URLs and numeric ports."""

    config = NPXServerConfig(command="npx demo", env_vars={})
    process = NPXServerProcess(config)

    line = "Server listening on http://localhost:3000/mcp"
    assert process._extract_server_url(line) == "http://localhost:3000/mcp"

    port_line = "App running on port 8123"
    assert process._extract_server_url(port_line) == "http://localhost:8123"


def test_troubleshooting_suggestions_include_hints() -> None:
    """Troubleshooting helper should add actionable suggestions."""

    config = NPXServerConfig(command="npx demo", env_vars={})
    process = NPXServerProcess(config)

    suggestions = process._generate_troubleshooting_suggestions(
        "No output captured", "running"
    )

    assert "download" in suggestions.lower()
    assert "npx demo" in suggestions


def test_parse_npx_command_and_detector() -> None:
    """Parsing helper should split env vars and NPX invocation."""

    clean, env = parse_npx_command("export TOKEN=abc && npx firecrawl-mcp")
    assert clean == "npx firecrawl-mcp"
    assert env == {"TOKEN": "abc"}
    assert is_npx_command(clean)


@pytest.mark.asyncio
async def test_server_manager_tracks_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manager should register launched servers and clean them up."""

    started: list[str] = []
    stopped: list[str] = []

    async def fake_start(self: NPXServerProcess) -> str:  # type: ignore[override]
        started.append(self.config.command)
        self.server_url = "http://localhost:9999"
        return self.server_url

    async def fake_stop(self: NPXServerProcess) -> None:  # type: ignore[override]
        stopped.append(self.config.command)
        self.server_url = None

    monkeypatch.setattr(NPXServerProcess, "start", fake_start, raising=False)
    monkeypatch.setattr(NPXServerProcess, "stop", fake_stop, raising=False)

    manager = NPXServerManager()
    url = await manager.launch_server("npx demo", env_vars={})

    assert url == "http://localhost:9999"
    assert manager.get_active_servers() == ["http://localhost:9999"]
    assert started == ["npx demo"]

    await manager.stop_server(url)
    assert manager.get_active_servers() == []
    assert stopped == ["npx demo"]

    await manager.stop_all_servers()
    assert manager.get_active_servers() == []
