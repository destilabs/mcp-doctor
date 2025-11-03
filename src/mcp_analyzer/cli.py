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
    llm_model: str = typer.Option(
        "gpt-4o-mini",
        "--llm-model",
        help="LLM model for parameter generation when validation fails (gpt-4o-mini, gpt-4o, claude-sonnet-4-20250514)",
    ),
    cache_tool_calls: bool = typer.Option(
        True,
        "--cache-tool-calls/--no-cache-tool-calls",
        help="Cache successful tool calls for future reference (stored in ~/.mcp-analyzer/tool-call-cache)",
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
    # For type compatibility across OAuth and non-OAuth branches
    from typing import Any as _Any

    client: _Any

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
                llm_model,
                cache_tool_calls,
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
    llm_model: str = "gpt-4o-mini",
    cache_tool_calls: bool = True,
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
            efficiency_checker = TokenEfficiencyChecker(
                overrides=overrides,
                llm_model=llm_model,
                cache_enabled=cache_tool_calls,
                server_url=actual_url,
            )
            efficiency_checker.show_tool_outputs = bool(show_tool_outputs)
            efficiency_results = await efficiency_checker.analyze_token_efficiency(
                tools, client
            )
            results["checks"]["token_efficiency"] = efficiency_results

            if cache_tool_calls and efficiency_checker.cache:
                cache_stats = efficiency_checker.cache.get_cache_stats()
                if cache_stats.get("total_calls", 0) > 0:
                    console.print(
                        f"\n💾 Cached {cache_stats.get('total_calls', 0)} successful tool calls "
                        f"to [cyan]{cache_stats.get('cache_path', 'cache')}[/cyan]"
                    )

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
    llm_model: str = "gpt-4o-mini",
    cache_tool_calls: bool = True,
) -> dict:
    """Run the actual analysis logic."""

    if npx_kwargs is None:
        npx_kwargs = {}

    is_npx = is_npx_command(target)

    if oauth and not is_npx:
        from mcp_analyzer.fastmcp_oauth_client import FastMCPOAuthClient

        async with FastMCPOAuthClient(target, timeout=timeout) as oauth_client:
            with console.status("[bold green]Connecting to MCP server with OAuth..."):
                await oauth_client.get_server_info()
                tools = await oauth_client.get_tools()

            actual_url = target
            console.print(f"✅ Connected! Found [bold]{len(tools)}[/bold] tools\n")

            return await _perform_checks(
                check,
                tools,
                oauth_client,
                target,
                actual_url,
                False,
                overrides,
                show_tool_outputs,
                timeout,
                npx_kwargs,
                llm_model,
                cache_tool_calls,
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
                await client.get_server_info()
                tools = await client.get_tools()

            actual_url = client.get_server_url()
            console.print(f"✅ NPX server launched at [cyan]{actual_url}[/cyan]")
        else:
            with console.status("[bold green]Connecting to MCP server..."):
                await client.get_server_info()
                tools = await client.get_tools()

            actual_url = target

    console.print(f"✅ Connected! Found [bold]{len(tools)}[/bold] tools\n")

    try:
        return await _perform_checks(
            check,
            tools,
            client,
            target,
            actual_url,
            is_npx,
            overrides,
            show_tool_outputs,
            timeout,
            npx_kwargs,
            llm_model,
            cache_tool_calls,
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
        5, min=1, max=200, help="Number of synthetic tasks to generate"
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

            headers_opt: Dict[str, str] = {}
            if headers_json:
                try:
                    parsed = json.loads(headers_json)
                    if not isinstance(parsed, dict):
                        raise ValueError(
                            "--headers must be a JSON object mapping header names to values"
                        )
                    headers_opt.update({str(k): str(v) for k, v in parsed.items()})
                except json.JSONDecodeError as exc:
                    raise DatasetGenerationError(f"Invalid JSON in --headers: {exc}")
                except ValueError as exc:
                    raise DatasetGenerationError(str(exc))

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

            lower_header_keys = {k.lower() for k in headers_opt}
            if api_key and "x-api-key" not in lower_header_keys:
                headers_opt["x-api-key"] = api_key

            headers_payload = headers_opt if headers_opt else None

            tools = asyncio.run(
                fetch_tools_for_dataset(
                    target,
                    timeout,
                    npx_kwargs,
                    headers=headers_payload,
                )
            )
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
def run_dataset(
    dataset: Path = typer.Option(
        ...,
        help="Path to dataset JSON file",
    ),
    mcp_target: str = typer.Option(
        ...,
        help="MCP server URL or NPX command",
    ),
    output: Path = typer.Option(
        ...,
        help="Path to save actual results JSON",
    ),
    provider: str = typer.Option(
        "openai",
        help="LLM provider to use (openai or anthropic)",
    ),
    model: Optional[str] = typer.Option(
        None,
        help="Model name (defaults: gpt-4o for OpenAI, claude-sonnet-4-20250514 for Anthropic)",
    ),
    timeout: int = typer.Option(30, help="Request timeout in seconds"),
    env_vars: Optional[str] = typer.Option(
        None,
        "--env-vars",
        help='Environment variables as JSON (e.g., \'{"API_KEY": "value"}\')',
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
) -> None:
    """Run dataset prompts through an LLM with actual MCP tools and capture results.
    
    This command connects to an MCP server, retrieves its tools, runs each dataset
    prompt through an LLM with those tools available, and captures which tools the
    LLM actually calls along with token usage and other metadata.
    
    Examples:
    
      # With .env file containing API keys
      mcp-doctor run-dataset \\
        --dataset dataset.json \\
        --mcp-target "https://api.example.com/mcp" \\
        --output results.json
      
      # With explicit API keys
      mcp-doctor run-dataset \\
        --dataset dataset.json \\
        --mcp-target "https://api.example.com/mcp" \\
        --output results.json \\
        --api-key "your-mcp-key" \\
        --provider anthropic
      
      # With NPX command
      mcp-doctor run-dataset \\
        --dataset dataset.json \\
        --mcp-target "npx @modelcontextprotocol/server-filesystem /tmp" \\
        --output results.json
    """
    try:
        from dotenv import load_dotenv
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
    except ImportError:
        pass
    
    if provider not in ["openai", "anthropic"]:
        console.print(f"[red]❌ Invalid provider: {provider}. Use 'openai' or 'anthropic'[/red]")
        raise typer.Exit(1)
    
    console.print("\n🚀 [bold blue]Run Dataset with MCP Tools[/bold blue]")
    console.print(f"Dataset: [cyan]{dataset}[/cyan]")
    console.print(f"MCP Target: [cyan]{mcp_target}[/cyan]")
    console.print(f"Provider: [yellow]{provider}[/yellow]\n")
    
    env_from_file = _load_and_apply_env_file(env_file, console) if env_file else {}
    
    npx_kwargs: Dict[str, Any] = {}
    headers_opt: Dict[str, str] = {}
    
    if env_from_file:
        npx_kwargs["env_vars"] = dict(env_from_file)
    
    if env_vars:
        try:
            env_payload = json.loads(env_vars)
        except json.JSONDecodeError as exc:
            console.print(f"[red]❌ Invalid JSON in env-vars: {exc}[/red]")
            raise typer.Exit(1)
        merged_env = npx_kwargs.get("env_vars", {}).copy()
        merged_env.update(env_payload)
        npx_kwargs["env_vars"] = merged_env
    
    if headers_json:
        try:
            parsed = json.loads(headers_json)
            if not isinstance(parsed, dict):
                raise ValueError("--headers must be a JSON object")
            headers_opt.update({str(k): str(v) for k, v in parsed.items()})
        except (json.JSONDecodeError, ValueError) as exc:
            console.print(f"[red]❌ Invalid JSON in --headers: {exc}[/red]")
            raise typer.Exit(1)
    
    for hv in header:
        raw = hv.strip()
        if not raw:
            continue
        if ":" in raw:
            key, value = raw.split(":", 1)
        elif "=" in raw:
            key, value = raw.split("=", 1)
        else:
            console.print(f"[yellow]⚠️  Ignoring malformed header: {hv!r}[/yellow]")
            continue
        headers_opt[key.strip()] = value.strip()
    
    if api_key and "x-api-key" not in {k.lower() for k in headers_opt}:
        headers_opt["x-api-key"] = api_key
    
    # Check for API keys in env_vars or environment
    import os
    if "x-api-key" not in headers_opt:
        if npx_kwargs.get("env_vars"):
            for key in ["API_KEY", "AUTHORIZATION"]:
                if key in npx_kwargs["env_vars"]:
                    headers_opt["x-api-key"] = npx_kwargs["env_vars"][key]
                    break
        if "x-api-key" not in headers_opt:
            if os.getenv("API_KEY"):
                headers_opt["x-api-key"] = os.getenv("API_KEY")
    
    if working_dir:
        npx_kwargs["working_dir"] = working_dir
    
    result = asyncio.run(
        _run_dataset_with_llm(
            dataset,
            mcp_target,
            output,
            provider,
            model,
            timeout,
            headers_opt if headers_opt else None,
            npx_kwargs,
        )
    )
    
    if result:
        console.print(f"\n✅ Results saved to [cyan]{output}[/cyan]")
        console.print(f"📊 Processed {len(result)} tasks")
        
        total_tokens = sum(
            r.get("tokens", {}).get("total_tokens", 0) 
            for r in result if isinstance(r, dict)
        )
        if total_tokens > 0:
            console.print(f"🎯 Total tokens used: {total_tokens:,}")


async def _run_dataset_with_llm(
    dataset_path: Path,
    mcp_target: str,
    output_path: Path,
    provider: str,
    model: Optional[str],
    timeout: int,
    headers: Optional[Dict[str, str]],
    npx_kwargs: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Run dataset through LLM with MCP tools."""
    from .mcp_client import MCPClient
    
    console.print(f"[dim]Connecting to MCP server...[/dim]")
    
    client = MCPClient(
        mcp_target,
        timeout=timeout,
        headers=headers,
        **npx_kwargs
    )
    
    try:
        server_info = await client.get_server_info()
        console.print(f"✅ Connected to: [green]{server_info.server_name or 'MCP Server'}[/green]")
        console.print(f"[dim]Transport: {client._transport}[/dim]")
        
        tools = await client.get_tools()
        console.print(f"✅ Retrieved {len(tools)} tools from MCP server\n")
        
        with open(dataset_path) as f:
            dataset = json.load(f)
        
        if provider == "openai":
            result = await _run_with_openai(dataset, tools, model, console)
        else:
            result = await _run_with_anthropic(dataset, tools, model, console)
        
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        
        return result
        
    finally:
        await client.close()


async def _run_with_openai(
    dataset: List[Dict[str, Any]],
    tools: List[Any],
    model: Optional[str],
    console: Console,
) -> List[Dict[str, Any]]:
    """Run dataset through OpenAI."""
    try:
        from openai import OpenAI
    except ImportError:
        console.print("[red]❌ OpenAI SDK not installed. Run: pip install openai[/red]")
        raise typer.Exit(1)
    
    model = model or "gpt-4o"
    console.print(f"🤖 Running {len(dataset)} prompts through [cyan]{model}[/cyan]\n")
    
    openai_tools = _convert_tools_to_openai(tools)
    client = OpenAI()
    all_results = []
    
    for idx, task in enumerate(dataset):
        prompt = task["prompt"]
        console.print(f"[dim]Task {idx + 1}/{len(dataset)}:[/dim] {prompt[:60]}...")
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            tools=openai_tools,
        )
        
        tool_calls = []
        tool_call_trace = []
        message = response.choices[0].message
        
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "tool_name": tc.function.name,
                    "arguments": [json.loads(tc.function.arguments)],
                })
                tool_call_trace.append({
                    "id": tc.id,
                    "tool_name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })
                console.print(f"  [green]→ Called:[/green] {tc.function.name}")
        else:
            console.print("  [yellow]→ No tools called[/yellow]")
        
        usage = response.usage
        task_result = {
            "query": prompt,
            "tool_calls": tool_calls,
            "tool_call_trace": tool_call_trace,
            "tokens": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
            "model": model,
            "finish_reason": response.choices[0].finish_reason,
        }
        
        all_results.append(task_result)
    
    return all_results


async def _run_with_anthropic(
    dataset: List[Dict[str, Any]],
    tools: List[Any],
    model: Optional[str],
    console: Console,
) -> List[Dict[str, Any]]:
    """Run dataset through Anthropic."""
    try:
        from anthropic import Anthropic
    except ImportError:
        console.print("[red]❌ Anthropic SDK not installed. Run: pip install anthropic[/red]")
        raise typer.Exit(1)
    
    model = model or "claude-sonnet-4-20250514"
    console.print(f"🤖 Running {len(dataset)} prompts through [cyan]{model}[/cyan]\n")
    
    anthropic_tools = _convert_tools_to_anthropic(tools)
    client = Anthropic()
    all_results = []
    
    for idx, task in enumerate(dataset):
        prompt = task["prompt"]
        console.print(f"[dim]Task {idx + 1}/{len(dataset)}:[/dim] {prompt[:60]}...")
        
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            tools=anthropic_tools,
        )
        
        tool_calls = []
        tool_call_trace = []
        
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "tool_name": block.name,
                    "arguments": [block.input],
                })
                tool_call_trace.append({
                    "id": block.id,
                    "tool_name": block.name,
                    "arguments": block.input,
                })
                console.print(f"  [green]→ Called:[/green] {block.name}")
        
        if not tool_calls:
            console.print("  [yellow]→ No tools called[/yellow]")
        
        task_result = {
            "query": prompt,
            "tool_calls": tool_calls,
            "tool_call_trace": tool_call_trace,
            "tokens": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            "model": model,
            "stop_reason": response.stop_reason,
        }
        
        all_results.append(task_result)
    
    return all_results


def _convert_tools_to_openai(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    """Convert MCP tools to OpenAI format."""
    openai_tools = []
    for tool in mcp_tools:
        parameters = tool.parameters if hasattr(tool, 'parameters') else tool.input_schema
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "No description",
                "parameters": parameters or {"type": "object", "properties": {}},
            }
        })
    return openai_tools


def _convert_tools_to_anthropic(mcp_tools: List[Any]) -> List[Dict[str, Any]]:
    """Convert MCP tools to Anthropic format."""
    anthropic_tools = []
    for tool in mcp_tools:
        parameters = tool.parameters if hasattr(tool, 'parameters') else tool.input_schema
        anthropic_tools.append({
            "name": tool.name,
            "description": tool.description or "No description",
            "input_schema": parameters or {"type": "object", "properties": {}},
        })
    return anthropic_tools


@app.command()
def evaluate_dataset(
    dataset: Path = typer.Option(
        ...,
        help="Path to dataset JSON file to evaluate",
    ),
    actual_results: Path = typer.Option(
        ...,
        help="Path to JSON file containing actual tool call results",
    ),
    evaluate_params: bool = typer.Option(
        True,
        "--evaluate-params/--no-evaluate-params",
        help="Include parameter accuracy in evaluation",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table, help="Output format for results"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Path to save evaluation report as JSON; prints to stdout when omitted",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output for each task"
    ),
) -> None:
    """Evaluate tool calling accuracy for a dataset.
    
    This command compares expected tool calls in a dataset against actual LLM results
    to measure tool calling accuracy.
    
    Examples:
    
      mcp-doctor evaluate-dataset --dataset dataset.json --actual-results results.json
      
      mcp-doctor evaluate-dataset --dataset dataset.json --actual-results results.json --no-evaluate-params
    """
    from .dataset_evaluator import (
        EvaluationError,
        evaluate_dataset as run_evaluation,
        load_dataset,
    )

    console.print("\n📊 [bold blue]Dataset Evaluation[/bold blue]")
    console.print(f"Dataset: [cyan]{dataset}[/cyan]")
    console.print(f"Actual Results: [cyan]{actual_results}[/cyan]")
    console.print(
        f"Parameter Evaluation: [yellow]{'Enabled' if evaluate_params else 'Disabled'}[/yellow]\n"
    )

    try:
        dataset_data = load_dataset(dataset)
        
        if not actual_results.exists():
            console.print(f"[red]❌ Results file not found: {actual_results}[/red]")
            raise typer.Exit(1)
        
        try:
            actual_data = json.loads(actual_results.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            console.print(f"[red]❌ Invalid JSON in results file: {exc}[/red]")
            raise typer.Exit(1)
        
        if not isinstance(actual_data, list):
            console.print("[red]❌ Results file must be a JSON array[/red]")
            raise typer.Exit(1)

        report = run_evaluation(
            dataset_data,
            actual_data,
            evaluate_params=evaluate_params,
            dataset_path=str(dataset),
        )

        if output_format == OutputFormat.json:
            if output:
                output.write_text(
                    json.dumps(report.to_dict(), indent=2), encoding="utf-8"
                )
                console.print(f"✅ Report saved to [cyan]{output}[/cyan]")
            else:
                console.print_json(data=report.to_dict())
        else:
            from rich.table import Table

            summary_table = Table(title="Evaluation Summary", show_header=True)
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", style="green")

            summary_table.add_row("Total Tasks", str(report.total_tasks))
            summary_table.add_row(
                "Overall Tool Accuracy", f"{report.overall_tool_accuracy:.2%}"
            )
            summary_table.add_row(
                "Overall Tool Order Accuracy",
                f"{report.overall_tool_order_accuracy:.2%}",
            )
            if report.overall_param_accuracy is not None:
                summary_table.add_row(
                    "Overall Parameter Accuracy",
                    f"{report.overall_param_accuracy:.2%}",
                )
            summary_table.add_row("Perfect Matches", str(report.perfect_matches))
            summary_table.add_row(
                "Tool-Only Matches", str(report.tool_only_matches)
            )

            console.print(summary_table)

            if verbose:
                console.print("\n[bold]Task-by-Task Results:[/bold]\n")
                for idx, task_eval in enumerate(report.task_evaluations):
                    task_info = actual_data[idx] if isinstance(actual_data[idx], dict) else {}
                    
                    title = f"Task {task_eval.task_index}: {task_eval.prompt[:60]}..."
                    if task_info.get("tokens"):
                        tokens = task_info["tokens"]
                        total = tokens.get("total_tokens", 0)
                        title += f" [{total} tokens]"
                    
                    task_table = Table(
                        title=title,
                        show_header=True,
                    )
                    task_table.add_column("Position", style="cyan")
                    task_table.add_column("Expected Tool", style="yellow")
                    task_table.add_column("Actual Tool", style="magenta")
                    task_table.add_column("Tool Match", style="green")
                    if evaluate_params:
                        task_table.add_column("Params Match", style="blue")

                    for match_idx, match in enumerate(task_eval.tool_matches):
                        row = [
                            str(match_idx),
                            match.expected_tool,
                            match.actual_tool or "<none>",
                            "✓" if match.tool_match else "✗",
                        ]
                        if evaluate_params:
                            if match.params_match is None:
                                row.append("N/A")
                            else:
                                row.append("✓" if match.params_match else "✗")
                        task_table.add_row(*row)

                    console.print(task_table)
                    
                    metrics_line = (
                        f"  Tool Accuracy: {task_eval.tool_accuracy:.2%}, "
                        f"Order Accuracy: {task_eval.tool_order_accuracy:.2%}"
                    )
                    if task_eval.param_accuracy is not None:
                        metrics_line += f", Param Accuracy: {task_eval.param_accuracy:.2%}"
                    
                    if task_info.get("tokens"):
                        tokens = task_info["tokens"]
                        metrics_line += (
                            f"\n  Tokens: {tokens.get('prompt_tokens') or tokens.get('input_tokens', 0)} input, "
                            f"{tokens.get('completion_tokens') or tokens.get('output_tokens', 0)} output, "
                            f"{tokens.get('total_tokens', 0)} total"
                        )
                    
                    if task_info.get("model"):
                        metrics_line += f"\n  Model: {task_info['model']}"
                    
                    console.print(metrics_line + "\n")

            if output:
                output.write_text(
                    json.dumps(report.to_dict(), indent=2), encoding="utf-8"
                )
                console.print(f"\n✅ Report saved to [cyan]{output}[/cyan]")

    except EvaluationError as exc:
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


@app.command()
def cache_stats(
    server_url: Optional[str] = typer.Option(
        None,
        "--server",
        help="Show cache stats for specific server URL (shows all if not provided)",
    ),
) -> None:
    """Show statistics about cached tool calls."""
    from pathlib import Path

    from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

    cache_root = Path.home() / ".mcp-analyzer" / "tool-call-cache"

    if not cache_root.exists():
        console.print(
            "[yellow]No cache found. Run token efficiency checks with --cache-tool-calls to build cache.[/yellow]"
        )
        return

    if server_url:
        cache = ToolCallCache(server_url)
        stats = cache.get_cache_stats()

        console.print(f"\n[bold]Cache Statistics for {server_url}[/bold]")
        console.print(f"Cache Path: [cyan]{stats['cache_path']}[/cyan]")
        console.print(f"Total Tools: [green]{stats['total_tools']}[/green]")
        console.print(f"Total Cached Calls: [green]{stats['total_calls']}[/green]\n")

        if stats.get("tools"):
            console.print("[bold]Tools:[/bold]")
            for tool_name, tool_data in stats["tools"].items():
                console.print(
                    f"  • [cyan]{tool_name}[/cyan]: {tool_data['total_cached_calls']} calls"
                )
                scenarios = tool_data.get("scenarios", {})
                if scenarios:
                    for scenario, count in scenarios.items():
                        console.print(f"    - {scenario}: {count}")
    else:
        console.print("\n[bold]All Cached Servers:[/bold]\n")

        server_dirs = [d for d in cache_root.iterdir() if d.is_dir()]
        if not server_dirs:
            console.print("[yellow]No cached servers found.[/yellow]")
            return

        for server_dir in server_dirs:
            metadata_file = server_dir / "_metadata.json"
            if metadata_file.exists():
                import json

                try:
                    metadata = json.loads(metadata_file.read_text())
                    server = metadata.get("server_url", server_dir.name)

                    cache = ToolCallCache(server)
                    stats = cache.get_cache_stats()

                    console.print(f"[cyan]{server}[/cyan]")
                    console.print(
                        f"  Tools: {stats['total_tools']}, Calls: {stats['total_calls']}"
                    )
                except Exception:
                    pass


@app.command()
def cache_clear(
    server_url: Optional[str] = typer.Option(
        None,
        "--server",
        help="Clear cache for specific server URL (clears all if not provided)",
    ),
    tool_name: Optional[str] = typer.Option(
        None,
        "--tool",
        help="Clear cache for specific tool only (requires --server)",
    ),
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Clear cached tool calls."""
    import shutil
    from pathlib import Path

    from mcp_analyzer.checkers.tool_call_cache import ToolCallCache

    cache_root = Path.home() / ".mcp-analyzer" / "tool-call-cache"

    if not cache_root.exists():
        console.print("[yellow]No cache found.[/yellow]")
        return

    if tool_name and not server_url:
        console.print("[red]Error: --tool requires --server[/red]")
        raise typer.Exit(1)

    if not confirm:
        if tool_name:
            message = f"Clear cache for tool '{tool_name}' on server '{server_url}'?"
        elif server_url:
            message = f"Clear all cache for server '{server_url}'?"
        else:
            message = "Clear ALL cached tool calls for ALL servers?"

        if not typer.confirm(message):
            console.print("Cancelled.")
            return

    if server_url:
        cache = ToolCallCache(server_url)
        cache.clear_cache(tool_name=tool_name)

        if tool_name:
            console.print(f"[green]✓[/green] Cleared cache for tool: {tool_name}")
        else:
            console.print(f"[green]✓[/green] Cleared cache for server: {server_url}")
    else:
        shutil.rmtree(cache_root)
        cache_root.mkdir(parents=True, exist_ok=True)
        console.print("[green]✓[/green] Cleared all cache")


if __name__ == "__main__":
    app()
