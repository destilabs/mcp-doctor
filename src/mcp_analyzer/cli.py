"""Main CLI interface for MCP Analyzer."""

import asyncio
from enum import Enum
from typing import Optional

import typer
from rich.console import Console

from .mcp_client import MCPClient
from .checkers.descriptions import DescriptionChecker
from .reports import ReportFormatter
from .npx_launcher import is_npx_command

console = Console()
app = typer.Typer(
    name="mcp-doctor",
    help="🩺 Diagnostic tool for MCP servers - analyze agent-friendliness, debug issues, and ensure best practices compliance"
)


class CheckType(str, Enum):
    descriptions = "descriptions"
    schemas = "schemas"
    performance = "performance"
    all = "all"


class OutputFormat(str, Enum):
    table = "table"
    json = "json"
    yaml = "yaml"


@app.command()
def analyze(
    target: str = typer.Option(
        ..., 
        help="MCP server URL (e.g., http://localhost:8000/mcp) or NPX command (e.g., 'npx firecrawl-mcp')"
    ),
    check: CheckType = typer.Option(
        CheckType.descriptions, 
        help="Type of analysis to run"
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table, 
        help="Output format for results"
    ),
    verbose: bool = typer.Option(
        False, 
        "--verbose", 
        "-v", 
        help="Show detailed output and suggestions"
    ),
    timeout: int = typer.Option(
        30, 
        help="Request timeout in seconds"
    ),
    env_vars: Optional[str] = typer.Option(
        None,
        "--env-vars",
        help="Environment variables for NPX command (JSON format: '{\"API_KEY\": \"value\"}')"
    ),
    working_dir: Optional[str] = typer.Option(
        None,
        "--working-dir",
        help="Working directory for NPX command"
    ),
) -> None:
    """
    Diagnose an MCP server for agent-friendliness and best practices compliance.
    
    MCP Doctor performs comprehensive health checks on MCP servers to ensure
    they follow Anthropic's recommendations for AI agent integration.
    
    Examples:
      # Diagnose HTTP server
      mcp-doctor analyze --target http://localhost:8000/mcp
      
      # Diagnose NPX server
      mcp-doctor analyze --target "npx firecrawl-mcp"
      
      # Diagnose NPX server with environment variables
      mcp-doctor analyze --target "export FIRECRAWL_API_KEY=abc123 && npx firecrawl-mcp"
      
      # Diagnose NPX server with JSON env vars
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
        # Prepare NPX arguments
        npx_kwargs = {}
        if env_vars:
            import json
            try:
                npx_kwargs['env_vars'] = json.loads(env_vars)
            except json.JSONDecodeError as e:
                console.print(f"[red]❌ Invalid JSON in env-vars: {e}[/red]")
                raise typer.Exit(1)
        
        if working_dir:
            npx_kwargs['working_dir'] = working_dir
        
        # Run the analysis
        result = asyncio.run(_run_analysis(target, check, timeout, verbose, npx_kwargs))
        
        # Format and display results
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
    npx_kwargs: dict = None
) -> dict:
    """Run the actual analysis logic."""
    
    if npx_kwargs is None:
        npx_kwargs = {}
    
    # Initialize MCP client
    client = MCPClient(target, timeout=timeout, **npx_kwargs)
    
    is_npx = is_npx_command(target)
    
    if is_npx:
        with console.status("[bold green]Launching NPX server..."):
            # This will trigger server launch in the client
            server_info = await client.get_server_info()
            tools = await client.get_tools()
        
        actual_url = client.get_server_url()
        console.print(f"✅ NPX server launched at [cyan]{actual_url}[/cyan]")
    else:
        with console.status("[bold green]Connecting to MCP server..."):
            # Test connection and get tools
            server_info = await client.get_server_info()
            tools = await client.get_tools()
        
        actual_url = target
    
    console.print(f"✅ Connected! Found [bold]{len(tools)}[/bold] tools\n")
    
    results = {
        "server_target": target,
        "server_url": actual_url,
        "server_info": server_info,
        "tools_count": len(tools),
        "is_npx_server": is_npx,
        "checks": {}
    }
    
    try:
        # Run specific checks based on type
        if check == CheckType.descriptions or check == CheckType.all:
            with console.status("[bold green]Analyzing tool descriptions..."):
                checker = DescriptionChecker()
                description_results = checker.analyze_tool_descriptions(tools)
                results["checks"]["descriptions"] = description_results
        
        # Future: Add other check types here
        if check == CheckType.schemas or check == CheckType.all:
            results["checks"]["schemas"] = {"message": "Schema analysis not yet implemented"}
        
        if check == CheckType.performance or check == CheckType.all:
            results["checks"]["performance"] = {"message": "Performance analysis not yet implemented"}
    
    finally:
        # Clean up NPX server if needed
        await client.close()
    
    return results


@app.command()
def version() -> None:
    """Show version and diagnostic capabilities."""
    from . import __version__, __description__
    console.print(f"[bold]🩺 MCP Doctor[/bold] v{__version__}")
    console.print(__description__)
    console.print("\n[bold green]Available Diagnostics:[/bold green]")
    console.print("• 📝 Tool Description Analysis")
    console.print("• 🔮 Schema Validation (coming soon)")
    console.print("• ⚡ Performance Analysis (coming soon)")
    console.print("• 🔒 Security Audit (coming soon)")




if __name__ == "__main__":
    app()
