from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_evaluator.llm_providers import (
    AnthropicProvider,
    OpenAIProvider,
    create_provider,
)


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.content = []
    client.messages.create.return_value = response
    return client


@pytest.fixture
def mock_openai_client() -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "test response"
    response.choices[0].message.tool_calls = None
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def mock_mcp_client() -> AsyncMock:
    client = AsyncMock()
    client.call_tool.return_value = {"result": "success"}
    return client


@pytest.mark.asyncio
async def test_anthropic_provider_initialization_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY required"):
        AnthropicProvider()


@pytest.mark.asyncio
async def test_anthropic_provider_query_with_text_response(
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic_client: MagicMock,
    mock_mcp_client: AsyncMock,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value = mock_anthropic_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello, world!"
        mock_anthropic_client.messages.create.return_value.content = [text_block]

        provider = AnthropicProvider()
        tools = [MagicMock(name="test_tool", description="Test", input_schema={})]

        response_text, tools_called = await provider.query_with_tools(
            "test query", tools, mock_mcp_client
        )

        assert response_text == "Hello, world!"
        assert tools_called == []


@pytest.mark.asyncio
async def test_anthropic_provider_query_with_tool_use(
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic_client: MagicMock,
    mock_mcp_client: AsyncMock,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value = mock_anthropic_client

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_weather"
        tool_block.input = {"location": "NYC"}
        mock_anthropic_client.messages.create.return_value.content = [tool_block]

        provider = AnthropicProvider()
        tools = [
            MagicMock(name="get_weather", description="Get weather", input_schema={})
        ]

        response_text, tools_called = await provider.query_with_tools(
            "what's the weather?", tools, mock_mcp_client
        )

        assert response_text == ""
        assert tools_called == ["get_weather"]
        mock_mcp_client.call_tool.assert_called_once_with(
            "get_weather", {"location": "NYC"}
        )


@pytest.mark.asyncio
async def test_openai_provider_initialization_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY required"):
        OpenAIProvider()


@pytest.mark.asyncio
async def test_openai_provider_query_with_text_response(
    monkeypatch: pytest.MonkeyPatch,
    mock_openai_client: MagicMock,
    mock_mcp_client: AsyncMock,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("openai.OpenAI") as mock_openai:
        mock_openai.return_value = mock_openai_client

        provider = OpenAIProvider()
        tools = [MagicMock(name="test_tool", description="Test", parameters={})]

        response_text, tools_called = await provider.query_with_tools(
            "test query", tools, mock_mcp_client
        )

        assert response_text == "test response"
        assert tools_called == []


@pytest.mark.asyncio
async def test_openai_provider_query_with_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
    mock_openai_client: MagicMock,
    mock_mcp_client: AsyncMock,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("openai.OpenAI") as mock_openai:
        mock_openai.return_value = mock_openai_client

        tool_call = MagicMock()
        tool_call.function.name = "calculate"
        tool_call.function.arguments = '{"x": 5, "y": 3}'
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.tool_calls = [tool_call]

        provider = OpenAIProvider()
        tools = [MagicMock(name="calculate", description="Calculate", parameters={})]

        response_text, tools_called = await provider.query_with_tools(
            "calculate 5 + 3", tools, mock_mcp_client
        )

        assert tools_called == ["calculate"]
        mock_mcp_client.call_tool.assert_called_once_with("calculate", {"x": 5, "y": 3})


def test_create_provider_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.Anthropic"):
        provider = create_provider("anthropic")
        assert isinstance(provider, AnthropicProvider)


def test_create_provider_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("openai.OpenAI"):
        provider = create_provider("openai")
        assert isinstance(provider, OpenAIProvider)


def test_create_provider_invalid() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        create_provider("invalid")


def test_create_provider_with_custom_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.Anthropic"):
        provider = create_provider("anthropic", "custom-model")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "custom-model"
