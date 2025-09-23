"""Main CLI interface for MCP Analyzer."""

import asyncio
import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console

from .checkers import (
    DescriptionChecker,
    SecurityChecker,
    TokenEfficiencyChecker,
)
from .dataset_generator import DatasetGenerationError, DatasetGenerator
from .langsmith_uploader import LangSmithUploadError, upload_dataset_to_langsmith
from .mcp_client import MCPClient
from .npx_launcher import is_npx_command
from .reports import ReportFormatter
from .tool_utils import fetch_tools_for_dataset, load_tools_from_file

console = Console()
app = typer.Typer(
    name="mcp-doctor",
    help="🩺 Diagnostic tool for MCP servers - analyze agent-friendliness, debug issues, and ensure best practices compliance",
)


class CheckType(str, Enum):
    descriptions = "descriptions"
    token_efficiency = "token_efficiency"
    security = "security"
    all = "all"


class OutputFormat(str, Enum):
    table = "table"
    json = "json"
    yaml = "yaml"


@app.command()
def analyze(
    target: str = typer.Option(
        ...,
        help="MCP server URL (e.g., http://localhost:8000/mcp) or NPX command (e.g., 'npx firecrawl-mcp')",
    ),
    check: CheckType = typer.Option(
        CheckType.descriptions,
        help="Type of analysis to run: descriptions, token_efficiency, security, or all",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table, help="Output format for results"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output and suggestions"
    ),
    timeout: int = typer.Option(30, help="Request timeout in seconds"),
    env_vars: Optional[str] = typer.Option(
        None,
        "--env-vars",
        help='Environment variables for NPX command (JSON format: \'{"API_KEY": "value"}\')',
    ),
    working_dir: Optional[str] = typer.Option(
        None, "--working-dir", help="Working directory for NPX command"
    ),
    no_env_logging: bool = typer.Option(
        False,
        "--no-env-logging",
        help="Disable environment variable logging for security",
    ),
) -> None:
    """
    Diagnose an MCP server for agent-friendliness and best practices compliance.

    MCP Doctor performs comprehensive health checks on MCP servers to ensure
    they follow Anthropic's recommendations for AI agent integration.

    Examples:

      mcp-doctor analyze --target http://localhost:8000/mcp


      mcp-doctor analyze --target "npx firecrawl-mcp"


      mcp-doctor analyze --target "export FIRECRAWL_API_KEY=abc123 && npx firecrawl-mcp"


      mcp-doctor analyze --target "npx firecrawl-mcp" --env-vars '{"FIRECRAWL_API_KEY": "abc123"}'
    """
    is_npx = is_npx_command(target)

    console.print("\n🩺 [bold blue]MCP Doctor - Server Diagnosis[/bold blue]")
    if is_npx:
        console.print(f"NPX Command: [cyan]{target}[/cyan]")
    else:
        console.print(f"Server URL: [cyan]{target}[/cyan]")
    console.print(f"Check Type: [yellow]{check.value}[/yellow]\n")

    try:

        npx_kwargs = {}
        if env_vars:
            import json

            try:
                npx_kwargs["env_vars"] = json.loads(env_vars)
            except json.JSONDecodeError as e:
                console.print(f"[red]❌ Invalid JSON in env-vars: {e}[/red]")
                raise typer.Exit(1)

        if working_dir:
            npx_kwargs["working_dir"] = working_dir

        if no_env_logging:
            npx_kwargs["log_env_vars"] = False

        result = asyncio.run(
            _run_analysis(
                target,
                check,
                timeout,
                verbose,
                npx_kwargs,
            )
        )

        formatter = ReportFormatter(output_format.value)
        formatter.display_results(result, verbose)

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")
        raise typer.Exit(1)


async def _run_analysis(
    target: str,
    check: CheckType,
    timeout: int,
    verbose: bool,
    npx_kwargs: Optional[dict] = None,
) -> dict:
    """Run the actual analysis logic."""

    if npx_kwargs is None:
        npx_kwargs = {}

    client = MCPClient(target, timeout=timeout, **npx_kwargs)

    is_npx = is_npx_command(target)

    if is_npx:
        with console.status("[bold green]Launching NPX server..."):

            server_info = await client.get_server_info()
            tools = await client.get_tools()

        actual_url = client.get_server_url()
        console.print(f"✅ NPX server launched at [cyan]{actual_url}[/cyan]")
    else:
        with console.status("[bold green]Connecting to MCP server..."):

            server_info = await client.get_server_info()
            tools = await client.get_tools()

        actual_url = target

    console.print(f"✅ Connected! Found [bold]{len(tools)}[/bold] tools\n")

    results: Dict[str, Any] = {
        "server_target": target,
        "server_url": actual_url,
        "server_info": server_info,
        "tools_count": len(tools),
        "is_npx_server": is_npx,
        "checks": {},
    }

    try:

        if check in {CheckType.descriptions, CheckType.all}:
            with console.status("[bold green]Analyzing tool descriptions..."):
                checker = DescriptionChecker()
                description_results = checker.analyze_tool_descriptions(tools)
                results["checks"]["descriptions"] = description_results

        if check in {CheckType.token_efficiency, CheckType.all}:
            with console.status("[bold green]Analyzing token efficiency..."):
                efficiency_checker = TokenEfficiencyChecker()
                efficiency_results = await efficiency_checker.analyze_token_efficiency(
                    tools, client
                )
                results["checks"]["token_efficiency"] = efficiency_results

        if check in {CheckType.security, CheckType.all}:
            with console.status("[bold green]Running security audit..."):
                security_checker = SecurityChecker(timeout=timeout, verify=False)
                security_results = await security_checker.analyze(actual_url)
                results["checks"]["security"] = security_results

    finally:

        await client.close()

    return results


@app.command()
def generate_dataset(
    target: Optional[str] = typer.Option(
        None,
        help="MCP server URL or NPX command to pull tool metadata from",
    ),
    tools_file: Optional[Path] = typer.Option(
        None,
        help="Path to JSON file describing MCP tools (alternative to --target)",
    ),
    num_tasks: int = typer.Option(
        5, min=1, max=20, help="Number of synthetic tasks to generate"
    ),
    model: Optional[str] = typer.Option(
        None,
        help="Override default model name for the chosen provider",
    ),
    timeout: int = typer.Option(
        30, help="Request timeout in seconds when fetching tools"
    ),
    env_vars: Optional[str] = typer.Option(
        None,
        "--env-vars",
        help='Environment variables for NPX command (JSON format: \'{"API_KEY": "value"}\')',
    ),
    working_dir: Optional[str] = typer.Option(
        None, "--working-dir", help="Working directory for NPX command"
    ),
    no_env_logging: bool = typer.Option(
        False,
        "--no-env-logging",
        help="Disable environment variable logging for security",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Path to save generated dataset as JSON; prints to stdout when omitted",
    ),
    llm_timeout: float = typer.Option(
        60.0,
        "--llm-timeout",
        help="Timeout (seconds) for LLM responses when generating datasets",
    ),
    push_to_langsmith: bool = typer.Option(
        False,
        "--push-to-langsmith",
        help="Upload the generated dataset to LangSmith when an API key is available",
    ),
    langsmith_api_key: Optional[str] = typer.Option(
        None,
        "--langsmith-api-key",
        help="LangSmith API key; defaults to LANGSMITH_API_KEY environment variable",
    ),
    langsmith_dataset_name: Optional[str] = typer.Option(
        None,
        "--langsmith-dataset-name",
        help="Dataset name to create inside LangSmith",
    ),
    langsmith_project: Optional[str] = typer.Option(
        None,
        "--langsmith-project",
        help="Optional LangSmith project to tag in metadata",
    ),
    langsmith_endpoint: Optional[str] = typer.Option(
        None,
        "--langsmith-endpoint",
        help="Custom LangSmith API endpoint (e.g. EU region)",
    ),
    langsmith_description: Optional[str] = typer.Option(
        None,
        "--langsmith-description",
        help="Optional LangSmith dataset description",
    ),
) -> None:
    """Generate synthetic datasets for MCP tool use cases."""

    if bool(target) == bool(tools_file):
        console.print(
            "[red]❌ Provide exactly one of --target or --tools-file to choose tool sources[/red]"
        )
        raise typer.Exit(1)

    try:
        if target:
            npx_kwargs: Dict[str, Any] = {}
            if env_vars:
                try:
                    npx_kwargs["env_vars"] = json.loads(env_vars)
                except json.JSONDecodeError as exc:
                    raise DatasetGenerationError(f"Invalid JSON in env-vars: {exc}")

            if working_dir:
                npx_kwargs["working_dir"] = working_dir

            if no_env_logging:
                npx_kwargs["log_env_vars"] = False

            tools = asyncio.run(fetch_tools_for_dataset(target, timeout, npx_kwargs))
        else:
            assert tools_file is not None  # narrow type for mypy
            tools = load_tools_from_file(tools_file)

        generator = DatasetGenerator(model=model, llm_timeout=llm_timeout)
        dataset = asyncio.run(generator.generate_dataset(tools, num_tasks=num_tasks))

        source_label = target if target else str(tools_file)

        if output:
            output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
            console.print(f"✅ Dataset saved to [cyan]{output}[/cyan]")
        else:
            console.print_json(data=dataset)

        if push_to_langsmith:
            effective_api_key = langsmith_api_key or os.getenv("LANGSMITH_API_KEY")
            if not effective_api_key:
                console.print(
                    "[red]❌ Provide a LangSmith API key via --langsmith-api-key or LANGSMITH_API_KEY[/red]"
                )
                raise typer.Exit(1)

            resolved_dataset_name = langsmith_dataset_name or (
                f"mcp-doctor-" + datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            )
            resolved_description = langsmith_description or (
                f"Synthetic dataset generated by MCP Doctor for {source_label}."
            )

            try:
                dataset_id = upload_dataset_to_langsmith(
                    dataset,
                    resolved_dataset_name,
                    api_key=effective_api_key,
                    endpoint=langsmith_endpoint,
                    project_name=langsmith_project,
                    description=resolved_description,
                )
            except LangSmithUploadError as exc:
                console.print(f"[red]❌ LangSmith upload failed: {exc}[/red]")
                raise typer.Exit(1)

            console.print(
                f"✅ Dataset uploaded to LangSmith as [cyan]{resolved_dataset_name}[/cyan]"
            )
            if langsmith_project:
                console.print(
                    f"🔖 Tagged project: [magenta]{langsmith_project}[/magenta]"
                )
            console.print(f"🆔 Dataset ID: [green]{dataset_id}[/green]")

    except DatasetGenerationError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version and diagnostic capabilities."""
    from . import __description__, __version__

    console.print(f"[bold]🩺 MCP Doctor[/bold] v{__version__}")
    console.print(__description__)
    console.print("\n[bold green]Available Diagnostics:[/bold green]")
    console.print("• 📝 Tool Description Analysis")
    console.print("• 🔢 Token Efficiency Analysis")
    console.print("• 🔮 Schema Validation (coming soon)")
    console.print("• ⚡ Performance Analysis (coming soon)")
    console.print("• 🔒 Security Audit (coming soon)")


if __name__ == "__main__":
    app()
