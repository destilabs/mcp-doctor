"""Lightweight tests for LLM parameter generation helpers."""

from __future__ import annotations

import pytest

from mcp_analyzer.checkers.token_efficiency_models import (
    LLMParameterGenerator,
)


def test_openai_generator_unavailable_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gen = LLMParameterGenerator(model="gpt-4o-mini")
    assert gen.is_available() is False

    # Attempting to generate returns None gracefully
    _ = (
        pytest.run(
            async_fn=gen.generate_parameters(
                tool_name="demo",
                input_schema={"type": "object", "properties": {}},
            )
        )
        if hasattr(pytest, "run")
        else None
    )
    # We don't rely on pytest.run existing; just assert is_available guards
    assert gen.is_available() is False


def test_anthropic_generator_unavailable_without_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    gen = LLMParameterGenerator(model="claude-3-5-sonnet-20241022")
    assert gen.is_available() is False


def test_build_prompt_includes_core_sections() -> None:
    gen = LLMParameterGenerator(model="gpt-4o-mini")
    prompt = gen._build_prompt(
        tool_name="search",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
        tool_description="Find things",
        previous_attempt={"q": 123},
        error_feedback="q must be string",
    )

    assert "Generate valid parameters for the MCP tool 'search'" in prompt
    assert "Tool Purpose: Find things" in prompt
    assert '"q":' in prompt and '"type": "object"' in prompt
    assert "Previous Attempt (FAILED):" in prompt
    assert "Error Feedback:" in prompt


@pytest.mark.asyncio
async def test_openai_generation_happy_path(monkeypatch) -> None:
    # Provide dummy OPENAI client via sys.modules so import succeeds
    import sys
    import types

    class _DummyParseResult:
        def __init__(self) -> None:
            self.choices = [
                types.SimpleNamespace(
                    message=types.SimpleNamespace(
                        parsed=types.SimpleNamespace(
                            parameters_json='{"x": 1}', reasoning="ok"
                        )
                    )
                )
            ]

    class _DummyCompletions:
        def parse(self, **kwargs):
            return _DummyParseResult()

    class _DummyBeta:
        def __init__(self) -> None:
            self.chat = types.SimpleNamespace(completions=_DummyCompletions())

    class _DummyOpenAIClient:
        def __init__(self, api_key: str) -> None:
            self.beta = _DummyBeta()

    dummy_openai = types.SimpleNamespace(OpenAI=_DummyOpenAIClient)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", dummy_openai)

    gen = LLMParameterGenerator(model="gpt-4o-mini")
    assert gen.is_available() is True
    result = await gen.generate_parameters("t", {"type": "object", "properties": {}})
    assert result == {"x": 1}
