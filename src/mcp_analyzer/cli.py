"""Main CLI interface for MCP Analyzer."""

import asyncio
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _load_env_file(path: Path) -> Dict[str, str]:
    """Parse simple .env style files into a dictionary."""

    if not path.exists():
        raise FileNotFoundError(path)

    env_vars: Dict[str, str] = {}
    for index, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            raise ValueError(f"Invalid env entry on line {index}: {raw_line!r}")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        env_vars[key] = value

    return env_vars


def _load_and_apply_env_file(
    env_file: Optional[Path], console: Console
) -> Dict[str, str]:
    """Load .env file and apply environment variables, returning the loaded variables."""
    env_from_file: Dict[str, str] = {}

    if env_file:
        try:
            env_from_file = _load_env_file(env_file)
        except FileNotFoundError:
            console.print(f"[red]❌ Env file not found: {env_file}[/red]")
            raise typer.Exit(1)
        except ValueError as exc:
            console.print(f"[red]❌ {exc}[/red]")
            raise typer.Exit(1)
        for key, value in env_from_file.items():
            os.environ.setdefault(key, value)
    return env_from_file


def _load_overrides_file(path: Path) -> Dict[str, Any]:
    """Load token-efficiency overrides from JSON or YAML file.

    The expected structure is either:
      - a mapping of tool_name -> params dict
      - or {"tools": {tool_name: params}}
    """
    if not path.exists():
        raise FileNotFoundError(path)

    content = path.read_text(encoding="utf-8")
    data: Any
    if path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency may be optional
            raise RuntimeError(
                "YAML overrides require PyYAML. Install with: pip install PyYAML"
            ) from exc
        data = yaml.safe_load(content)

    if not isinstance(data, dict):
        raise ValueError("Overrides file must contain a mapping/dict at top level")

    tools_block = data.get("tools") if "tools" in data else data
    if not isinstance(tools_block, dict):
        raise ValueError("Overrides must be a mapping of tool names to parameter dicts")

    # Normalize values to dicts
    normalized: Dict[str, Any] = {}
    for key, value in tools_block.items():
        if not isinstance(value, dict):
            raise ValueError(f"Override for '{key}' must be an object/dict of params")
        normalized[str(key)] = value

    return normalized


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
    show_tool_outputs: bool = typer.Option(
        False,
        "--show-tool-outputs",
        help="Print tool call responses during token efficiency analysis",
    ),
    timeout: int = typer.Option(30, help="Request timeout in seconds"),
    env_vars: Optional[str] = typer.Option(
        None,
        "--env-vars",
        help='Environment variables for NPX command (JSON format: \'{"API_KEY": "value"}\')',
    ),
    env_file: Optional[Path] = typer.Option(
        None,
        "--env-file",
        help="Path to a .env file whose values should be injected when running the command",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key to send as 'x-api-key' header when connecting to HTTP/SSE MCP servers",
    ),
    headers_json: Optional[str] = typer.Option(
        None,
        "--headers",
        help='Additional HTTP headers as JSON object (e.g., \'{"Authorization": "Bearer ..."}\')',
    ),
    header: List[str] = typer.Option(
        [],
        "--header",
        "-H",
        help="Additional HTTP header (repeatable). Format 'Name: Value' or 'Name=Value'",
    ),
    working_dir: Optional[str] = typer.Option(
        None, "--working-dir", help="Working directory for NPX command"
    ),
    no_env_logging: bool = typer.Option(
        False,
        "--no-env-logging",
        help="Disable environment variable logging for security",
    ),
    export_html: Optional[Path] = typer.Option(
        None,
        "--export-html",
        help="Path to save the analysis report as HTML (preserves styling)",
    ),
    overrides: Optional[Path] = typer.Option(
        None,
        "--overrides",
        help="Path to JSON or YAML file with tool parameter overrides for token efficiency checks",
    ),
    oauth: bool = typer.Option(
        False,
        "--oauth",
        help="Enable OAuth 2.0 authentication (opens browser for login). For SSE/HTTP servers only.",
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
        env_from_file = _load_and_apply_env_file(env_file, console)

        npx_kwargs: Dict[str, Any] = {}
        if env_from_file:
            npx_kwargs["env_vars"] = dict(env_from_file)
        if env_vars:
            try:
                env_payload = json.loads(env_vars)
            except json.JSONDecodeError as e:
                console.print(f"[red]❌ Invalid JSON in env-vars: {e}[/red]")
                raise typer.Exit(1)
            combined = npx_kwargs.get("env_vars", {}).copy()
            combined.update(env_payload)
            npx_kwargs["env_vars"] = combined

        if working_dir:
            npx_kwargs["working_dir"] = working_dir

        if no_env_logging:
            npx_kwargs["log_env_vars"] = False

        # Build headers from options
        headers_opt: Dict[str, str] = {}
        if headers_json:
            try:
                parsed = json.loads(headers_json)
                if not isinstance(parsed, dict):
                    raise ValueError(
                        "--headers must be a JSON object mapping header names to values"
                    )
                # Convert all values to strings for httpx
                headers_opt.update({str(k): str(v) for k, v in parsed.items()})
            except json.JSONDecodeError as exc:
                console.print(f"[red]❌ Invalid JSON in --headers: {exc}[/red]")
                raise typer.Exit(1)
            except ValueError as exc:
                console.print(f"[red]❌ {exc}[/red]")
                raise typer.Exit(1)

        # Parse repeated --header options
        for hv in header:
            raw = hv.strip()
            if not raw:
                continue
            key: Optional[str] = None
            value: Optional[str] = None
            if ":" in raw:
                key, value = raw.split(":", 1)
            elif "=" in raw:
                key, value = raw.split("=", 1)
            else:
                console.print(
                    f"[yellow]⚠️ Ignoring malformed --header entry (use 'Name: Value' or 'Name=Value'): {hv!r}[/yellow]"
                )
                continue
            key = key.strip()
            value = value.strip()
            if not key:
                console.print(
                    f"[yellow]⚠️ Ignoring --header with empty name: {hv!r}[/yellow]"
                )
                continue
            headers_opt[key] = value

        # Convenience: --api-key populates x-api-key if not overridden explicitly
        if api_key and "x-api-key" not in {
            k.lower(): v for k, v in headers_opt.items()
        }:
            headers_opt["x-api-key"] = api_key

        # Load overrides file if provided
        loaded_overrides: Optional[Dict[str, Any]] = None
        if overrides:
            try:
                loaded_overrides = _load_overrides_file(overrides)
            except Exception as exc:
                console.print(f"[red]❌ Failed to load overrides: {exc}[/red]")
                raise typer.Exit(1)

        result = asyncio.run(
            _run_analysis(
                target,
                check,
                timeout,
                verbose,
                show_tool_outputs,
                headers_opt if headers_opt else None,
                loaded_overrides,
                npx_kwargs,
                oauth,
            )
        )

        formatter = ReportFormatter(output_format.value)
        formatter.display_results(result, verbose)

        if export_html:
            try:
                formatter.export_to_html(result, verbose, export_html)
                console.print(f"🌐 HTML report saved to [cyan]{export_html}[/cyan]")
            except Exception as exc:
                console.print(f"[red]❌ Failed to export HTML report: {exc}[/red]")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")
        raise typer.Exit(1)


async def _perform_checks(
    check: CheckType,
    tools: List[Any],
    client: Any,
    target: str,
    actual_url: str,
    is_npx: bool,
    overrides: Optional[Dict[str, Any]],
    show_tool_outputs: bool,
    timeout: int,
    npx_kwargs: dict,
) -> dict:
    """Perform the actual analysis checks."""
    server_info = await client.get_server_info()
    
    results: Dict[str, Any] = {
        "server_target": target,
        "server_url": actual_url,
        "server_info": server_info,
        "tools_count": len(tools),
        "is_npx_server": is_npx,
        "checks": {},
    }

    if check in {CheckType.descriptions, CheckType.all}:
        with console.status("[bold green]Analyzing tool descriptions..."):
            checker = DescriptionChecker()
            description_results = checker.analyze_tool_descriptions(tools)
            results["checks"]["descriptions"] = description_results

    if check in {CheckType.token_efficiency, CheckType.all}:
        with console.status("[bold green]Analyzing token efficiency..."):
            efficiency_checker = TokenEfficiencyChecker(overrides=overrides)
            efficiency_checker.show_tool_outputs = bool(show_tool_outputs)
            efficiency_results = await efficiency_checker.analyze_token_efficiency(
                tools, client
            )
            results["checks"]["token_efficiency"] = efficiency_results

    if check in {CheckType.security, CheckType.all}:
        with console.status("[bold green]Running security audit..."):
            security_checker = SecurityChecker(
                timeout=timeout,
                verify=False,
                env_vars=npx_kwargs.get("env_vars"),
            )
            security_results = await security_checker.analyze(actual_url)
            results["checks"]["security"] = security_results

    return results


async def _run_analysis(
    target: str,
    check: CheckType,
    timeout: int,
    verbose: bool,
    show_tool_outputs: bool = False,
    headers: Optional[Dict[str, str]] = None,
    overrides: Optional[Dict[str, Any]] = None,
    npx_kwargs: Optional[dict] = None,
    oauth: bool = False,
) -> dict:
    """Run the actual analysis logic."""

    if npx_kwargs is None:
        npx_kwargs = {}

    is_npx = is_npx_command(target)

    if oauth and not is_npx:
        from mcp_analyzer.fastmcp_oauth_client import FastMCPOAuthClient
        
        async with FastMCPOAuthClient(target, timeout=timeout) as client:
            with console.status("[bold green]Connecting to MCP server with OAuth..."):
                server_info = await client.get_server_info()
                tools = await client.get_tools()

            actual_url = target
            console.print(f"✅ Connected! Found [bold]{len(tools)}[/bold] tools\n")

            return await _perform_checks(
                check, tools, client, target, actual_url, False, overrides, show_tool_outputs, timeout, npx_kwargs
            )
    else:
        if oauth and is_npx:
            console.print(
                "[yellow]⚠️  OAuth is only supported for HTTP/SSE servers. "
                "Ignoring --oauth flag for NPX command.[/yellow]\n"
            )
        client = MCPClient(target, timeout=timeout, headers=headers, **npx_kwargs)

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

    try:
        return await _perform_checks(
            check, tools, client, target, actual_url, is_npx, overrides, show_tool_outputs, timeout, npx_kwargs
        )
    finally:
        await client.close()


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
    env_file: Optional[Path] = typer.Option(
        None,
        "--env-file",
        help="Path to a .env file whose values should be injected when running the command",
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
        env_from_file = _load_and_apply_env_file(env_file, console)

        if target:
            npx_kwargs: Dict[str, Any] = {}
            if env_from_file:
                npx_kwargs["env_vars"] = dict(env_from_file)
            if env_vars:
                try:
                    env_payload = json.loads(env_vars)
                except json.JSONDecodeError as exc:
                    raise DatasetGenerationError(f"Invalid JSON in env-vars: {exc}")
                merged_env = npx_kwargs.get("env_vars", {}).copy()
                merged_env.update(env_payload)
                npx_kwargs["env_vars"] = merged_env

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
                "mcp-doctor-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            )
            resolved_description = langsmith_description or (
                f"Synthetic dataset generated by MCP Doctor for {source_label}."
            )

            try:
                dataset_id, reused_existing = upload_dataset_to_langsmith(
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

            if reused_existing:
                console.print(
                    "♻️ Reused existing LangSmith dataset "
                    f"[cyan]{resolved_dataset_name}[/cyan]"
                )
            else:
                console.print(
                    "✅ Dataset uploaded to LangSmith as "
                    f"[cyan]{resolved_dataset_name}[/cyan]"
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
def evaluate_dataset() -> None:
    """(Temporarily disabled)"""

    console.print(
        "[yellow]⚠️ Evaluation functionality has been temporarily disabled. "
        "Stay tuned for future updates.[/yellow]"
    )
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
