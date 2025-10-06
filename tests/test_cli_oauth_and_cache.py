"""Additional CLI coverage: OAuth flow and cache commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mcp_analyzer import cli

runner = CliRunner()


class DummyConsole:
    def __init__(self) -> None:
        self.messages: list[str] = []

    class _Status:
        def __init__(self, outer: "DummyConsole", message: str) -> None:
            self.outer = outer
            self.message = message

        def __enter__(self) -> "DummyConsole._Status":
            self.outer.messages.append(f"status:{self.message}")
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            self.outer.messages.append(f"status_end:{self.message}")

    def status(self, message: str) -> "DummyConsole._Status":
        return DummyConsole._Status(self, message)

    def print(self, message) -> None:
        self.messages.append(str(message))

    def print_json(self, *, data) -> None:
        self.messages.append(f"json:{json.dumps(data, sort_keys=True)}")


class OAuthDummyClient:
    """Minimal FastMCPOAuthClient drop-in used by _run_analysis when --oauth is set."""

    def __init__(self, server_url: str, timeout: int = 30) -> None:
        self.server_url = server_url
        self.timeout = timeout
        self.closed = False

    async def __aenter__(self) -> "OAuthDummyClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    async def get_server_info(self):
        return {"server": "oauth"}

    async def get_tools(self):
        return [
            type("Tool", (), {"name": "t1", "description": "d", "input_schema": {}})()
        ]

    async def close(self) -> None:
        self.closed = True

    def get_server_url(self) -> str:
        return self.server_url


class DummyDescriptionChecker:
    def analyze_tool_descriptions(self, tools):
        return {
            "issues": [],
            "statistics": {"total_tools": len(tools)},
            "recommendations": [],
        }


class DummyTokenChecker:
    def __init__(self, **kwargs) -> None:
        # Provide a cache stub so _perform_checks can print cache stats
        class CacheStub:
            def get_cache_stats(self_inner):
                return {"total_calls": 2, "cache_path": "/tmp/cache"}

        self.cache = CacheStub()
        self.show_tool_outputs = False

    async def analyze_token_efficiency(self, tools, client):
        return {
            "issues": [],
            "tool_metrics": [],
            "statistics": {"total_tools": len(tools), "tools_analyzed": len(tools)},
            "recommendations": [],
        }


class DummySecurityChecker:
    def __init__(self, **kwargs) -> None:
        pass

    async def analyze(self, target: str):
        return {
            "summary": {},
            "statistics": {"total_findings": 0},
            "findings": [],
            "timestamp": "now",
        }


def _patch_common_checkers(monkeypatch) -> None:
    monkeypatch.setattr(cli, "DescriptionChecker", lambda: DummyDescriptionChecker())
    monkeypatch.setattr(
        cli, "TokenEfficiencyChecker", lambda **kwargs: DummyTokenChecker(**kwargs)
    )
    monkeypatch.setattr(
        cli, "SecurityChecker", lambda **kwargs: DummySecurityChecker(**kwargs)
    )


def test_cli_analyze_oauth_http_flow(monkeypatch) -> None:
    """--oauth with HTTP target uses OAuth client branch and runs checks."""
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: False)
    # Ensure the FastMCPOAuthClient import inside _run_analysis resolves to our dummy
    import mcp_analyzer.fastmcp_oauth_client as oauth_mod

    monkeypatch.setattr(oauth_mod, "FastMCPOAuthClient", OAuthDummyClient)
    # Use dummy checkers to avoid hitting network/LLM code paths
    _patch_common_checkers(monkeypatch)

    # Minimal ReportFormatter to avoid printing tables
    monkeypatch.setattr(
        cli,
        "ReportFormatter",
        lambda fmt: type(
            "F", (), {"display_results": lambda self, data, verbose: None}
        )(),
    )

    result = runner.invoke(
        cli.app,
        [
            "analyze",
            "--target",
            "http://localhost:7000/mcp",
            "--oauth",
            "--check",
            "all",
        ],
    )

    assert result.exit_code == 0
    # Connection message should reflect OAuth path
    assert any(
        "Connecting to MCP server with OAuth" in m for m in dummy_console.messages
    )
    assert any("Connected! Found" in m for m in dummy_console.messages)
    # Cache stats line may include styling markup
    assert any(
        "Cached" in m and "successful tool calls" in m for m in dummy_console.messages
    )


def test_cli_analyze_oauth_ignored_for_npx(monkeypatch) -> None:
    """--oauth should be ignored for NPX targets with a warning."""
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: True)
    _patch_common_checkers(monkeypatch)

    # Patch MCPClient used in non-OAuth path to a minimal stub
    class FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        async def get_server_info(self):
            return {}

        async def get_tools(self):
            return []

        def get_server_url(self) -> str:
            return "http://127.0.0.1:9000"

        async def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "MCPClient", FakeClient)
    monkeypatch.setattr(
        cli,
        "ReportFormatter",
        lambda fmt: type(
            "F", (), {"display_results": lambda self, data, verbose: None}
        )(),
    )

    result = runner.invoke(
        cli.app,
        ["analyze", "--target", "npx demo", "--oauth", "--check", "descriptions"],
    )

    assert result.exit_code == 0
    assert any(
        "OAuth is only supported for HTTP/SSE servers" in m
        for m in dummy_console.messages
    )


def _set_fake_home(monkeypatch, home: Path) -> None:
    # Make cli cache commands store under a temporary home directory
    import pathlib as _pl

    monkeypatch.setattr(_pl.Path, "home", lambda: home)


def test_cache_stats_no_cache(monkeypatch, tmp_path: Path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    _set_fake_home(monkeypatch, tmp_path)

    result = runner.invoke(cli.app, ["cache-stats"])  # no cache created yet
    assert result.exit_code == 0
    assert any("No cache found" in m for m in dummy_console.messages)


def test_cache_stats_for_specific_server(monkeypatch, tmp_path: Path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    _set_fake_home(monkeypatch, tmp_path)

    # Build cache using real ToolCallCache so stats are correct
    from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

    server = "http://s.example/mcp"
    cache = ToolCallCache(server)
    cache.cache_successful_call(
        "t1", {"a": 1}, {"ok": True}, 10, 0.1, scenario="minimal"
    )
    cache.cache_successful_call("t2", {}, {}, 5, 0.05, scenario="typical")

    result = runner.invoke(cli.app, ["cache-stats", "--server", server])
    assert result.exit_code == 0
    # Should print a per-server heading and totals (with markup around numbers)
    assert any("Cache Statistics for" in m for m in dummy_console.messages)
    joined = "\n".join(dummy_console.messages)
    assert "Total Tools:" in joined
    assert "Total Cached Calls:" in joined


def test_cache_stats_all_servers(monkeypatch, tmp_path: Path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    _set_fake_home(monkeypatch, tmp_path)

    from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

    s1, s2 = "http://one", "http://two"
    c1 = ToolCallCache(s1)
    c1.cache_successful_call("t", {}, {}, 1, 0.01)
    c2 = ToolCallCache(s2)
    c2.cache_successful_call("t", {}, {}, 1, 0.01)
    c2.cache_successful_call("t", {}, {}, 1, 0.01)

    result = runner.invoke(cli.app, ["cache-stats"])  # all
    assert result.exit_code == 0
    # Expect both servers listed with their call counts
    joined = "\n".join(dummy_console.messages)
    assert s1 in joined and s2 in joined


def test_cache_clear_requires_server_with_tool(monkeypatch, tmp_path: Path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    _set_fake_home(monkeypatch, tmp_path)

    # Ensure cache root exists so validation isn't short-circuited by "No cache found"
    cache_root = tmp_path / ".mcp-analyzer" / "tool-call-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    result = runner.invoke(cli.app, ["cache-clear", "--tool", "t1"])
    assert result.exit_code != 0
    assert any("requires --server" in m for m in dummy_console.messages)


def test_cache_clear_tool_on_server(monkeypatch, tmp_path: Path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    _set_fake_home(monkeypatch, tmp_path)

    from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

    server = "http://svc"
    cache = ToolCallCache(server)
    cache.cache_successful_call("t1", {}, {}, 1, 0.01)
    cache.cache_successful_call("t2", {}, {}, 1, 0.01)

    # Resolve directories before clearing
    root = Path(cache.cache_root)
    assert (root / "t1").exists() and (root / "t2").exists()

    result = runner.invoke(
        cli.app, ["cache-clear", "--server", server, "--tool", "t1", "--yes"]
    )
    assert result.exit_code == 0
    assert not (root / "t1").exists()
    assert (root / "t2").exists()
    assert any("Cleared cache for tool" in m for m in dummy_console.messages)


def test_cache_clear_server_and_all(monkeypatch, tmp_path: Path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    _set_fake_home(monkeypatch, tmp_path)

    from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

    s = "http://svc2"
    c = ToolCallCache(s)
    c.cache_successful_call("t", {}, {}, 1, 0.01)
    server_root = Path(c.cache_root)

    # Clear only this server
    result = runner.invoke(cli.app, ["cache-clear", "--server", s, "--yes"])
    assert result.exit_code == 0
    # Server root recreated and contains metadata file
    assert server_root.exists()
    assert (server_root / "_metadata.json").exists()
    assert any("Cleared cache for server" in m for m in dummy_console.messages)

    # Create two servers and clear ALL
    s2 = "http://svc3"
    c2 = ToolCallCache(s2)
    global_root = server_root.parent  # ~/.mcp-analyzer/tool-call-cache
    assert any(d.is_dir() for d in global_root.iterdir())

    result2 = runner.invoke(cli.app, ["cache-clear", "--yes"])
    assert result2.exit_code == 0
    # Global root recreated and empty
    assert global_root.exists()
    assert list(global_root.iterdir()) == []
