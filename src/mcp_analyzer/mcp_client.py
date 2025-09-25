"""MCP server client for fetching tool information.

This module also provides an LLM-driven per-tool chat execution helper that
lets a model call a single MCP tool via the Messages API (Anthropic-compatible).
"""

import asyncio
import json
import logging
import os
import random
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
from pydantic import BaseModel, ValidationError

from .mcp_sse_client import MCPSSEClient
from .mcp_stdio_client import MCPStdioClient
from .npx_launcher import NPXLauncherError, NPXServerManager, is_npx_command

logger = logging.getLogger(__name__)


class MCPServerInfo(BaseModel):
    """Information about the MCP server."""

    protocol_version: Optional[str] = None
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None


class MCPTool(BaseModel):
    """Representation of an MCP tool."""

    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None


class LLMToolCall(BaseModel):
    """Record of a tool call initiated by an LLM."""

    id: str
    name: str
    input: Dict[str, Any]
    result: Optional[Any] = None


class MCPClientError(Exception):
    """Custom exception for MCP client errors."""

    pass


class MCPClient:
    """Client for communicating with MCP servers."""

    def __init__(
        self,
        server_target: str,
        timeout: int = 30,
        transport: str = "auto",
        *,
        http_headers: Optional[Dict[str, str]] = None,
        **npx_kwargs: Any,
    ) -> None:
        """
        Initialize MCP client.

        Args:
            server_target: Either a URL (http://...) or NPX command (npx ...)
            timeout: Request timeout in seconds
            transport: Transport type ("auto", "http", "stdio")
            **npx_kwargs: Additional arguments for NPX server (env_vars, working_dir, etc.)
        """
        self.server_target = server_target
        self.timeout = timeout
        self.npx_kwargs = npx_kwargs
        self._session: Optional[httpx.AsyncClient] = None
        self._npx_manager: Optional[NPXServerManager] = None
        self._stdio_client: Optional[MCPStdioClient] = None
        self._sse_client: Optional[MCPSSEClient] = None
        self._is_npx_server = is_npx_command(server_target)
        self._actual_server_url: Optional[str] = None
        self._http_headers: Dict[str, str] = dict(http_headers or {})

        self._transport = self._detect_transport_type(transport)

        if not self._is_npx_server and self._transport == "http":

            self._actual_server_url = server_target.rstrip("/")

    def _detect_transport_type(self, transport: str) -> str:
        """Detect the appropriate transport type."""
        if transport != "auto":
            return transport

        if self.server_target.startswith(("http://", "https://")):
            return "http"  # Will probe for SSE vs REST during connection
        elif self._is_npx_server:
            return "stdio"
        else:
            return "stdio"

    async def _probe_http_endpoint(self, url: str) -> str:
        """Probe HTTP endpoint to determine if it's SSE or REST."""
        try:
            logger.info(f"Probing endpoint type for: {url}")

            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    head_response = await client.head(url)
                    if head_response.status_code == 406:
                        logger.info(
                            "HEAD request returned 406 requiring text/event-stream; treating as SSE"
                        )
                        return "sse"
                    content_type = head_response.headers.get("content-type", "").lower()

                    if "text/event-stream" in content_type:
                        logger.info("Detected SSE endpoint (Server-Sent Events)")
                        return "sse"

                except httpx.HTTPStatusError:
                    pass

                try:
                    response = await asyncio.wait_for(client.get(url), timeout=3.0)

                    content_type = response.headers.get("content-type", "").lower()

                    if "text/event-stream" in content_type:
                        logger.info("Detected SSE endpoint via GET response")
                        return "sse"
                    elif response.status_code == 406:
                        logger.info(
                            "Endpoint returned 406 requiring text/event-stream; treating as SSE"
                        )
                        return "sse"
                    elif "application/json" in content_type:
                        logger.info("Detected REST API endpoint")
                        return "http"
                    else:
                        logger.info(
                            f"Unknown content type: {content_type}, defaulting to REST"
                        )
                        return "http"

                except asyncio.TimeoutError:
                    logger.warning("Quick probe timed out, might be SSE endpoint")
                    return "sse"

        except Exception as e:
            logger.warning(f"Failed to probe endpoint: {e}, defaulting to REST")
            return "http"

    async def _try_get_server_info_from_sse(self, sse_url: str) -> str:
        """Try to get server information from SSE endpoint or related paths."""
        try:
            if sse_url.endswith("/mcp"):
                base_url = sse_url[:-4]  # Remove '/mcp'
            else:
                base_url = sse_url.rstrip("/")

            info_paths = ["/", "/info", "/status", "/health"]

            async with httpx.AsyncClient(timeout=5.0) as client:
                for path in info_paths:
                    try:
                        test_url = f"{base_url}{path}"
                        logger.debug(f"Trying server info from: {test_url}")
                        response = await client.get(test_url)

                        if response.status_code == 200:
                            data = response.json()
                            if isinstance(data, dict):
                                name = data.get("message", data.get("name", "Unknown"))
                                version = data.get("version", "Unknown")

                                details = []
                                if "documentation" in data:
                                    details.append("Has API documentation")
                                if "endpoints" in data:
                                    endpoint_count = len(data["endpoints"])
                                    details.append(f"{endpoint_count} endpoints")
                                if "github" in data:
                                    details.append("Open source")

                                info_str = f"{name} v{version}"
                                if details:
                                    info_str += f" ({', '.join(details)})"

                                return info_str

                    except Exception as e:
                        logger.debug(f"Failed to get info from {test_url}: {e}")
                        continue

            return "Server information not available"

        except Exception as e:
            logger.debug(f"Error getting server info: {e}")
            return "Unable to retrieve server information"

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        await self._ensure_server_ready()

        if self._transport == "http":
            self._session = httpx.AsyncClient(timeout=self.timeout)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._session:
            await self._session.aclose()
        if self._npx_manager:
            await self._npx_manager.stop_all_servers()
        if self._stdio_client:
            await self._stdio_client.close()
        if self._sse_client:
            await self._sse_client.close()

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if not self._session:
            self._session = httpx.AsyncClient(timeout=self.timeout)
        return self._session

    async def _ensure_server_ready(self) -> None:
        """Ensure the server is running and ready for communication."""
        if self._transport == "stdio":
            self._stdio_client = MCPStdioClient(
                self.server_target, timeout=self.timeout, **self.npx_kwargs
            )
            await self._stdio_client.__aenter__()
            logger.info(f"STDIO MCP client connected to: {self.server_target}")

        elif self._transport == "http":
            if self._is_npx_server:
                # Launch NPX server for HTTP transport
                if not self._npx_manager:
                    self._npx_manager = NPXServerManager()

                try:
                    logger.info(f"Launching NPX server: {self.server_target}")
                    self._actual_server_url = await self._npx_manager.launch_server(
                        self.server_target, timeout=self.timeout, **self.npx_kwargs
                    )
                    logger.info(f"NPX server ready at: {self._actual_server_url}")
                except NPXLauncherError as e:
                    raise MCPClientError(f"Failed to launch NPX server: {e}")
            else:
                # For HTTP URLs, probe to detect SSE vs REST
                actual_transport = await self._probe_http_endpoint(self.server_target)
                if actual_transport == "sse":
                    # Update transport type and try SSE connection
                    self._transport = "sse"
                    logger.info("Switching to SSE transport")

                    try:
                        self._sse_client = MCPSSEClient(
                            self.server_target, timeout=self.timeout, headers=self._http_headers
                        )
                        await self._sse_client.__aenter__()
                        logger.info(
                            f"SSE MCP client connected to: {self.server_target}"
                        )
                    except Exception as e:
                        # If SSE connection fails, provide helpful guidance
                        server_info = await self._try_get_server_info_from_sse(
                            self.server_target
                        )

                        raise MCPClientError(
                            f"🌊 Detected SSE (Server-Sent Events) endpoint at {self.server_target}.\n\n"
                            f"📋 Server Info: {server_info}\n\n"
                            f"❌ SSE connection failed: {e}\n\n"
                            f"🔍 This endpoint might be:\n"
                            f"   • A non-standard MCP implementation\n"
                            f"   • An API proxy rather than a direct MCP server\n"
                            f"   • Using a custom SSE protocol\n\n"
                            f"💡 Try these alternatives:\n"
                            f"   1. Official MCP Inspector: npx @modelcontextprotocol/inspector --cli {self.server_target} --transport sse\n"
                            f"   2. Check server documentation for proper MCP endpoints\n"
                            f"   3. Contact the server maintainer for MCP compatibility details"
                        )

    def get_server_url(self) -> str:
        """Get the actual server URL (after NPX launch if applicable)."""
        if self._transport == "stdio":
            return f"stdio://{self.server_target}"
        elif self._transport == "sse":
            return f"sse://{self.server_target}"

        if not self._actual_server_url:
            raise MCPClientError(
                "Server URL not available. Call _ensure_server_ready() first."
            )
        return self._actual_server_url

    async def get_server_info(self) -> MCPServerInfo:
        """
        Fetch basic server information.

        Returns:
            Server information including protocol version and capabilities

        Raises:
            MCPClientError: If server is unreachable or invalid
        """
        await self._ensure_server_ready()

        try:
            if self._transport == "stdio":
                if not self._stdio_client:
                    raise MCPClientError("STDIO client not initialized")
                info = await self._stdio_client.get_server_info()
                return MCPServerInfo(
                    protocol_version=info.get("protocol_version"),
                    server_name=info.get("server_name", "MCP Server"),
                    server_version=info.get("server_version"),
                    capabilities=info.get("capabilities", {}),
                )
            elif self._transport == "sse":
                if not self._sse_client:
                    raise MCPClientError("SSE client not initialized")
                info = await self._sse_client.get_server_info()
                return MCPServerInfo(
                    protocol_version=info.get("protocol_version"),
                    server_name=info.get("server_name", "SSE MCP Server"),
                    server_version=info.get("server_version"),
                    capabilities=info.get("capabilities", {}),
                )
            else:
                # HTTP transport with enhanced debugging
                server_url = self.get_server_url()
                logger.info(f"Making HTTP request to: {server_url}")

                session = await self._get_session()

                try:
                    # Add explicit timeout wrapper
                    response = await asyncio.wait_for(
                        session.get(server_url), timeout=self.timeout
                    )
                    logger.info(f"HTTP response: {response.status_code}")

                except asyncio.TimeoutError:
                    raise MCPClientError(
                        f"HTTP request timed out after {self.timeout} seconds. "
                        f"The server at {server_url} is not responding."
                    )

                if response.status_code == 404:
                    raise MCPClientError(
                        f"MCP server not found at {server_url} (404). "
                        f"Make sure the server is running and MCP is mounted at the correct path."
                    )

                if response.status_code != 200:
                    # Include response body for better debugging
                    try:
                        error_body = response.text[:200]
                    except Exception:
                        error_body = "Unable to read response body"

                    raise MCPClientError(
                        f"Server returned status {response.status_code}. "
                        f"Response: {error_body}"
                    )

                try:
                    data = response.json()
                    logger.debug(
                        f"Server response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
                    )
                except Exception as e:
                    # Include response content for debugging
                    try:
                        content_preview = response.text[:200]
                    except Exception:
                        content_preview = "Unable to read response content"

                    raise MCPClientError(
                        f"Invalid JSON response from server: {e}. "
                        f"Response content: {content_preview}"
                    )

                return MCPServerInfo(
                    protocol_version=data.get("protocol_version"),
                    server_name=data.get("server_name", "Unknown"),
                    server_version=data.get("server_version"),
                    capabilities=data.get("capabilities", {}),
                )

        except httpx.ConnectError as e:
            raise MCPClientError(
                f"Cannot connect to MCP server at {self.get_server_url()}. "
                f"Connection error: {e}. Make sure the server is running and accessible."
            )
        except httpx.TimeoutException:
            raise MCPClientError(
                f"HTTP request timed out after {self.timeout} seconds. "
                f"The server at {self.get_server_url()} is taking too long to respond."
            )
        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Unexpected error connecting to HTTP server: {e}")

    async def get_tools(self) -> List[MCPTool]:
        """
        Fetch all available tools from the MCP server.

        Returns:
            List of tools with their schemas and descriptions

        Raises:
            MCPClientError: If tools cannot be fetched
        """
        await self._ensure_server_ready()

        try:
            if self._transport == "stdio":
                if not self._stdio_client:
                    raise MCPClientError("STDIO client not initialized")
                tools_data = await self._stdio_client.list_tools()
            elif self._transport == "sse":
                if not self._sse_client:
                    raise MCPClientError("SSE client not initialized")
                tools_data = await self._sse_client.list_tools()
            else:
                server_url = self.get_server_url()
                session = await self._get_session()

                try:
                    response = await asyncio.wait_for(
                        session.get(server_url), timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    raise MCPClientError(
                        f"HTTP request for tools timed out after {self.timeout} seconds. "
                        f"The server at {server_url} is not responding."
                    )

                if response.status_code != 200:
                    try:
                        error_body = response.text[:200]
                    except Exception:
                        error_body = "Unable to read response body"

                    raise MCPClientError(
                        f"Cannot fetch tools: Server returned {response.status_code}. "
                        f"Response: {error_body}"
                    )

                try:
                    data = response.json()
                except Exception as e:
                    try:
                        content_preview = response.text[:200]
                    except Exception:
                        content_preview = "Unable to read response content"

                    raise MCPClientError(
                        f"Invalid JSON response when fetching tools: {e}. "
                        f"Response content: {content_preview}"
                    )

                tools_data = data.get("tools", [])

            if not tools_data:
                logger.warning("No tools found in MCP server response")
                return []

            tools = []
            for tool_data in tools_data:
                try:

                    if isinstance(tool_data, str):

                        tool = MCPTool(name=tool_data)
                    elif isinstance(tool_data, dict):

                        tool = MCPTool(
                            name=tool_data.get("name", "unnamed_tool"),
                            description=tool_data.get("description"),
                            input_schema=tool_data.get("inputSchema"),
                            parameters=tool_data.get("parameters"),
                        )
                    else:
                        logger.warning(
                            f"Unexpected tool data format: {type(tool_data)}"
                        )
                        continue

                    tools.append(tool)

                except ValidationError as e:
                    logger.warning(f"Failed to parse tool data: {e}")
                    continue

            return tools

        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Failed to fetch tools: {e}")

    async def get_tool_details(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific tool.

        Args:
            tool_name: Name of the tool to get details for

        Returns:
            Detailed tool information if available
        """
        await self._ensure_server_ready()
        server_url = self.get_server_url()

        try:

            session = await self._get_session()

            endpoints = [
                f"{server_url}/tools/{tool_name}",
                f"{server_url}/tool/{tool_name}",
                f"{server_url}/schema/{tool_name}",
            ]

            for endpoint in endpoints:
                try:
                    response = await session.get(endpoint)
                    if response.status_code == 200:
                        return cast(Dict[str, Any], response.json())
                except httpx.HTTPStatusError:
                    continue

            logger.warning(f"No detailed endpoint found for tool: {tool_name}")
            return None

        except Exception as e:
            logger.error(f"Error fetching tool details for {tool_name}: {e}")
            return None

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool with the given arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result

        Raises:
            MCPClientError: If the tool call fails
        """
        await self._ensure_server_ready()

        try:
            if self._stdio_client:
                # Use STDIO client for NPX servers
                return await self._stdio_client.call_tool(tool_name, arguments)
            elif self._sse_client:
                # Use SSE client for SSE servers
                return await self._sse_client.call_tool(tool_name, arguments)
            else:
                raise NotImplementedError("HTTP transport not supported")
        except Exception as e:
            if isinstance(e, MCPClientError):
                raise
            raise MCPClientError(f"Failed to call tool {tool_name}: {e}")

    # ------------------------------
    # LLM-driven per-tool chat logic
    # ------------------------------

    async def _generate_sample_message_for_tool(self, tool: MCPTool) -> str:
        """Generate a concise sample user message for a tool using any available LLM.

        Falls back to a deterministic prompt if no LLM provider is configured.
        """
        try:
            # Reuse the dataset generator's provider resolution to keep dependency surface small
            from .dataset_generator import (
                AnthropicClient as _AnthropicTextClient,
                OpenAIClient as _OpenAITextClient,
                resolve_provider as _resolve_provider,
                ModelProvider as _ModelProvider,
            )

            provider = _resolve_provider()
            prompt = (
                "Generate a single concise user request (max 30 words) that would "
                "cause an AI assistant to use the following MCP tool. "
                "Output only the user message, no commentary.\n\n" 
                f"Tool name: {tool.name}\n"
                f"Description: {tool.description or 'No description'}\n"
                f"Parameters (JSON): {json.dumps(tool.parameters or tool.input_schema or {}, ensure_ascii=False)}"
            )

            if provider.provider == _ModelProvider.ANTHROPIC:
                client = _AnthropicTextClient(provider.api_key, provider.model)
            else:
                client = _OpenAITextClient(provider.api_key, provider.model)

            try:
                text = await client.complete(prompt)
            except Exception:
                # Fall back if LLM call fails
                text = f"Please use the tool '{tool.name}' to perform a typical operation."
            return text.strip() or f"Use the '{tool.name}' tool for a common task."
        except Exception:
            # If no LLM keys are configured, return a deterministic generic prompt
            return f"Use the '{tool.name}' tool for a common task."

    @staticmethod
    def _normalize_tool_schema(tool: MCPTool) -> Dict[str, Any]:
        """Ensure we always pass a valid JSON schema to the LLM tools interface."""
        schema = tool.input_schema or tool.parameters
        if isinstance(schema, dict) and schema:
            return schema
        # Minimal permissive schema
        return {"type": "object", "properties": {}, "additionalProperties": True}

    @staticmethod
    def _anthropic_headers(api_key: str) -> Dict[str, str]:
        version = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")
        return {
            "x-api-key": api_key,
            "anthropic-version": version,
            "content-type": "application/json",
        }

    @staticmethod
    def _normalize_tool_result_content(result: Any) -> List[Dict[str, Any]]:
        """Convert MCP tool result into Anthropic tool_result content blocks."""
        # If server already returned MCP-style content blocks, pass them through
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list) and all(isinstance(c, dict) for c in content):
                return content  # Assume already in [{type: 'text', text: ...}] format

        # Otherwise stringify conservatively
        if isinstance(result, (str, int, float, bool)):
            text = str(result)
        else:
            try:
                text = json.dumps(result, ensure_ascii=False)
            except Exception:
                text = str(result)
        return [{"type": "text", "text": text}]

    async def process_query_for_tool(
        self,
        tool: MCPTool,
        *,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        system: Optional[str] = None,
    ) -> Tuple[str, List[LLMToolCall]]:
        """Run an LLM chat for a single tool and return response and tool calls.

        Logic (inspired by typical `process_query` flows):
        - Generate a sample user message with AI
        - Provide only the specified tool to the LLM
        - Execute any requested tool calls via this MCP client
        - Return the assistant's final text and the tool call records

        Requirements:
        - Requires `ANTHROPIC_API_KEY` in environment.
        - Uses Anthropic Messages HTTP API directly (no SDK dependency).
        """
        await self._ensure_server_ready()

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise MCPClientError(
                "ANTHROPIC_API_KEY is required to run LLM-driven tool chats"
            )

        base_url = os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com")
        model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

        sample_user = await self._generate_sample_message_for_tool(tool)
        messages: List[Dict[str, Any]] = [{"role": "user", "content": sample_user}]
        if system:
            # Anthropic supports a system prompt via top-level field in payload
            system_prompt = system
        else:
            system_prompt = None

        tools_payload = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": self._normalize_tool_schema(tool),
            }
        ]

        headers = self._anthropic_headers(api_key)

        async def _create(payload: Dict[str, Any]) -> Dict[str, Any]:
            retriable_statuses = {408, 409, 429, 500, 502, 503, 504, 522, 524, 529}
            base_delay = float(os.getenv("MCP_DOCTOR_LLM_BACKOFF_BASE", "0.5"))
            max_attempts = int(os.getenv("MCP_DOCTOR_LLM_BACKOFF_ATTEMPTS", "5"))
            attempt = 0

            last_error_text = None
            last_status = None

            while True:
                attempt += 1
                try:
                    async with httpx.AsyncClient(
                        base_url=base_url, timeout=self.timeout
                    ) as client:
                        resp = await client.post(
                            "/v1/messages", headers=headers, json=payload
                        )

                        if resp.status_code in retriable_statuses:
                            last_status = resp.status_code
                            try:
                                last_error_text = (await resp.aread()).decode()
                            except Exception:
                                try:
                                    last_error_text = resp.text
                                except Exception:
                                    last_error_text = "<unreadable>"

                            # Respect Retry-After if present
                            retry_after = resp.headers.get("retry-after")
                            if retry_after:
                                try:
                                    delay = max(float(retry_after), base_delay)
                                except ValueError:
                                    delay = base_delay
                            else:
                                delay = base_delay * (2 ** (attempt - 1))
                                # Add small jitter
                                delay += random.uniform(0, 0.25)

                            logger.warning(
                                "Anthropic API transient error %s (attempt %s/%s). Retrying in %.2fs", 
                                resp.status_code, attempt, max_attempts, delay,
                            )

                            if attempt >= max_attempts:
                                break
                            await asyncio.sleep(delay)
                            continue

                        # For non-retriable statuses raise
                        try:
                            resp.raise_for_status()
                        except httpx.HTTPStatusError as exc:  # pragma: no cover - network wrapper
                            err_text = exc.response.text[:200] if exc.response is not None else ""
                            raise MCPClientError(
                                f"Anthropic API error: {exc.response.status_code} {err_text}"
                            ) from exc

                        data = resp.json()
                        # If API returns a JSON error envelope with success status (unlikely), surface it
                        if isinstance(data, dict) and data.get("type") == "error":
                            err = data.get("error", {})
                            message = err.get("message", "Unknown error") if isinstance(err, dict) else str(err)
                            raise MCPClientError(f"Anthropic API returned error payload: {message}")

                        return data

                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    # Network issues - backoff and retry
                    last_error_text = str(exc)
                    if attempt >= max_attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                    logger.warning(
                        "Anthropic API network error (attempt %s/%s). Retrying in %.2fs: %s",
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue

            # If we exit the loop without returning, we exhausted retries
            status_part = f"{last_status} " if last_status is not None else ""
            snippet = (last_error_text or "").strip()[:200]
            raise MCPClientError(
                f"Anthropic API error: {status_part}{snippet or 'request failed after retries'}"
            )

        final_text_parts: List[str] = []
        tool_calls: List[LLMToolCall] = []
        loop_guard = 0

        while True:
            loop_guard += 1
            if loop_guard > 5:
                # Avoid infinite loops if a model keeps requesting tools
                break

            payload: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "tools": tools_payload,
            }
            if system_prompt:
                payload["system"] = system_prompt

            response = await _create(payload)
            content = response.get("content", [])

            # Collect assistant content to thread history
            assistant_blocks: List[Dict[str, Any]] = []
            pending_tool_uses: List[Dict[str, Any]] = []

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        final_text_parts.append(text)
                        assistant_blocks.append({"type": "text", "text": text})
                elif btype == "tool_use":
                    # Accumulate for execution
                    pending_tool_uses.append(block)
                    assistant_blocks.append(block)

            # Always append assistant's message to history
            if assistant_blocks:
                messages.append({"role": "assistant", "content": assistant_blocks})

            # If no tool requests, we are done
            if not pending_tool_uses:
                break

            # Execute each requested tool call and append tool_result blocks
            tool_result_blocks: List[Dict[str, Any]] = []
            for tu in pending_tool_uses:
                tu_id = tu.get("id") or ""
                tu_name = tu.get("name") or tool.name
                tu_input = cast(Dict[str, Any], tu.get("input") or {})

                try:
                    exec_result = await self.call_tool(tu_name, tu_input)
                except Exception as exec_err:  # pragma: no cover - thin wrapper
                    exec_result = {"error": str(exec_err)}

                tool_calls.append(
                    LLMToolCall(id=str(tu_id), name=str(tu_name), input=tu_input, result=exec_result)
                )

                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu_id,
                        "content": self._normalize_tool_result_content(exec_result),
                    }
                )

            # Append aggregated tool results as a single user message
            if tool_result_blocks:
                messages.append({"role": "user", "content": tool_result_blocks})

        return ("\n".join(final_text_parts).strip(), tool_calls)

    async def close(self) -> None:
        """Close connections and stop servers."""
        if self._session:
            await self._session.aclose()
            self._session = None
        if self._npx_manager:
            await self._npx_manager.stop_all_servers()
            self._npx_manager = None
        if self._stdio_client:
            await self._stdio_client.close()
            self._stdio_client = None
        if self._sse_client:
            await self._sse_client.close()
            self._sse_client = None
