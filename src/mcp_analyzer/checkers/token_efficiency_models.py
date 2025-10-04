"""LLM-based parameter generation for token efficiency testing."""

import json
import logging
import os
from typing import Any, Dict, Optional, cast

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ParameterGenerationRequest(BaseModel):
    """Request for LLM to generate tool parameters."""

    tool_name: str
    tool_description: Optional[str]
    input_schema: Dict[str, Any]
    previous_attempt: Optional[Dict[str, Any]] = None
    error_feedback: Optional[str] = None


class ParameterGenerationResponse(BaseModel):
    """LLM response with generated parameters."""

    model_config = ConfigDict(strict=True)

    parameters_json: str = Field(
        description="JSON string of generated parameters that satisfy the tool schema"
    )
    reasoning: str = Field(description="Brief explanation of parameter choices")


class LLMParameterGenerator:
    """
    Generate valid tool parameters using LLM with structured output.

    Uses OpenAI or Anthropic to intelligently create parameters based on:
    - Tool schema
    - Error feedback from previous attempts
    - Tool description and context
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        """
        Initialize the parameter generator.

        Args:
            model: Model to use (gpt-4o-mini, gpt-4o, claude-3-5-sonnet-20241022, etc.)
        """
        self.model = model
        self._client: Any = None
        self._provider: Optional[str] = None

        if model.startswith("gpt"):
            try:
                import openai

                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    logger.warning(
                        "OPENAI_API_KEY not set, LLM parameter generation disabled"
                    )
                    return
                self._client = openai.OpenAI(api_key=api_key)
                self._provider = "openai"
            except ImportError:
                logger.warning(
                    "openai package not installed, LLM parameter generation disabled"
                )
        elif model.startswith("claude"):
            try:
                import anthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    logger.warning(
                        "ANTHROPIC_API_KEY not set, LLM parameter generation disabled"
                    )
                    return
                self._client = anthropic.Anthropic(api_key=api_key)
                self._provider = "anthropic"
            except ImportError:
                logger.warning(
                    "anthropic package not installed, LLM parameter generation disabled"
                )

    def is_available(self) -> bool:
        """Check if LLM generation is available."""
        return self._client is not None

    async def generate_parameters(
        self,
        tool_name: str,
        input_schema: Dict[str, Any],
        tool_description: Optional[str] = None,
        previous_attempt: Optional[Dict[str, Any]] = None,
        error_feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate valid parameters for a tool using LLM.

        Args:
            tool_name: Name of the tool
            input_schema: JSON schema for tool parameters
            tool_description: Optional description of what the tool does
            previous_attempt: Previous parameter attempt that failed
            error_feedback: Error message from previous attempt

        Returns:
            Generated parameters or None if generation fails
        """
        if not self.is_available():
            return None

        try:
            if self._provider == "openai":
                return await self._generate_with_openai(
                    tool_name,
                    input_schema,
                    tool_description,
                    previous_attempt,
                    error_feedback,
                )
            elif self._provider == "anthropic":
                return await self._generate_with_anthropic(
                    tool_name,
                    input_schema,
                    tool_description,
                    previous_attempt,
                    error_feedback,
                )
        except Exception as e:
            logger.warning(f"LLM parameter generation failed for {tool_name}: {e}")
            return None
        return None

    async def _generate_with_openai(
        self,
        tool_name: str,
        input_schema: Dict[str, Any],
        tool_description: Optional[str],
        previous_attempt: Optional[Dict[str, Any]],
        error_feedback: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Generate parameters using OpenAI structured outputs."""
        prompt = self._build_prompt(
            tool_name, input_schema, tool_description, previous_attempt, error_feedback
        )

        client = cast(Any, self._client)
        response = client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a parameter generation expert. Generate valid, realistic parameters for MCP tools based on their schema and any error feedback.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=ParameterGenerationResponse,
        )

        if response.choices[0].message.parsed:
            result = response.choices[0].message.parsed
            logger.info(f"Generated parameters for {tool_name}: {result.reasoning}")
            try:
                parsed: Dict[str, Any] = json.loads(result.parameters_json)
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse parameters JSON for {tool_name}: {e}")
                return None

        return None

    async def _generate_with_anthropic(
        self,
        tool_name: str,
        input_schema: Dict[str, Any],
        tool_description: Optional[str],
        previous_attempt: Optional[Dict[str, Any]],
        error_feedback: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Generate parameters using Anthropic with JSON schema."""
        prompt = self._build_prompt(
            tool_name, input_schema, tool_description, previous_attempt, error_feedback
        )

        client = cast(Any, self._client)
        response = client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            system="You are a parameter generation expert. Generate valid, realistic parameters for MCP tools based on their schema and any error feedback. Return ONLY valid JSON matching the requested schema.",
        )

        try:
            content = response.content[0].text
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                result = cast(Dict[str, Any], json.loads(json_str))
                logger.info(f"Generated parameters for {tool_name}")
                value = result.get("parameters", result)
                if isinstance(value, dict):
                    return cast(Dict[str, Any], value)
                return None
        except Exception as e:
            logger.warning(f"Failed to parse Anthropic response for {tool_name}: {e}")

        return None

    def _build_prompt(
        self,
        tool_name: str,
        input_schema: Dict[str, Any],
        tool_description: Optional[str],
        previous_attempt: Optional[Dict[str, Any]],
        error_feedback: Optional[str],
    ) -> str:
        """Build prompt for LLM parameter generation."""
        prompt_parts = [
            f"Generate valid parameters for the MCP tool '{tool_name}'.\n",
        ]

        if tool_description:
            prompt_parts.append(f"Tool Purpose: {tool_description}\n")

        prompt_parts.append(f"\nInput Schema:\n{json.dumps(input_schema, indent=2)}\n")

        if previous_attempt and error_feedback:
            prompt_parts.append(
                f"\nPrevious Attempt (FAILED):\n{json.dumps(previous_attempt, indent=2)}\n"
            )
            prompt_parts.append(f"\nError Feedback:\n{error_feedback}\n")
            prompt_parts.append("\nIMPORTANT: Fix the errors in the previous attempt.")
        else:
            prompt_parts.append(
                "\nGenerate minimal but valid parameters to test the tool."
            )

        prompt_parts.append("\nRequirements:")
        prompt_parts.append("- Satisfy all 'required' fields in the schema")
        prompt_parts.append("- Use realistic, minimal test values")
        prompt_parts.append(
            "- For arrays with minItems, provide at least that many elements"
        )
        prompt_parts.append("- For strings, use short realistic examples")
        prompt_parts.append("- For IDs, use simple test values like 'test_id_1'")
        prompt_parts.append("- Keep parameters minimal to test token efficiency")
        prompt_parts.append(
            "\nReturn the parameters as a valid JSON string in the parameters_json field."
        )

        return "\n".join(prompt_parts)
