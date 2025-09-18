"""Report formatting and display utilities."""

import json
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .checkers.descriptions import Severity

console = Console()


class ReportFormatter:
    """Formats and displays analysis results."""

    def __init__(self, output_format: str = "table"):
        self.output_format = output_format

    def display_results(self, results: Dict[str, Any], verbose: bool = False) -> None:
        """Display analysis results in the specified format."""

        if self.output_format == "json":
            self._display_json(results)
        elif self.output_format == "yaml":
            self._display_yaml(results)
        else:  # table format
            self._display_table(results, verbose)

    def _display_table(self, results: Dict[str, Any], verbose: bool) -> None:
        """Display results in a rich table format."""

        # Server info header
        server_url = results.get("server_url", "Unknown")
        tools_count = results.get("tools_count", 0)

        console.print(
            Panel(
                f"[bold blue]MCP Server Analysis Report[/bold blue]\n"
                f"Server: [cyan]{server_url}[/cyan]\n"
                f"Tools Found: [yellow]{tools_count}[/yellow]",
                title="📊 Analysis Summary",
            )
        )

        # Process each check type
        checks = results.get("checks", {})

        for check_type, check_results in checks.items():
            if check_type == "descriptions":
                self._display_description_results(check_results, verbose)
            elif check_type == "token_efficiency":
                self._display_token_efficiency_results(check_results, verbose)
            else:
                # For future check types
                console.print(f"\n[yellow]ℹ️  {check_type.title()} Analysis:[/yellow]")
                console.print(f"   {check_results.get('message', 'No results')}")

    def _display_description_results(
        self, results: Dict[str, Any], verbose: bool
    ) -> None:
        """Display description analysis results."""

        issues = results.get("issues", [])
        stats = results.get("statistics", {})
        recommendations = results.get("recommendations", [])

        console.print(f"\n[bold green]📝 AI-Readable Description Analysis[/bold green]")

        # Statistics
        total = stats.get("total_tools", 0)
        passed = stats.get("tools_passed", 0)
        errors = stats.get("errors", 0)
        warnings = stats.get("warnings", 0)
        info_count = stats.get("info", 0)

        # Create statistics table
        stats_table = Table(show_header=True, header_style="bold magenta")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Count", justify="right")
        stats_table.add_column("Percentage", justify="right")

        if total > 0:
            stats_table.add_row("✅ Passed", str(passed), f"{(passed/total)*100:.1f}%")
            stats_table.add_row(
                "⚠️  Warnings",
                str(warnings),
                f"{(warnings/(warnings+errors+info_count) if (warnings+errors+info_count) > 0 else 0)*100:.1f}%",
            )
            stats_table.add_row(
                "❌ Errors",
                str(errors),
                f"{(errors/(warnings+errors+info_count) if (warnings+errors+info_count) > 0 else 0)*100:.1f}%",
            )
            stats_table.add_row(
                "ℹ️  Info",
                str(info_count),
                f"{(info_count/(warnings+errors+info_count) if (warnings+errors+info_count) > 0 else 0)*100:.1f}%",
            )

        console.print(stats_table)

        # Issues table (if any)
        if issues:
            console.print(f"\n[bold red]Issues Found:[/bold red]")

            issues_table = Table(show_header=True, header_style="bold red")
            issues_table.add_column("Tool", style="cyan", min_width=20)
            issues_table.add_column("Severity", justify="center", min_width=8)
            issues_table.add_column("Issue", min_width=30)

            if verbose:
                issues_table.add_column("Suggestion", min_width=40)

            # Sort issues by severity
            severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
            sorted_issues = sorted(
                issues, key=lambda x: (severity_order[x.severity], x.tool_name)
            )

            for issue in sorted_issues:
                severity_icon = self._get_severity_icon(issue.severity)

                row = [issue.tool_name, severity_icon, issue.message]

                if verbose:
                    row.append(issue.suggestion)

                issues_table.add_row(*row)

            console.print(issues_table)

            if not verbose and issues:
                console.print(
                    "\n[dim]💡 Use --verbose flag to see detailed suggestions[/dim]"
                )

        # Recommendations
        if recommendations:
            console.print(f"\n[bold yellow]🎯 Top Recommendations:[/bold yellow]")
            for i, rec in enumerate(recommendations, 1):
                console.print(f"   {i}. {rec}")

        # Summary message
        if passed == total:
            console.print(
                f"\n[bold green]🎉 Excellent! All tools have agent-friendly descriptions![/bold green]"
            )
        elif errors == 0:
            console.print(
                f"\n[bold blue]👍 Good foundation! Address the warnings to make tools even more agent-friendly.[/bold blue]"
            )
        else:
            console.print(
                f"\n[bold yellow]📝 Focus on fixing the errors first, then address warnings for better agent experience.[/bold yellow]"
            )

    def _display_token_efficiency_results(
        self, results: Dict[str, Any], verbose: bool
    ) -> None:
        """Display token efficiency analysis results."""

        issues = results.get("issues", [])
        stats = results.get("statistics", {})
        recommendations = results.get("recommendations", [])
        tool_metrics = results.get("tool_metrics", [])

        console.print(f"\n[bold green]🔢 Token Efficiency Analysis[/bold green]")

        # Overall statistics
        total_tools = stats.get("total_tools", 0)
        analyzed_tools = stats.get("tools_analyzed", 0)
        avg_tokens = stats.get("avg_tokens_per_response", 0)
        max_tokens = stats.get("max_tokens_observed", 0)
        tools_exceeding = stats.get("tools_exceeding_limit", 0)

        # Create summary table
        summary_table = Table(show_header=True, header_style="bold magenta")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right")
        summary_table.add_column("Status", justify="center")

        if analyzed_tools > 0:
            # Average response size
            avg_status = (
                "✅ Efficient"
                if avg_tokens < 5000
                else "⚠️ Moderate" if avg_tokens < 15000 else "🚨 Large"
            )
            summary_table.add_row(
                "Average Response Size", f"{avg_tokens:,.0f} tokens", avg_status
            )

            # Maximum response size
            max_status = (
                "✅ Good"
                if max_tokens < 25000
                else "⚠️ Large" if max_tokens < 50000 else "🚨 Oversized"
            )
            summary_table.add_row(
                "Largest Response", f"{max_tokens:,} tokens", max_status
            )

            # Tools exceeding limit
            exceeding_status = (
                "✅ None" if tools_exceeding == 0 else f"🚨 {tools_exceeding}"
            )
            summary_table.add_row(
                "Tools Over 25k Tokens", str(tools_exceeding), exceeding_status
            )

            summary_table.add_row(
                "Tools Successfully Analyzed",
                f"{analyzed_tools}/{total_tools}",
                "✅ Complete" if analyzed_tools == total_tools else "⚠️ Partial",
            )

        console.print(summary_table)

        # Tool-specific metrics table (if verbose and we have metrics)
        if verbose and tool_metrics:
            console.print(f"\n[bold cyan]📊 Per-Tool Response Metrics[/bold cyan]")

            metrics_table = Table(show_header=True, header_style="bold cyan")
            metrics_table.add_column("Tool Name", style="cyan", min_width=20)
            metrics_table.add_column("Avg Tokens", justify="right", min_width=12)
            metrics_table.add_column("Max Tokens", justify="right", min_width=12)
            metrics_table.add_column("Scenarios", justify="center", min_width=10)
            metrics_table.add_column("Status", justify="center", min_width=12)

            for metrics in tool_metrics:
                valid_measurements = [
                    m for m in metrics.measurements if m.token_count > 0
                ]
                scenario_count = len(valid_measurements)

                if scenario_count > 0:
                    status = (
                        "✅ Efficient"
                        if metrics.max_tokens < 25000
                        else "⚠️ Large" if metrics.max_tokens < 50000 else "🚨 Oversized"
                    )

                    metrics_table.add_row(
                        metrics.tool_name,
                        f"{metrics.avg_tokens:,.0f}",
                        f"{metrics.max_tokens:,}",
                        f"{scenario_count}/3",
                        status,
                    )

            console.print(metrics_table)

        # Issues table (if any)
        if issues:
            console.print(f"\n[bold red]🚨 Token Efficiency Issues Found:[/bold red]")

            issues_table = Table(show_header=True, header_style="bold red")
            issues_table.add_column("Tool", style="cyan", min_width=20)
            issues_table.add_column("Severity", justify="center", min_width=8)
            issues_table.add_column("Issue", min_width=40)

            if verbose:
                issues_table.add_column("Scenario", min_width=15)
                issues_table.add_column("Tokens", justify="right", min_width=10)

            # Sort issues by severity and measured tokens
            severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
            sorted_issues = sorted(
                issues,
                key=lambda x: (
                    severity_order[x.severity],
                    -(x.measured_tokens or 0),
                    x.tool_name,
                ),
            )

            for issue in sorted_issues:
                severity_icon = self._get_severity_icon(issue.severity)

                row = [issue.tool_name, severity_icon, issue.message]

                if verbose:
                    row.append(issue.scenario or "N/A")
                    row.append(
                        f"{issue.measured_tokens:,}" if issue.measured_tokens else "N/A"
                    )

                issues_table.add_row(*row)

            console.print(issues_table)

            if verbose:
                # Show detailed suggestions
                console.print(f"\n[bold yellow]💡 Detailed Suggestions:[/bold yellow]")
                for issue in sorted_issues:
                    if issue.suggestion:
                        console.print(
                            f"   • [cyan]{issue.tool_name}[/cyan]: {issue.suggestion}"
                        )

            elif issues:
                console.print(
                    "\n[dim]💡 Use --verbose flag to see detailed suggestions and token counts[/dim]"
                )

        # Recommendations
        if recommendations:
            console.print(
                f"\n[bold yellow]🎯 Token Efficiency Recommendations:[/bold yellow]"
            )
            for i, rec in enumerate(recommendations, 1):
                console.print(f"   {i}. {rec}")

        # Summary message
        if not issues:
            console.print(
                f"\n[green]✅ All analyzed tools show good token efficiency![/green]"
            )
        elif tools_exceeding == 0:
            console.print(
                f"\n[yellow]⚠️  Found efficiency improvements, but no tools exceed the 25k token limit[/yellow]"
            )
        else:
            console.print(
                f"\n[red]🚨 {tools_exceeding} tool(s) exceed the recommended 25k token limit[/red]"
            )

    def _get_severity_icon(self, severity: Severity) -> str:
        """Get icon for severity level."""
        icons = {
            Severity.ERROR: "[red]❌[/red]",
            Severity.WARNING: "[yellow]⚠️[/yellow]",
            Severity.INFO: "[blue]ℹ️[/blue]",
        }
        return icons.get(severity, "❓")

    def _display_json(self, results: Dict[str, Any]) -> None:
        """Display results as JSON."""
        # Convert dataclasses to dicts for JSON serialization
        json_results = self._convert_for_json(results)
        console.print(json.dumps(json_results, indent=2))

    def _display_yaml(self, results: Dict[str, Any]) -> None:
        """Display results as YAML."""
        try:
            import yaml

            yaml_results = self._convert_for_json(results)
            console.print(yaml.dump(yaml_results, default_flow_style=False))
        except ImportError:
            console.print(
                "[red]Error: PyYAML not installed. Install with: pip install PyYAML[/red]"
            )
            console.print("Falling back to JSON output:")
            self._display_json(results)

    def _convert_for_json(self, obj: Any) -> Any:
        """Convert objects to JSON-serializable format."""
        if isinstance(obj, dict):
            return {k: self._convert_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_for_json(item) for item in obj]
        elif hasattr(obj, "__dict__"):
            # Convert dataclass or object to dict
            return self._convert_for_json(obj.__dict__)
        elif isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        else:
            # Convert enum or other objects to string
            return str(obj)
