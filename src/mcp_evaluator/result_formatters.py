from __future__ import annotations

from typing import Any


def format_tool_call_result(
    tool_name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"tool_name": tool_name, "arguments": [arguments or {}]}


def format_evaluation_result(
    query: str,
    tool_calls: list[str],
    provider: str,
    model: str,
    execution_success: bool = True,
) -> dict[str, Any]:
    return {
        "query": query,
        "tool_calls": [format_tool_call_result(tool) for tool in tool_calls],
        "model": f"{provider}-{model}",
        "finish_reason": "tool_calls" if tool_calls else "stop",
        "success": execution_success,
    }


def format_generation_result(
    query: str, tool_calls: list[str], provider: str, model: str
) -> dict[str, Any]:
    return {
        "query": query,
        "tool_calls": [format_tool_call_result(tool) for tool in tool_calls],
        "model": f"{provider}-{model}",
        "finish_reason": "tool_calls" if tool_calls else "stop",
    }
