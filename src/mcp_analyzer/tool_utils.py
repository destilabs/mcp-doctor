"""Utilities for loading and fetching MCP tools."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from rich.console import Console

from .dataset_generator import DatasetGenerationError
from .mcp_client import MCPClient, MCPTool
from .npx_launcher import is_npx_command

console = Console()


def load_tools_from_file(tools_file: Path) -> List[MCPTool]:
    """Load MCP tools from a JSON file."""

    if not tools_file.exists():
        raise DatasetGenerationError(f"Tools file not found: {tools_file}")

    content = tools_file.read_text(encoding="utf-8").strip()
    if not content:
        raise DatasetGenerationError("Tools file is empty")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DatasetGenerationError("Tools file must contain valid JSON") from exc

    if not isinstance(payload, list):
        raise DatasetGenerationError("Tools file must contain a JSON array")

    tools: List[MCPTool] = []
    for index, entry in enumerate(payload):
        if isinstance(entry, str):
            tools.append(MCPTool(name=entry))
            continue
        if isinstance(entry, dict):
            try:
                tools.append(MCPTool(**entry))
            except ValidationError as exc:
                raise DatasetGenerationError(
                    f"Invalid tool definition at index {index}: {exc}"
                ) from exc
            continue
        raise DatasetGenerationError(
            f"Unsupported tool entry at index {index}: {type(entry).__name__}"
        )

    if not tools:
        raise DatasetGenerationError("Tools file must define at least one tool")

    return tools


async def fetch_tools_for_dataset(
    target: str, timeout: int, npx_kwargs: Optional[Dict[str, Any]] = None
) -> List[MCPTool]:
    """Fetch MCP tools from a running server or NPX command."""

    if npx_kwargs is None:
        npx_kwargs = {}

    client = MCPClient(target, timeout=timeout, **npx_kwargs)
    is_npx = is_npx_command(target)

    status_message = (
        "[bold green]Launching NPX server..."
        if is_npx
        else "[bold green]Connecting to MCP server..."
    )

    with console.status(status_message):
        server_info = await client.get_server_info()
        tools = await client.get_tools()

    try:
        if is_npx:
            actual_url = client.get_server_url()
            console.print(f"✅ NPX server launched at [cyan]{actual_url}[/cyan]")
        else:
            console.print(f"✅ Connected to MCP server [cyan]{target}[/cyan]")

        server_name = getattr(server_info, "server_name", None)
        if server_name:
            console.print(f"📛 Server name: [bold]{server_name}[/bold]")

        console.print(f"📦 Retrieved [bold]{len(tools)}[/bold] tools\n")
    finally:
        await client.close()

    return tools
