"""Tests for synthetic dataset generation."""

import json
from pathlib import Path

import pytest

import mcp_analyzer.dataset_generator as dataset_module
from mcp_analyzer.dataset_generator import (
    DatasetGenerationError,
    DatasetGenerator,
    ModelProvider,
    OpenAIClient,
    resolve_provider,
)
from mcp_analyzer.mcp_client import MCPTool
from mcp_analyzer.tool_utils import load_tools_from_file


class DummyClient:
    """Fake LLM client for tests."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    async def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


@pytest.fixture
def sample_tools() -> list[MCPTool]:
    """Return a small set of tools for testing."""

    return [
        MCPTool(name="calculate", description="Add two numbers"),
        MCPTool(name="print", description="Print value"),
    ]


@pytest.mark.asyncio
async def test_dataset_generator_success(sample_tools: list[MCPTool]) -> None:
    """Dataset generator should parse valid JSON output."""

    response = json.dumps(
        [
            {
                "prompt": "Add 2 and 2 then print the result",
                "tools_called": ["calculate", "print"],
                "tools_args": [["2", "2"], ["4"]],
            }
        ],
        indent=2,
    )
    client = DummyClient(f"```json\n{response}\n```")
    generator = DatasetGenerator(llm_client=client)

    dataset = await generator.generate_dataset(sample_tools, num_tasks=1)

    assert dataset[0]["tools_called"] == ["calculate", "print"]
    assert dataset[0]["tools_args"][0] == ["2", "2"]
    assert "calculate" in client.last_prompt


@pytest.mark.asyncio
async def test_dataset_generator_detects_invalid_tools(
    sample_tools: list[MCPTool],
) -> None:
    """Generator should raise when dataset references unknown tools."""

    response = json.dumps(
        [
            {
                "prompt": "Call unsupported tool",
                "tools_called": ["missing"],
                "tools_args": [["1"]],
            }
        ]
    )
    generator = DatasetGenerator(llm_client=DummyClient(response))

    with pytest.raises(DatasetGenerationError):
        await generator.generate_dataset(sample_tools, num_tasks=1)


@pytest.mark.asyncio
async def test_dataset_generator_max_tasks_guard(sample_tools: list[MCPTool]) -> None:
    """Generator should guard against excessive task counts."""

    generator = DatasetGenerator(llm_client=DummyClient("[]"), max_tasks=2)
    with pytest.raises(DatasetGenerationError):
        await generator.generate_dataset(sample_tools, num_tasks=3)


@pytest.mark.asyncio
async def test_dataset_generator_mismatched_args(sample_tools: list[MCPTool]) -> None:
    """Generator should detect tools_args mismatch."""

    response = json.dumps(
        [
            {
                "prompt": "Add numbers",
                "tools_called": ["calculate"],
                "tools_args": [],
            }
        ]
    )
    generator = DatasetGenerator(llm_client=DummyClient(response))

    with pytest.raises(DatasetGenerationError):
        await generator.generate_dataset(sample_tools, num_tasks=1)


def test_resolve_provider_prefers_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anthropic key should take precedence when both are present."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = resolve_provider()

    assert config.provider == ModelProvider.ANTHROPIC
    assert config.model == "claude-4-sonnet"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_resolve_provider_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI provider should be selected when only that key is present."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = resolve_provider(model="gpt-custom")

    assert config.provider == ModelProvider.OPENAI
    assert config.model == "gpt-custom"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_resolve_provider_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing keys should raise an explicit error."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(DatasetGenerationError):
        resolve_provider()


def test_openai_extract_text_from_output_entries() -> None:
    """OpenAI parser should handle output_text content entries."""

    dataset_json = json.dumps(
        [
            {
                "prompt": "Add numbers",
                "tools_called": ["calculate"],
                "tools_args": [["1", "2"]],
            }
        ]
    )
    payload = {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": dataset_json,
                    }
                ]
            }
        ]
    }

    extracted = OpenAIClient._extract_text(payload)

    assert json.loads(extracted)[0]["tools_called"] == ["calculate"]


def test_openai_extract_text_from_output_text_list() -> None:
    """OpenAI parser should support output_text helper field."""

    dataset_json = json.dumps(
        [
            {
                "prompt": "Print sum",
                "tools_called": ["print"],
                "tools_args": [["42"]],
            }
        ]
    )
    payload = {"output_text": [dataset_json]}

    extracted = OpenAIClient._extract_text(payload)

    assert json.loads(extracted)[0]["tools_args"][0] == ["42"]


@pytest.mark.asyncio
async def test_dataset_generator_allows_custom_timeout(
    monkeypatch: pytest.MonkeyPatch, sample_tools: list[MCPTool]
) -> None:
    """Custom timeout should be forwarded to the provider client."""

    class FakeProvider:
        provider = ModelProvider.OPENAI
        api_key = "key"
        model = "gpt"

    monkeypatch.setattr(
        dataset_module, "resolve_provider", lambda model=None: FakeProvider
    )

    captured: dict[str, float] = {}

    class FakeLLM:
        async def complete(self, prompt: str) -> str:
            return json.dumps(
                [
                    {
                        "prompt": "test",
                        "tools_called": [sample_tools[0].name],
                        "tools_args": [["1", "2"]],
                    }
                ]
            )

    def fake_openai_client(
        api_key: str, model: str, *, timeout: float, max_tokens: int = 2048
    ) -> FakeLLM:
        captured["timeout"] = timeout
        captured["max_tokens"] = max_tokens
        return FakeLLM()

    monkeypatch.setattr(dataset_module, "OpenAIClient", fake_openai_client)

    generator = DatasetGenerator(llm_timeout=123.0)
    await generator.generate_dataset(sample_tools[:1], num_tasks=1)

    assert captured["timeout"] == 123.0
    assert captured["max_tokens"] == 2048


def test_load_tools_from_file(tmp_path: Path) -> None:
    """Tools loader should parse strings and objects."""

    tools_path = tmp_path / "tools.json"
    tools_path.write_text(
        json.dumps(["calculate", {"name": "print", "description": "Print value"}]),
        encoding="utf-8",
    )

    tools = load_tools_from_file(tools_path)

    assert len(tools) == 2
    assert tools[0].name == "calculate"
    assert tools[1].description == "Print value"


def test_load_tools_from_file_invalid(tmp_path: Path) -> None:
    """Invalid definitions should raise a descriptive error."""

    tools_path = tmp_path / "tools.json"
    tools_path.write_text(json.dumps([123]), encoding="utf-8")

    with pytest.raises(DatasetGenerationError):
        load_tools_from_file(tools_path)
