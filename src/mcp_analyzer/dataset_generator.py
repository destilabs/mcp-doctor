"""Synthetic dataset generation using LLM providers."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence

import httpx

from .mcp_client import MCPTool


class DatasetGenerationError(Exception):
    """Raised when synthetic dataset generation fails."""


class ProviderResolutionError(DatasetGenerationError):
    """Raised when a model provider cannot be determined."""


class ModelProvider(str, Enum):
    """Supported LLM providers for dataset generation."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


DEFAULT_MODELS: Dict[ModelProvider, str] = {
    ModelProvider.ANTHROPIC: "claude-4-sonnet",
    ModelProvider.OPENAI: "gpt-4.1",
}


@dataclass
class ProviderConfig:
    """Resolved provider configuration."""

    provider: ModelProvider
    api_key: str
    model: str


class LLMClient(Protocol):
    """Protocol for language model clients."""

    async def complete(self, prompt: str) -> str:
        """Return raw text completion for the given prompt."""


def resolve_provider(model: Optional[str] = None) -> ProviderConfig:
    """Resolve which provider to use based on environment variables."""

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if anthropic_key:
        resolved_model = model or DEFAULT_MODELS[ModelProvider.ANTHROPIC]
        return ProviderConfig(ModelProvider.ANTHROPIC, anthropic_key, resolved_model)

    if openai_key:
        resolved_model = model or DEFAULT_MODELS[ModelProvider.OPENAI]
        return ProviderConfig(ModelProvider.OPENAI, openai_key, resolved_model)

    raise ProviderResolutionError(
        "Set either ANTHROPIC_API_KEY or OPENAI_API_KEY to generate datasets."
    )


class AnthropicClient:
    """Minimal Anthropic Messages API client."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        max_tokens: int = 2048,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.base_url = os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com")
        self.api_version = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")

    async def complete(self, prompt: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        async with httpx.AsyncClient(
            timeout=self.timeout, base_url=self.base_url
        ) as client:
            response = await client.post("/v1/messages", headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - thin wrapper
                raise DatasetGenerationError(
                    f"Anthropic API request failed with status {exc.response.status_code}"
                ) from exc

        data = response.json()

        try:
            content_blocks = data["content"]
        except (KeyError, TypeError) as exc:
            raise DatasetGenerationError(
                "Unexpected response format from Anthropic API"
            ) from exc

        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if not text_parts:
            raise DatasetGenerationError(
                "Anthropic response did not contain text content"
            )
        return "\n".join(part.strip() for part in text_parts if part).strip()


class OpenAIClient:
    """Minimal OpenAI Responses API client."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        max_tokens: int = 2048,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com")

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        output_entries = data.get("output")
        if isinstance(output_entries, list):
            text_parts: List[str] = []
            for entry in output_entries:
                if not isinstance(entry, dict):
                    continue
                for content in entry.get("content", []):
                    if (
                        isinstance(content, dict)
                        and content.get("type") in {"text", "output_text"}
                        and isinstance(content.get("text"), str)
                    ):
                        text_parts.append(content["text"].strip())
            if text_parts:
                return "\n".join(text_parts).strip()

        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        if isinstance(output_text, list):
            joined = "\n".join(
                part.strip() for part in output_text if isinstance(part, str)
            )
            if joined.strip():
                return joined.strip()

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content.strip()

        raise DatasetGenerationError(
            "OpenAI response did not include usable text content"
        )

    async def complete(self, prompt: str) -> str:
        headers = {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": self.max_tokens,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout, base_url=self.base_url
        ) as client:
            response = await client.post("/v1/responses", headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - thin wrapper
                raise DatasetGenerationError(
                    f"OpenAI API request failed with status {exc.response.status_code}"
                ) from exc

        data = response.json()
        return self._extract_text(data)


class DatasetGenerator:
    """Generate synthetic datasets of tool use cases."""

    def __init__(
        self,
        *,
        llm_client: Optional[LLMClient] = None,
        model: Optional[str] = None,
        max_tasks: int = 20,
        llm_timeout: float = 60.0,
    ) -> None:
        self.max_tasks = max_tasks
        self.llm_timeout = llm_timeout
        if llm_client is not None:
            self._llm_client = llm_client
        else:
            provider = resolve_provider(model=model)
            if provider.provider == ModelProvider.ANTHROPIC:
                self._llm_client = AnthropicClient(
                    provider.api_key, provider.model, timeout=self.llm_timeout
                )
            else:
                self._llm_client = OpenAIClient(
                    provider.api_key, provider.model, timeout=self.llm_timeout
                )

    async def generate_dataset(
        self, tools: Sequence[MCPTool], *, num_tasks: int = 5
    ) -> List[Dict[str, Any]]:
        """Generate synthetic dataset entries for the provided tools."""
        if not tools:
            raise DatasetGenerationError("Provide at least one tool to generate tasks")

        if num_tasks < 1:
            raise DatasetGenerationError("Number of tasks must be greater than zero")

        if num_tasks > self.max_tasks:
            raise DatasetGenerationError(
                f"Requested {num_tasks} tasks but the generator allows up to {self.max_tasks}"
            )

        prompt = self._build_prompt(tools, num_tasks)
        raw_response = await self._llm_client.complete(prompt)
        dataset = self._parse_dataset(raw_response)
        self._validate_dataset(dataset, tools)
        return dataset

    def _build_prompt(self, tools: Sequence[MCPTool], num_tasks: int) -> str:
        tool_sections = []
        for tool in tools:
            description = tool.description or "No description provided"
            parameters = tool.parameters or tool.input_schema or {}
            tool_sections.append(
                json.dumps(
                    {
                        "name": tool.name,
                        "description": description,
                        "parameters": parameters,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )

        tool_block = "\n\n".join(tool_sections)
        instructions = (
            "You are helping generate synthetic training data for MCP tool usage. "
            "Create a JSON array with exactly {num_tasks} task objects. Each object must contain:"
            "\n  - 'prompt': Natural language instructions for an analyst or developer.\n"
            "  - 'tools_called': Array of tool names used in execution order.\n"
            "  - 'tools_args': Array of arrays representing arguments passed to each tool.\n"
            "Ensure 'tools_args' has the same length and order as 'tools_called'. "
            "Focus on realistic workflows combining tools when appropriate. "
            "Only return valid JSON, without commentary or markdown fences."
        ).format(num_tasks=num_tasks)

        return (
            f"Available MCP tools (JSON format):\n{tool_block}\n\n"
            f"{instructions}\n"
            "Use concise prompts (max 40 words). Include both single-tool and multi-tool use cases."
        )

    def _parse_dataset(self, response_text: str) -> List[Dict[str, Any]]:
        json_text = self._extract_json(response_text)
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise DatasetGenerationError(
                "Failed to parse LLM response as JSON"
            ) from exc

        if not isinstance(parsed, list):
            raise DatasetGenerationError(
                "Expected response to be a JSON array of tasks"
            )
        return parsed

    def _extract_json(self, text: str) -> str:
        code_block_pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
        match = code_block_pattern.search(text)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _validate_dataset(
        self, dataset: Iterable[Dict[str, Any]], tools: Sequence[MCPTool]
    ) -> None:
        tool_names = {tool.name for tool in tools}
        for index, item in enumerate(dataset):
            if not isinstance(item, dict):
                raise DatasetGenerationError(
                    f"Task at index {index} is not an object: {type(item).__name__}"
                )

            prompt = item.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise DatasetGenerationError(
                    f"Task {index} is missing a valid 'prompt' string"
                )

            tools_called = item.get("tools_called")
            if not isinstance(tools_called, list) or not tools_called:
                raise DatasetGenerationError(
                    f"Task {index} must include a non-empty 'tools_called' list"
                )

            tools_args = item.get("tools_args")
            if not isinstance(tools_args, list) or len(tools_args) != len(tools_called):
                raise DatasetGenerationError(
                    f"Task {index} 'tools_args' must align with 'tools_called'"
                )

            for tool_name in tools_called:
                if tool_name not in tool_names:
                    raise DatasetGenerationError(
                        f"Task {index} references unknown tool '{tool_name}'"
                    )

            for arg_index, arg_set in enumerate(tools_args):
                if not isinstance(arg_set, list):
                    raise DatasetGenerationError(
                        f"Task {index} argument entry {arg_index} is not a list"
                    )


__all__ = [
    "DatasetGenerator",
    "DatasetGenerationError",
    "ProviderResolutionError",
    "resolve_provider",
    "ModelProvider",
]
