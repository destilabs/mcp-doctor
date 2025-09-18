"""Configuration constants for MCP Analyzer reports and display."""

from dataclasses import dataclass, field
from typing import Dict

from .checkers.descriptions import Severity


@dataclass
class TokenThresholds:
    """Token count thresholds for efficiency analysis."""

    EFFICIENT_LIMIT: int = 5000
    MODERATE_LIMIT: int = 15000
    LARGE_LIMIT: int = 25000
    OVERSIZED_LIMIT: int = 50000


@dataclass
class TableColumnWidths:
    """Minimum column widths for various tables."""

    TOOL_NAME: int = 20
    SEVERITY: int = 8
    ISSUE_SHORT: int = 30
    SUGGESTION: int = 40
    ISSUE_LONG: int = 40
    SCENARIO: int = 15
    TOKENS: int = 10
    AVG_TOKENS: int = 12
    MAX_TOKENS: int = 12
    SCENARIOS_COUNT: int = 10
    STATUS: int = 12


@dataclass
class DisplayConfig:
    """General display configuration."""

    JSON_INDENT: int = 2
    PERCENTAGE_MULTIPLIER: int = 100
    PERCENTAGE_DECIMAL_PLACES: int = 1
    RECOMMENDATION_START_INDEX: int = 1
    MIN_TOKEN_COUNT: int = 0


class SeverityConfig:
    """Severity ordering and icons configuration."""

    SEVERITY_ORDER: Dict[Severity, int] = {
        Severity.ERROR: 0,
        Severity.WARNING: 1,
        Severity.INFO: 2,
    }

    SEVERITY_ICONS: Dict[Severity, str] = {
        Severity.ERROR: "[red]❌[/red]",
        Severity.WARNING: "[yellow]⚠️[/yellow]",
        Severity.INFO: "[blue]ℹ️[/blue]",
    }

    DEFAULT_ICON: str = "❓"


@dataclass
class ReportConfig:
    """Main configuration class combining all report settings."""

    token_thresholds: TokenThresholds = field(default_factory=TokenThresholds)
    table_widths: TableColumnWidths = field(default_factory=TableColumnWidths)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    severity: SeverityConfig = field(default_factory=SeverityConfig)


# Global configuration instance
report_config = ReportConfig()
