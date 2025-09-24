"""CLI tests for Snyk NPX audit command."""

from __future__ import annotations

import json

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

        def __enter__(self):
            self.outer.messages.append(f"status:{self.message}")
            return self

        def __exit__(self, exc_type, exc, tb):
            self.outer.messages.append(f"status_end:{self.message}")

    def status(self, message: str):
        return DummyConsole._Status(self, message)

    def print(self, message) -> None:
        self.messages.append(str(message))

    def print_json(self, *, data) -> None:
        self.messages.append(f"json:{json.dumps(data, sort_keys=True)}")


def test_audit_npx_success_json(monkeypatch) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    class FakeChecker:
        def __init__(self, snyk_cmd: str = "snyk") -> None:
            self.snyk_cmd = snyk_cmd

        def check_npx_command(self, target: str, **kwargs):  # type: ignore[no-redef]
            return {
                "package": "some-package",
                "summary": {"high": 1, "medium": 2},
                "issues": [
                    {"id": "1", "title": "X", "severity": "high"},
                    {"id": "2", "title": "Y", "severity": "medium"},
                ],
                "raw": {},
            }

    monkeypatch.setattr(cli, "SnykPackageChecker", FakeChecker)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: True)

    result = runner.invoke(
        cli.app,
        [
            "audit-npx",
            "--target",
            "npx some-package",
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert any(m.startswith("json:") for m in dummy_console.messages)


def test_audit_npx_rejects_non_npx(monkeypatch) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: False)

    result = runner.invoke(cli.app, ["audit-npx", "--target", "http://localhost:8000/mcp"])

    assert result.exit_code != 0
    assert any("not an NPX command" in m for m in dummy_console.messages)

