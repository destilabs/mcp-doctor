from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol, cast

from mcp_analyzer.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    async def query_with_tools(
        self, query: str, tools: list[Any], mcp_client: MCPClient
    ) -> tuple[str, list[str]]: ...


class AnthropicProvider:
    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        from anthropic import Anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required in .env")

        self.client = Anthropic(api_key=api_key)
        self.model = model

    async def query_with_tools(
        self, query: str, tools: list[Any], mcp_client: MCPClient
    ) -> tuple[str, list[str]]:
        anthropic_tools = self._convert_tools(tools)
        messages = [{"role": "user", "content": query}]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=cast(Any, messages),
            tools=cast(Any, anthropic_tools),
        )

        return await self._process_response(response, mcp_client)

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description or "No description",
                "input_schema": tool.input_schema
                or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]

    async def _process_response(
        self, response: Any, mcp_client: MCPClient
    ) -> tuple[str, list[str]]:
        response_text = ""
        actual_tools_called = []

        for block in response.content:
            if block.type == "text":
                response_text += block.text
            elif block.type == "tool_use":
                actual_tools_called.append(block.name)
                try:
                    _ = await mcp_client.call_tool(block.name, block.input)
                    logger.info("Tool executed: %s", block.name)
                except Exception as e:
                    logger.error("Tool execution failed %s: %s", block.name, str(e))

        return response_text, actual_tools_called


class OpenAIProvider:
    def __init__(self, model: str = "gpt-4o") -> None:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required in .env")

        self.client = OpenAI(api_key=api_key)
        self.model = model

    async def query_with_tools(
        self, query: str, tools: list[Any], mcp_client: MCPClient
    ) -> tuple[str, list[str]]:
        openai_tools = self._convert_tools(tools)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": query}],  # type: ignore[arg-type]
            tools=cast(Any, openai_tools),
        )

        return await self._process_response(response, mcp_client)

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "No description",
                    "parameters": tool.parameters
                    or tool.input_schema
                    or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
        ]

    async def _process_response(
        self, response: Any, mcp_client: MCPClient
    ) -> tuple[str, list[str]]:
        message = response.choices[0].message
        response_text = message.content or ""
        actual_tools_called = []

        if message.tool_calls:
            for tool_call in message.tool_calls:
                actual_tools_called.append(tool_call.function.name)
                try:
                    args = json.loads(tool_call.function.arguments)
                    _ = await mcp_client.call_tool(tool_call.function.name, args)
                    logger.info("Tool executed: %s", tool_call.function.name)
                except Exception as e:
                    logger.error(
                        "Tool execution failed %s: %s", tool_call.function.name, str(e)
                    )

        return response_text, actual_tools_called


def create_provider(provider: str, model: str | None = None) -> LLMProvider:
    if provider == "anthropic":
        return AnthropicProvider(model or "claude-sonnet-4-20250514")
    elif provider == "openai":
        return OpenAIProvider(model or "gpt-4o")
    else:
        raise ValueError(f"Unsupported provider: {provider}")
