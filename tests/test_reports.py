"""Tests for report formatting helpers."""

from __future__ import annotations

import sys
import types

from rich.console import Console

from mcp_analyzer.checkers.descriptions import DescriptionIssue, IssueType as DescriptionIssueType, Severity as DescriptionSeverity
from mcp_analyzer.checkers.token_efficiency import (
    ResponseMetric,
    ResponseMetrics,
    TokenEfficiencyIssue,
    IssueType as TokenIssueType,
    Severity as TokenSeverity,
)
from mcp_analyzer.reports import ReportFormatter


def build_sample_results() -> dict:
    """Construct a representative results payload."""

    description_issue = DescriptionIssue(
        tool_name="alpha",
        issue_type=DescriptionIssueType.MISSING_DESCRIPTION,
        severity=DescriptionSeverity.ERROR,
        message="Missing description",
        suggestion="Add clear description",
    )

    token_metric = ResponseMetric(
        scenario="bulk",
        token_count=30000,
        response_time=1.2,
        response_size_bytes=2048,
        contains_low_value_data=False,
        has_verbose_identifiers=False,
    )
    token_metrics = ResponseMetrics(
        tool_name="beta",
        measurements=[token_metric],
        avg_tokens=28000,
        max_tokens=30000,
        min_tokens=28000,
    )
    token_issue = TokenEfficiencyIssue(
        tool_name="beta",
        issue_type=TokenIssueType.OVERSIZED_RESPONSE,
        severity=TokenSeverity.WARNING,
        message="Large response",
        suggestion="Introduce pagination",
        scenario="bulk",
        measured_tokens=30000,
    )

    return {
        "server_url": "http://localhost:8000/mcp",
        "tools_count": 2,
        "checks": {
            "descriptions": {
                "issues": [description_issue],
                "statistics": {
                    "total_tools": 2,
                    "tools_passed": 1,
                    "errors": 1,
                    "warnings": 0,
                    "info": 0,
                },
                "recommendations": ["Add onboarding docs"],
            },
            "token_efficiency": {
                "issues": [token_issue],
                "tool_metrics": [token_metrics],
                "statistics": {
                    "total_tools": 2,
                    "tools_analyzed": 1,
                    "errors": 0,
                    "warnings": 1,
                    "info": 0,
                    "avg_tokens_per_response": 28000,
                    "max_tokens_observed": 30000,
                    "tools_exceeding_limit": 1,
                },
                "recommendations": ["Paginate heavy listings"],
            },
        },
    }


def test_report_formatter_table_includes_sections(monkeypatch) -> None:
    """Table output should mention each major analysis section."""

    from mcp_analyzer import reports as module

    recording_console = Console(record=True, width=120)
    monkeypatch.setattr(module, "console", recording_console)

    formatter = ReportFormatter(output_format="table")
    formatter.display_results(build_sample_results(), verbose=True)

    output = recording_console.export_text()

    assert "MCP Server Analysis Report" in output
    assert "AI-Readable Description Analysis" in output
    assert "Token Efficiency Analysis" in output
    assert "Paginate heavy listings" in output


def test_report_formatter_json_and_yaml_output(monkeypatch) -> None:
    """Structured outputs should serialize results in the requested format."""

    from mcp_analyzer import reports as module

    recording_console_json = Console(record=True, width=120)
    monkeypatch.setattr(module, "console", recording_console_json)

    formatter = ReportFormatter(output_format="json")
    formatter.display_results(build_sample_results(), verbose=False)

    json_output = recording_console_json.export_text()
    assert '"server_url"' in json_output

    fake_yaml = types.ModuleType("yaml")

    def dump(data, default_flow_style=False):
        dump.called_with = (data, default_flow_style)
        return "yaml-output"

    dump.called_with = None
    fake_yaml.dump = dump
    sys.modules.pop("yaml", None)
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)

    recording_console_yaml = Console(record=True, width=120)
    monkeypatch.setattr(module, "console", recording_console_yaml)

    formatter_yaml = ReportFormatter(output_format="yaml")
    formatter_yaml.display_results(build_sample_results(), verbose=False)

    yaml_output = recording_console_yaml.export_text()
    assert "yaml-output" in yaml_output
    assert dump.called_with is not None
