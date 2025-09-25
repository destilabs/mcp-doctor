"""Data models and types for token efficiency analysis."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class IssueType(str, Enum):
    """Types of token efficiency issues that can be found."""

    OVERSIZED_RESPONSE = "oversized_response"
    NO_PAGINATION = "no_pagination"
    VERBOSE_IDENTIFIERS = "verbose_identifiers"
    MISSING_FILTERING = "missing_filtering"
    REDUNDANT_DATA = "redundant_data"
    POOR_DEFAULT_LIMITS = "poor_default_limits"
    MISSING_TRUNCATION = "missing_truncation"
    NO_RESPONSE_FORMAT_CONTROL = "no_response_format_control"


class Severity(str, Enum):
    """Issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class EvaluationScenario:
    """Evaluation scenario for tool execution."""

    name: str
    params: Dict[str, Any]
    description: str


@dataclass
class ResponseMetric:
    """Metrics for a single tool response."""

    scenario: str
    token_count: int
    response_time: float
    response_size_bytes: int
    contains_low_value_data: bool
    has_verbose_identifiers: bool
    is_truncated: bool = False
    error: Optional[str] = None


@dataclass
class ResponseMetrics:
    """Collection of response metrics for a tool."""

    tool_name: str
    measurements: List[ResponseMetric]
    avg_tokens: float = 0
    max_tokens: int = 0
    min_tokens: int = 0


@dataclass
class TokenEfficiencyIssue:
    """Represents a token efficiency issue found in tools."""

    tool_name: str
    issue_type: IssueType
    severity: Severity
    message: str
    suggestion: str
    scenario: Optional[str] = None
    field: Optional[str] = None
    measured_tokens: Optional[int] = None
