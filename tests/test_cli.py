"""CLI tests for mcp-doctor."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from mcp_analyzer import cli
from mcp_analyzer.checkers.security import VulnerabilityLevel

runner = CliRunner()


class DummyConsole:
    """Console stub recording printed messages."""

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


def test_cli_analyze_success(monkeypatch) -> None:
    """Successful analyze invocation should display formatted results."""

    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: False)

    async def fake_run_analysis(target, check, timeout, verbose, show_tool_outputs, headers, overrides, npx_kwargs):
        fake_run_analysis.called_with = (
            target,
            check,
            timeout,
            verbose,
            show_tool_outputs,
            headers,
            overrides,
            npx_kwargs,
        )
        return {
            "server_url": target,
            "tools_count": 0,
            "checks": {},
        }

    fake_run_analysis.called_with = None
    monkeypatch.setattr(cli, "_run_analysis", fake_run_analysis)

    class DummyFormatter:
        def __init__(self, fmt: str) -> None:
            self.format = fmt
            DummyFormatter.created = self
            self.data = None
            self.verbose = None

        def display_results(self, results, verbose: bool) -> None:
            self.data = results
            self.verbose = verbose

    DummyFormatter.created = None
    monkeypatch.setattr(cli, "ReportFormatter", DummyFormatter)

    result = runner.invoke(
        cli.app, ["analyze", "--target", "http://localhost:8080/mcp"]
    )

    assert result.exit_code == 0
    assert fake_run_analysis.called_with == (
        "http://localhost:8080/mcp",
        cli.CheckType.descriptions,
        30,
        False,
        False,
        None,
        None,
        {},
    )
    assert DummyFormatter.created is not None
    assert DummyFormatter.created.data["server_url"] == "http://localhost:8080/mcp"
    assert "Server URL" in "\n".join(dummy_console.messages)


def test_cli_analyze_invalid_env_vars(monkeypatch) -> None:
    """Invalid env-vars payload should trigger exit with error."""

    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    result = runner.invoke(
        cli.app,
        [
            "analyze",
            "--target",
            "http://localhost:8080/mcp",
            "--env-vars",
            "{not-json}",
        ],
    )

    assert result.exit_code != 0
    assert any(
        "Invalid JSON in env-vars" in message for message in dummy_console.messages
    )


def test_cli_analyze_handles_npx(monkeypatch) -> None:
    """NPX targets should pass env/working-dir settings to the runner."""

    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: True)

    async def fake_run_analysis(target, check, timeout, verbose, show_tool_outputs, headers, overrides, npx_kwargs):
        fake_run_analysis.received = (
            target,
            check,
            timeout,
            verbose,
            show_tool_outputs,
            headers,
            overrides,
            npx_kwargs,
        )
        return {
            "server_url": "http://localhost:9999",
            "tools_count": 1,
            "checks": {},
        }

    fake_run_analysis.received = None
    monkeypatch.setattr(cli, "_run_analysis", fake_run_analysis)
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
            "npx demo",
            "--env-vars",
            '{"TOKEN": "xyz"}',
            "--working-dir",
            ".",
            "--no-env-logging",
        ],
    )

    assert result.exit_code == 0
    assert any("NPX Command" in message for message in dummy_console.messages)
    assert fake_run_analysis.received is not None
    assert fake_run_analysis.received[7] == {
        "env_vars": {"TOKEN": "xyz"},
        "working_dir": ".",
        "log_env_vars": False,
    }


def test_cli_analyze_env_file(monkeypatch, tmp_path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setattr(cli, "is_npx_command", lambda value: True)

    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=file\n", encoding="utf-8")

    async def fake_run_analysis(target, check, timeout, verbose, show_tool_outputs, headers, overrides, npx_kwargs):
        fake_run_analysis.received = npx_kwargs
        return {"server_url": "http://localhost", "tools_count": 0, "checks": {}}

    fake_run_analysis.received = None
    monkeypatch.setattr(cli, "_run_analysis", fake_run_analysis)
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
            "npx demo",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code == 0
    assert fake_run_analysis.received == {"env_vars": {"TOKEN": "file"}}


def test_cli_generate_dataset_from_file(monkeypatch, tmp_path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            StubGenerator.created = (model, llm_timeout)

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            StubGenerator.received = (tools, num_tasks)
            return [{"prompt": "demo"}]

    StubGenerator.created = None
    StubGenerator.received = None
    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--llm-timeout",
            "15",
        ],
    )

    assert result.exit_code == 0
    assert StubGenerator.created == (None, 15.0)
    assert StubGenerator.received[1] == 5
    assert any(message.startswith("json:") for message in dummy_console.messages)


def test_cli_generate_dataset_from_target(monkeypatch, tmp_path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    async def fake_fetch(target, timeout, npx_kwargs):
        fake_fetch.called = (target, timeout, npx_kwargs)
        return ["tool-a"]

    fake_fetch.called = None
    monkeypatch.setattr(cli, "fetch_tools_for_dataset", fake_fetch)

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            StubGenerator.created = (model, llm_timeout)

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            StubGenerator.received = (tools, num_tasks)
            return [{"prompt": "demo"}]

    StubGenerator.created = None
    StubGenerator.received = None
    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)

    output_path = tmp_path / "dataset.json"
    env_file = tmp_path / "env"
    env_file.write_text("FROM_FILE=1\n", encoding="utf-8")

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--target",
            "npx demo",
            "--env-vars",
            '{"TOKEN": "xyz"}',
            "--env-file",
            str(env_file),
            "--working-dir",
            str(tmp_path),
            "--no-env-logging",
            "--output",
            str(output_path),
            "--model",
            "gpt",
            "--llm-timeout",
            "20",
            "--num-tasks",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert fake_fetch.called[0] == "npx demo"
    assert fake_fetch.called[2] == {
        "env_vars": {"FROM_FILE": "1", "TOKEN": "xyz"},
        "working_dir": str(tmp_path),
        "log_env_vars": False,
    }
    assert StubGenerator.created == ("gpt", 20.0)
    assert StubGenerator.received[1] == 3
    assert json.loads(output_path.read_text()) == [{"prompt": "demo"}]
    assert any("Dataset saved" in message for message in dummy_console.messages)


def test_cli_generate_dataset_option_validation(monkeypatch) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--target",
            "http://localhost",
            "--tools-file",
            "tools.json",
        ],
    )

    assert result.exit_code != 0
    assert any("Provide exactly one" in message for message in dummy_console.messages)


def test_cli_generate_dataset_invalid_env(monkeypatch) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--target",
            "http://localhost",
            "--env-vars",
            "{bad}",
        ],
    )

    assert result.exit_code != 0
    assert any("Invalid JSON" in message for message in dummy_console.messages)


def test_cli_generate_dataset_langsmith_requires_api_key(monkeypatch, tmp_path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            return [
                {
                    "prompt": "demo",
                    "tools_called": ["demo"],
                    "tools_args": [["a"]],
                    "retrieved_contexts": ["Demo context"],
                    "response": "Demo response",
                    "reference": "Demo reference",
                }
            ]

        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            pass

    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)

    def _unexpected_upload(*args, **kwargs):
        raise RuntimeError("should not upload")

    monkeypatch.setattr(cli, "upload_dataset_to_langsmith", _unexpected_upload)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--push-to-langsmith",
        ],
    )

    assert result.exit_code != 0
    assert any(
        "Provide a LangSmith API key" in message for message in dummy_console.messages
    )


def test_cli_generate_dataset_langsmith_upload(monkeypatch, tmp_path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            pass

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            return [
                {
                    "prompt": "demo",
                    "tools_called": ["demo"],
                    "tools_args": [["a"]],
                    "retrieved_contexts": ["Demo context"],
                    "response": "Demo response",
                    "reference": "Demo reference",
                }
            ]

    def fake_upload(dataset, dataset_name, **kwargs):
        fake_upload.called_with = (dataset, dataset_name, kwargs)
        return "dataset-123", False

    fake_upload.called_with = None

    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)
    monkeypatch.setattr(cli, "upload_dataset_to_langsmith", fake_upload)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--push-to-langsmith",
            "--langsmith-api-key",
            "ls-test",
            "--langsmith-dataset-name",
            "demo-dataset",
            "--langsmith-project",
            "demo-project",
            "--langsmith-description",
            "demo description",
            "--langsmith-endpoint",
            "https://example.com",
        ],
    )

    assert result.exit_code == 0
    assert fake_upload.called_with is not None
    dataset, dataset_name, kwargs = fake_upload.called_with
    assert dataset_name == "demo-dataset"
    assert kwargs["api_key"] == "ls-test"
    assert kwargs["endpoint"] == "https://example.com"
    assert kwargs["project_name"] == "demo-project"
    assert kwargs["description"] == "demo description"
    assert any(
        "Dataset uploaded to LangSmith" in message for message in dummy_console.messages
    )
    assert any("Dataset ID" in message for message in dummy_console.messages)


def test_cli_generate_dataset_langsmith_reuse(monkeypatch, tmp_path) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            pass

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            return [
                {
                    "prompt": "demo",
                    "tools_called": ["demo"],
                    "tools_args": [["a"]],
                    "retrieved_contexts": ["Demo context"],
                    "response": "Demo response",
                    "reference": "Demo reference",
                }
            ]

    def fake_upload(dataset, dataset_name, **kwargs):
        return "dataset-123", True

    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)
    monkeypatch.setattr(cli, "upload_dataset_to_langsmith", fake_upload)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--push-to-langsmith",
            "--langsmith-api-key",
            "ls-test",
        ],
    )

    assert result.exit_code == 0
    assert any("Reused existing" in message for message in dummy_console.messages)
    assert not any(
        "Dataset uploaded to LangSmith" in message for message in dummy_console.messages
    )


def test_cli_evaluate_dataset_disabled(monkeypatch) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    result = runner.invoke(cli.app, ["evaluate-dataset"])

    assert result.exit_code != 0
    assert any(
        "Evaluation functionality has been temporarily disabled" in msg
        for msg in dummy_console.messages
    )


def test_cli_generate_dataset_langsmith_upload_error(monkeypatch, tmp_path) -> None:
    """Test that LangSmith upload errors are handled gracefully."""
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            pass

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            return [
                {
                    "prompt": "demo",
                    "tools_called": ["demo"],
                    "tools_args": [["a"]],
                    "retrieved_contexts": ["Demo context"],
                    "response": "Demo response",
                    "reference": "Demo reference",
                }
            ]

    def fake_upload_error(dataset, dataset_name, **kwargs):
        from mcp_analyzer.langsmith_uploader import LangSmithUploadError

        raise LangSmithUploadError("Upload failed")

    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)
    monkeypatch.setattr(cli, "upload_dataset_to_langsmith", fake_upload_error)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--push-to-langsmith",
            "--langsmith-api-key",
            "ls-test",
        ],
    )

    assert result.exit_code != 0
    assert any(
        "LangSmith upload failed" in message for message in dummy_console.messages
    )


def test_cli_generate_dataset_langsmith_upload_without_project(
    monkeypatch, tmp_path
) -> None:
    """Test LangSmith upload without project name (covers the if langsmith_project branch)."""
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            pass

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            return [
                {
                    "prompt": "demo",
                    "tools_called": ["demo"],
                    "tools_args": [["a"]],
                    "retrieved_contexts": ["Demo context"],
                    "response": "Demo response",
                    "reference": "Demo reference",
                }
            ]

    def fake_upload(dataset, dataset_name, **kwargs):
        return "dataset-123", False

    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)
    monkeypatch.setattr(cli, "upload_dataset_to_langsmith", fake_upload)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--push-to-langsmith",
            "--langsmith-api-key",
            "ls-test",
        ],
    )

    assert result.exit_code == 0
    # Should NOT have the "Tagged project" message since no project was specified
    assert not any("Tagged project" in message for message in dummy_console.messages)
    assert any(
        "Dataset uploaded to LangSmith" in message for message in dummy_console.messages
    )


def test_cli_generate_dataset_from_env_api_key(monkeypatch, tmp_path) -> None:
    """Test LangSmith upload using environment variable for API key."""
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    monkeypatch.setenv("LANGSMITH_API_KEY", "env-key")

    tools_file = tmp_path / "tools.json"
    tools_file.write_text('["demo-tool"]', encoding="utf-8")

    class StubGenerator:
        def __init__(self, *, model=None, llm_timeout=60.0) -> None:
            pass

        async def generate_dataset(self, tools, *, num_tasks: int) -> list[dict]:
            return [
                {
                    "prompt": "demo",
                    "tools_called": ["demo"],
                    "tools_args": [["a"]],
                }
            ]

    def fake_upload(dataset, dataset_name, **kwargs):
        fake_upload.called_with = (dataset, dataset_name, kwargs)
        return "dataset-123", False

    fake_upload.called_with = None

    monkeypatch.setattr(cli, "DatasetGenerator", StubGenerator)
    monkeypatch.setattr(cli, "upload_dataset_to_langsmith", fake_upload)

    result = runner.invoke(
        cli.app,
        [
            "generate-dataset",
            "--tools-file",
            str(tools_file),
            "--push-to-langsmith",
        ],
    )

    assert result.exit_code == 0
    assert fake_upload.called_with is not None
    dataset, dataset_name, kwargs = fake_upload.called_with
    assert kwargs["api_key"] == "env-key"


def test_cli_version_command(monkeypatch) -> None:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    result = runner.invoke(cli.app, ["version"])

    assert result.exit_code == 0
    assert any("MCP Doctor" in message for message in dummy_console.messages)


class FakeClient:
    """Fake MCP client for _run_analysis tests."""

    last_instance: "FakeClient | None" = None

    def __init__(self, target: str, timeout: int, **kwargs) -> None:
        self.target = target
        self.timeout = timeout
        self.kwargs = kwargs
        self.closed = False
        FakeClient.last_instance = self

    async def get_server_info(self):
        return {"server_name": "Fake"}

    async def get_tools(self):
        return ["tool-a", "tool-b"]

    def get_server_url(self) -> str:
        return "http://localhost:9999"

    async def close(self) -> None:
        self.closed = True


class DummyDescriptionChecker:
    """Collects invocation details for description analysis."""

    def __init__(self) -> None:
        self.tools = None

    def analyze_tool_descriptions(self, tools):
        self.tools = tools
        return {
            "issues": [],
            "statistics": {
                "total_tools": len(tools),
                "tools_passed": len(tools),
                "errors": 0,
                "warnings": 0,
                "info": 0,
            },
            "recommendations": [],
        }


class DummyTokenChecker:
    """Collects invocation details for token analysis."""

    def __init__(self) -> None:
        self.tools = None

    async def analyze_token_efficiency(self, tools, client):
        self.tools = tools
        DummyTokenChecker.last_client = client
        return {
            "issues": [],
            "tool_metrics": [],
            "statistics": {
                "total_tools": len(tools),
                "tools_analyzed": len(tools),
                "errors": 0,
                "warnings": 0,
                "info": 0,
                "avg_tokens_per_response": 0,
                "max_tokens_observed": 0,
                "tools_exceeding_limit": 0,
            },
            "recommendations": [],
        }


DummyTokenChecker.last_client = None


class DummySecurityChecker:
    """Collects invocation details for the security audit."""

    created_with_timeout: list[int] = []
    calls: list[str] = []

    def __init__(self, timeout: int = 0, verify: bool = True, **kwargs) -> None:
        self.timeout = timeout
        self.verify = verify
        DummySecurityChecker.created_with_timeout.append(timeout)

    async def analyze(self, target: str):
        DummySecurityChecker.calls.append(target)
        return {
            "summary": {level.value: 0 for level in VulnerabilityLevel},
            "statistics": {"total_findings": 0},
            "findings": [],
            "timestamp": "now",
        }


def build_dummy_console(monkeypatch) -> DummyConsole:
    dummy_console = DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)
    return dummy_console


def patch_analysis_dependencies(monkeypatch, *, is_npx: bool) -> None:
    DummySecurityChecker.created_with_timeout = []
    DummySecurityChecker.calls = []
    monkeypatch.setattr(cli, "MCPClient", FakeClient)
    monkeypatch.setattr(cli, "is_npx_command", lambda target: is_npx)
    monkeypatch.setattr(cli, "DescriptionChecker", lambda: DummyDescriptionChecker())
    monkeypatch.setattr(cli, "TokenEfficiencyChecker", lambda: DummyTokenChecker())
    monkeypatch.setattr(
        cli, "SecurityChecker", lambda **kwargs: DummySecurityChecker(**kwargs)
    )


@pytest.mark.asyncio
async def test_run_analysis_for_npx_target(monkeypatch) -> None:
    dummy_console = build_dummy_console(monkeypatch)
    patch_analysis_dependencies(monkeypatch, is_npx=True)

    result = await cli._run_analysis(
        target="npx fake",
        check=cli.CheckType.all,
        timeout=10,
        verbose=True,
        npx_kwargs={"env_vars": {"TOKEN": "abc"}},
    )

    assert result["is_npx_server"] is True
    assert result["checks"].keys() == {
        "descriptions",
        "token_efficiency",
        "security",
    }
    assert any("NPX server launched" in message for message in dummy_console.messages)
    assert DummyTokenChecker.last_client is not None
    assert FakeClient.last_instance is not None
    assert FakeClient.last_instance.closed is True
    assert DummySecurityChecker.created_with_timeout == [10]
    assert DummySecurityChecker.calls == ["http://localhost:9999"]


@pytest.mark.asyncio
async def test_run_analysis_for_http_target(monkeypatch) -> None:
    dummy_console = build_dummy_console(monkeypatch)
    patch_analysis_dependencies(monkeypatch, is_npx=False)

    result = await cli._run_analysis(
        target="http://localhost:1234/mcp",
        check=cli.CheckType.descriptions,
        timeout=5,
        verbose=False,
        npx_kwargs={},
    )

    assert result["is_npx_server"] is False
    assert "token_efficiency" not in result["checks"]
    assert "security" not in result["checks"]
    assert any("Connected!" in message for message in dummy_console.messages)
    assert FakeClient.last_instance is not None
    assert FakeClient.last_instance.closed is True
    assert DummySecurityChecker.calls == []


@pytest.mark.asyncio
async def test_run_analysis_with_none_npx_kwargs(monkeypatch) -> None:
    """Test _run_analysis when npx_kwargs is None (covers line 151)."""
    dummy_console = build_dummy_console(monkeypatch)
    patch_analysis_dependencies(monkeypatch, is_npx=False)

    result = await cli._run_analysis(
        target="http://localhost:1234/mcp",
        check=cli.CheckType.descriptions,
        timeout=5,
        verbose=False,
        npx_kwargs=None,  # This should trigger the line 151: npx_kwargs = {}
    )

    assert result["is_npx_server"] is False
    assert FakeClient.last_instance is not None
    assert FakeClient.last_instance.kwargs == {}  # Should be empty dict, not None


def test_load_env_file_not_found(tmp_path) -> None:
    """Test _load_env_file raises FileNotFoundError for non-existent file."""
    non_existent_file = tmp_path / "does_not_exist.env"

    with pytest.raises(FileNotFoundError):
        cli._load_env_file(non_existent_file)


def test_load_env_file_empty_lines_and_comments(tmp_path) -> None:
    """Test _load_env_file handles empty lines and comments correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# This is a comment\n"
        "\n"
        "KEY1=value1\n"
        "   \n"  # whitespace-only line
        "# Another comment\n"
        "KEY2=value2\n",
        encoding="utf-8",
    )

    result = cli._load_env_file(env_file)
    assert result == {"KEY1": "value1", "KEY2": "value2"}


def test_load_env_file_export_prefix(tmp_path) -> None:
    """Test _load_env_file handles export prefix correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "export KEY1=value1\n" "KEY2=value2\n" "export KEY3=value3\n", encoding="utf-8"
    )

    result = cli._load_env_file(env_file)
    assert result == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"}


def test_load_env_file_invalid_line_no_equals(tmp_path) -> None:
    """Test _load_env_file raises ValueError for lines without equals sign."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KEY1=value1\n" "INVALID_LINE_WITHOUT_EQUALS\n" "KEY2=value2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid env entry on line 2"):
        cli._load_env_file(env_file)


def test_load_env_file_quoted_values(tmp_path) -> None:
    """Test _load_env_file handles quoted values correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        'KEY1="quoted value"\n'
        "KEY2='single quoted'\n"
        'KEY3="value with spaces and symbols!@#"\n'
        "KEY4=unquoted\n"
        'KEY5=""\n'  # empty quoted value
        "KEY6=''\n",  # empty single quoted value
        encoding="utf-8",
    )

    result = cli._load_env_file(env_file)
    assert result == {
        "KEY1": "quoted value",
        "KEY2": "single quoted",
        "KEY3": "value with spaces and symbols!@#",
        "KEY4": "unquoted",
        "KEY5": "",
        "KEY6": "",
    }


def test_load_env_file_mixed_quotes_not_stripped(tmp_path) -> None:
    """Test _load_env_file doesn't strip quotes when they don't match."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KEY1=\"mismatched'\n" "KEY2='also mismatched\"\n" 'KEY3="properly matched"\n',
        encoding="utf-8",
    )

    result = cli._load_env_file(env_file)
    assert result == {
        "KEY1": "\"mismatched'",
        "KEY2": "'also mismatched\"",
        "KEY3": "properly matched",
    }


def test_load_and_apply_env_file_file_not_found(tmp_path) -> None:
    """Test _load_and_apply_env_file handles FileNotFoundError."""
    import typer

    dummy_console = DummyConsole()
    non_existent_file = tmp_path / "does_not_exist.env"

    with pytest.raises(typer.Exit):
        cli._load_and_apply_env_file(non_existent_file, dummy_console)

    assert any("Env file not found" in msg for msg in dummy_console.messages)


def test_load_and_apply_env_file_value_error(tmp_path) -> None:
    """Test _load_and_apply_env_file handles ValueError from invalid env file."""
    import typer

    dummy_console = DummyConsole()
    env_file = tmp_path / ".env"
    env_file.write_text("INVALID_LINE_WITHOUT_EQUALS\n", encoding="utf-8")

    with pytest.raises(typer.Exit):
        cli._load_and_apply_env_file(env_file, dummy_console)

    assert any("Invalid env entry" in msg for msg in dummy_console.messages)


def test_load_and_apply_env_file_success(tmp_path, monkeypatch) -> None:
    """Test _load_and_apply_env_file successfully loads and applies env vars."""
    dummy_console = DummyConsole()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TEST_VAR=test_value\nANOTHER_VAR=another_value\n", encoding="utf-8"
    )

    # Clear any existing env vars
    monkeypatch.delenv("TEST_VAR", raising=False)
    monkeypatch.delenv("ANOTHER_VAR", raising=False)

    result = cli._load_and_apply_env_file(env_file, dummy_console)

    assert result == {"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"}
    # Verify they were actually set in the environment
    import os

    assert os.environ.get("TEST_VAR") == "test_value"
    assert os.environ.get("ANOTHER_VAR") == "another_value"


def test_load_and_apply_env_file_none(tmp_path) -> None:
    """Test _load_and_apply_env_file returns empty dict when env_file is None."""
    dummy_console = DummyConsole()

    result = cli._load_and_apply_env_file(None, dummy_console)

    assert result == {}
    assert len(dummy_console.messages) == 0
