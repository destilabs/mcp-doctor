from __future__ import annotations

from src.mcp_evaluator.result_formatters import (
    format_evaluation_result,
    format_generation_result,
    format_tool_call_result,
)


def test_format_tool_call_result_without_arguments() -> None:
    result = format_tool_call_result("get_weather")
    assert result == {"tool_name": "get_weather", "arguments": [{}]}


def test_format_tool_call_result_with_arguments() -> None:
    args = {"location": "NYC", "units": "celsius"}
    result = format_tool_call_result("get_weather", args)
    assert result == {
        "tool_name": "get_weather",
        "arguments": [{"location": "NYC", "units": "celsius"}],
    }


def test_format_evaluation_result_with_tool_calls() -> None:
    result = format_evaluation_result(
        query="What's the weather?",
        tool_calls=["get_weather", "get_forecast"],
        provider="anthropic",
        model="claude-sonnet-4",
        execution_success=True,
    )

    assert result["query"] == "What's the weather?"
    assert result["model"] == "anthropic-claude-sonnet-4"
    assert result["finish_reason"] == "tool_calls"
    assert result["success"] is True
    assert len(result["tool_calls"]) == 2
    assert result["tool_calls"][0]["tool_name"] == "get_weather"
    assert result["tool_calls"][1]["tool_name"] == "get_forecast"


def test_format_evaluation_result_without_tool_calls() -> None:
    result = format_evaluation_result(
        query="Hello",
        tool_calls=[],
        provider="openai",
        model="gpt-4o",
        execution_success=True,
    )

    assert result["query"] == "Hello"
    assert result["model"] == "openai-gpt-4o"
    assert result["finish_reason"] == "stop"
    assert result["success"] is True
    assert len(result["tool_calls"]) == 0


def test_format_evaluation_result_with_failure() -> None:
    result = format_evaluation_result(
        query="Test query",
        tool_calls=["tool1"],
        provider="anthropic",
        model="claude",
        execution_success=False,
    )

    assert result["success"] is False


def test_format_generation_result_with_tools() -> None:
    result = format_generation_result(
        query="Calculate 2 + 2",
        tool_calls=["calculate"],
        provider="anthropic",
        model="claude-sonnet-4",
    )

    assert result["query"] == "Calculate 2 + 2"
    assert result["model"] == "anthropic-claude-sonnet-4"
    assert result["finish_reason"] == "tool_calls"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool_name"] == "calculate"


def test_format_generation_result_without_tools() -> None:
    result = format_generation_result(
        query="Just a question",
        tool_calls=[],
        provider="openai",
        model="gpt-4o",
    )

    assert result["query"] == "Just a question"
    assert result["model"] == "openai-gpt-4o"
    assert result["finish_reason"] == "stop"
    assert len(result["tool_calls"]) == 0
