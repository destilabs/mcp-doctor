"""Token efficiency checker based on Anthropic's guidelines."""

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


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


class TokenEfficiencyChecker:
    """
    Analyzes MCP tools for token efficiency and response optimization.

    Based on Anthropic's recommendations:
    - Tool responses should be under 25,000 tokens
    - Implement pagination, filtering, and truncation
    - Prioritize contextual relevance over flexibility
    - Use semantic identifiers instead of technical ones
    """

    def __init__(self) -> None:
        self.max_recommended_tokens = 25000  # From Anthropic's article
        self.sample_requests_per_tool = 3  # Test multiple scenarios

        # Patterns for detecting verbose identifiers
        self.verbose_id_patterns = [
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",  # UUID
            r"[0-9a-f]{32}",  # MD5-like hashes
            r"[0-9a-f]{40}",  # SHA1-like hashes
            r"[A-Za-z0-9]{20,}",  # Long alphanumeric IDs
        ]

        # Pagination parameter indicators
        self.pagination_params = [
            "limit",
            "offset",
            "page",
            "page_size",
            "per_page",
            "cursor",
            "next_token",
            "continuation_token",
            "start",
            "count",
        ]

        # Filtering parameter indicators
        self.filtering_params = [
            "filter",
            "where",
            "query",
            "search",
            "include",
            "exclude",
            "fields",
            "select",
            "only",
            "except",
            "type",
            "status",
        ]

        # Response format control parameters
        self.format_control_params = [
            "format",
            "response_format",
            "detail_level",
            "verbosity",
            "compact",
            "full",
            "summary",
            "detailed",
        ]

    async def analyze_token_efficiency(
        self, tools: List[Any], mcp_client: Any
    ) -> Dict[str, Any]:
        """
        Analyze tools for token efficiency issues.

        Args:
            tools: List of MCP tools to analyze
            mcp_client: MCP client for executing tool calls

        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Starting token efficiency analysis for {len(tools)} tools")

        issues = []
        tool_metrics = []
        stats = {
            "total_tools": len(tools),
            "tools_analyzed": 0,
            "tools_with_issues": 0,
            "errors": 0,
            "warnings": 0,
            "info": 0,
            "avg_tokens_per_response": 0,
            "max_tokens_observed": 0,
            "tools_exceeding_limit": 0,
        }

        for tool in tools:
            try:
                # Static analysis (schema-based)
                static_issues = self._analyze_tool_schema(tool)
                issues.extend(static_issues)

                # Dynamic analysis (execution-based)
                try:
                    metrics = await self._measure_response_sizes(tool, mcp_client)
                    tool_metrics.append(metrics)

                    dynamic_issues = self._analyze_response_metrics(metrics)
                    issues.extend(dynamic_issues)

                    stats["tools_analyzed"] += 1

                except Exception as e:
                    logger.warning(
                        f"Failed to analyze tool {getattr(tool, 'name', 'unknown')}: {e}"
                    )
                    # Continue with static analysis only

            except Exception as e:
                logger.error(
                    f"Failed to analyze tool {getattr(tool, 'name', 'unknown')}: {e}"
                )
                continue

        # Calculate statistics
        if tool_metrics:
            all_measurements = []
            for metrics in tool_metrics:
                all_measurements.extend(metrics.measurements)

            if all_measurements:
                token_counts = [
                    m.token_count for m in all_measurements if m.token_count > 0
                ]
                if token_counts:
                    stats["avg_tokens_per_response"] = int(
                        sum(token_counts) / len(token_counts)
                    )
                    stats["max_tokens_observed"] = max(token_counts)
                    stats["tools_exceeding_limit"] = len(
                        [t for t in token_counts if t > self.max_recommended_tokens]
                    )

        # Count issue severities
        tools_with_issues = set()
        for issue in issues:
            tools_with_issues.add(issue.tool_name)
            if issue.severity == Severity.ERROR:
                stats["errors"] += 1
            elif issue.severity == Severity.WARNING:
                stats["warnings"] += 1
            elif issue.severity == Severity.INFO:
                stats["info"] += 1

        stats["tools_with_issues"] = len(tools_with_issues)

        return {
            "issues": issues,
            "tool_metrics": tool_metrics,
            "statistics": stats,
            "recommendations": self._generate_recommendations(issues, stats),
        }

    def _analyze_tool_schema(self, tool: Any) -> List[TokenEfficiencyIssue]:
        """Analyze tool schema for potential token efficiency issues."""
        issues = []
        tool_name = getattr(tool, "name", "unknown_tool")

        # Check for pagination support
        issues.extend(self._check_pagination_support(tool))

        # Check for filtering support
        issues.extend(self._check_filtering_support(tool))

        # Check for response format control
        issues.extend(self._check_response_format_control(tool))

        return issues

    def _check_pagination_support(self, tool: Any) -> List[TokenEfficiencyIssue]:
        """Check if tool supports pagination for large datasets."""
        issues: list[TokenEfficiencyIssue] = []
        tool_name = getattr(tool, "name", "unknown_tool")

        input_schema = getattr(tool, "input_schema", None) or getattr(
            tool, "parameters", None
        )
        if not input_schema or not isinstance(input_schema, dict):
            return issues

        properties = input_schema.get("properties", {})

        # Check if tool has pagination parameters
        has_pagination = any(
            param_name.lower() in [p.lower() for p in self.pagination_params]
            for param_name in properties.keys()
        )

        # Check if tool likely returns lists/collections
        if not has_pagination and self._likely_returns_collections(tool):
            issues.append(
                TokenEfficiencyIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.NO_PAGINATION,
                    severity=Severity.INFO,
                    message="Tool likely returns collections but doesn't support pagination",
                    suggestion="Consider adding pagination parameters (limit, offset, page) to control response size",
                )
            )

        return issues

    def _check_filtering_support(self, tool: Any) -> List[TokenEfficiencyIssue]:
        """Check if tool supports filtering to reduce response size."""
        issues: List[TokenEfficiencyIssue] = []
        tool_name = getattr(tool, "name", "unknown_tool")

        input_schema = getattr(tool, "input_schema", None) or getattr(
            tool, "parameters", None
        )
        if not input_schema or not isinstance(input_schema, dict):
            return issues

        properties = input_schema.get("properties", {})

        # Check if tool has filtering parameters
        has_filtering = any(
            param_name.lower() in [f.lower() for f in self.filtering_params]
            for param_name in properties.keys()
        )

        # Check if tool would benefit from filtering
        if not has_filtering and self._would_benefit_from_filtering(tool):
            issues.append(
                TokenEfficiencyIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.MISSING_FILTERING,
                    severity=Severity.INFO,
                    message="Tool would benefit from filtering capabilities to reduce response size",
                    suggestion="Consider adding filtering parameters to allow users to specify exactly what data they need",
                )
            )

        return issues

    def _check_response_format_control(self, tool: Any) -> List[TokenEfficiencyIssue]:
        """Check if tool supports response format control."""
        issues: List[TokenEfficiencyIssue] = []
        tool_name = getattr(tool, "name", "unknown_tool")

        input_schema = getattr(tool, "input_schema", None) or getattr(
            tool, "parameters", None
        )
        if not input_schema or not isinstance(input_schema, dict):
            return issues

        properties = input_schema.get("properties", {})

        # Check if tool has response format control parameters
        has_format_control = any(
            param_name.lower() in [f.lower() for f in self.format_control_params]
            for param_name in properties.keys()
        )

        # Check if tool would benefit from format control
        if not has_format_control and self._would_benefit_from_format_control(tool):
            issues.append(
                TokenEfficiencyIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.NO_RESPONSE_FORMAT_CONTROL,
                    severity=Severity.INFO,
                    message="Tool could benefit from response format control options",
                    suggestion="Consider adding response_format parameter (e.g., 'concise', 'detailed') to control output verbosity",
                )
            )

        return issues

    async def _measure_response_sizes(
        self, tool: Any, mcp_client: Any
    ) -> ResponseMetrics:
        """Execute sample tool calls and measure response token counts."""
        tool_name = getattr(tool, "name", "unknown_tool")
        logger.debug(f"Measuring response sizes for tool: {tool_name}")

        # Generate test scenarios
        test_scenarios = self._generate_test_scenarios(tool)

        measurements = []
        for scenario in test_scenarios:
            try:
                start_time = time.time()

                # Execute tool call
                response = await mcp_client.call_tool(tool_name, scenario.params)

                end_time = time.time()

                # Analyze response
                token_count = self._estimate_token_count(response)
                response_size = len(json.dumps(response, ensure_ascii=False))

                measurements.append(
                    ResponseMetric(
                        scenario=scenario.name,
                        token_count=token_count,
                        response_time=end_time - start_time,
                        response_size_bytes=response_size,
                        contains_low_value_data=self._detect_low_value_data(response),
                        has_verbose_identifiers=self._detect_verbose_identifiers(
                            response
                        ),
                        is_truncated=self._detect_truncation(response),
                    )
                )

                logger.debug(
                    f"Tool {tool_name} scenario {scenario.name}: {token_count} tokens"
                )

            except Exception as e:
                measurements.append(
                    ResponseMetric(
                        scenario=scenario.name,
                        token_count=0,
                        response_time=0,
                        response_size_bytes=0,
                        contains_low_value_data=False,
                        has_verbose_identifiers=False,
                        error=str(e),
                    )
                )
                logger.warning(
                    f"Failed to execute {tool_name} with scenario {scenario.name}: {e}"
                )

        # Calculate aggregate metrics
        valid_measurements = [m for m in measurements if m.token_count > 0]
        if valid_measurements:
            token_counts = [m.token_count for m in valid_measurements]
            avg_tokens = sum(token_counts) / len(token_counts)
            max_tokens = max(token_counts)
            min_tokens = min(token_counts)
        else:
            avg_tokens = max_tokens = min_tokens = 0

        return ResponseMetrics(
            tool_name=tool_name,
            measurements=measurements,
            avg_tokens=avg_tokens,
            max_tokens=max_tokens,
            min_tokens=min_tokens,
        )

    def _analyze_response_metrics(
        self, metrics: ResponseMetrics
    ) -> List[TokenEfficiencyIssue]:
        """Analyze response metrics to identify efficiency issues."""
        issues = []

        # Check for oversized responses
        for measurement in metrics.measurements:
            if measurement.token_count > self.max_recommended_tokens:
                issues.append(
                    TokenEfficiencyIssue(
                        tool_name=metrics.tool_name,
                        issue_type=IssueType.OVERSIZED_RESPONSE,
                        severity=Severity.WARNING,
                        message=f"Response contains {measurement.token_count:,} tokens (>{self.max_recommended_tokens:,} recommended)",
                        suggestion="Consider implementing pagination, filtering, or truncation to reduce response size",
                        scenario=measurement.scenario,
                        measured_tokens=measurement.token_count,
                    )
                )

        # Check for verbose identifiers
        verbose_measurements = [
            m for m in metrics.measurements if m.has_verbose_identifiers
        ]
        if verbose_measurements:
            issues.append(
                TokenEfficiencyIssue(
                    tool_name=metrics.tool_name,
                    issue_type=IssueType.VERBOSE_IDENTIFIERS,
                    severity=Severity.INFO,
                    message="Responses contain verbose technical identifiers (UUIDs, hashes)",
                    suggestion="Consider using semantic identifiers or provide response format options to exclude technical IDs",
                )
            )

        # Check for low-value data
        low_value_measurements = [
            m for m in metrics.measurements if m.contains_low_value_data
        ]
        if low_value_measurements:
            issues.append(
                TokenEfficiencyIssue(
                    tool_name=metrics.tool_name,
                    issue_type=IssueType.REDUNDANT_DATA,
                    severity=Severity.INFO,
                    message="Responses contain potentially redundant or low-value data",
                    suggestion="Review response format to prioritize high-signal information",
                )
            )

        return issues

    def _generate_test_scenarios(self, tool: Any) -> List[EvaluationScenario]:
        """Generate realistic test parameters for the tool."""
        scenarios = []
        tool_name = getattr(tool, "name", "unknown_tool")

        input_schema = getattr(tool, "input_schema", None) or getattr(
            tool, "parameters", None
        )
        if not input_schema or not isinstance(input_schema, dict):
            # Create minimal scenario with no parameters
            scenarios.append(
                EvaluationScenario(
                    name="minimal", params={}, description="No parameters"
                )
            )
            return scenarios

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Scenario 1: Minimal (required parameters only)
        minimal_params = {}
        for param in required:
            if param in properties:
                minimal_params[param] = self._generate_sample_value(
                    param, properties[param]
                )

        scenarios.append(
            EvaluationScenario(
                name="minimal",
                params=minimal_params,
                description="Required parameters only",
            )
        )

        # Scenario 2: Typical (some optional parameters)
        typical_params = minimal_params.copy()

        # Add pagination if available (small limit)
        for pagination_param in self.pagination_params:
            if pagination_param in properties:
                if pagination_param in ["limit", "count", "per_page", "page_size"]:
                    typical_params[pagination_param] = 10
                elif pagination_param in ["page"]:
                    typical_params[pagination_param] = 1
                break

        scenarios.append(
            EvaluationScenario(
                name="typical",
                params=typical_params,
                description="Typical usage with moderate limits",
            )
        )

        # Scenario 3: Large (test for potential oversized responses)
        large_params = minimal_params.copy()

        # Add larger pagination if available
        for pagination_param in self.pagination_params:
            if pagination_param in properties:
                if pagination_param in ["limit", "count", "per_page", "page_size"]:
                    large_params[pagination_param] = 1000  # Large but not excessive
                elif pagination_param in ["page"]:
                    large_params[pagination_param] = 1
                break

        scenarios.append(
            EvaluationScenario(
                name="large",
                params=large_params,
                description="Large request to test response size limits",
            )
        )

        return scenarios

    def _generate_sample_value(
        self, param_name: str, param_schema: Dict[str, Any]
    ) -> Any:
        """Generate a sample value for a parameter based on its schema."""
        param_type = param_schema.get("type", "string")

        if param_type == "string":
            # Generate contextual sample values
            param_lower = param_name.lower()
            if any(word in param_lower for word in ["url", "link", "href"]):
                return "https://example.com"
            elif any(word in param_lower for word in ["email", "mail"]):
                return "test@example.com"
            elif any(word in param_lower for word in ["query", "search", "term"]):
                return "sample query"
            elif any(word in param_lower for word in ["id", "key"]):
                return "sample_id"
            else:
                return "sample_value"
        elif param_type == "integer":
            return 1
        elif param_type == "number":
            return 1.0
        elif param_type == "boolean":
            return True
        elif param_type == "array":
            return []
        elif param_type == "object":
            return {}
        else:
            return None

    def _estimate_token_count(self, response: Any) -> int:
        """Estimate token count in response (approximation)."""
        if response is None:
            return 0

        # Convert response to string representation
        try:
            response_text = json.dumps(response, ensure_ascii=False)
        except (TypeError, ValueError):
            response_text = str(response)

        # Rough approximation: 1 token ≈ 4 characters for English text
        # This is a conservative estimate; actual tokenization varies by model
        estimated_tokens = len(response_text) // 4

        return max(1, estimated_tokens)  # Minimum 1 token

    def _detect_low_value_data(self, response: Any) -> bool:
        """Detect if response contains potentially low-value data."""
        if not isinstance(response, (dict, list)):
            return False

        response_str = json.dumps(response).lower()

        # Look for patterns that might indicate low-value data
        low_value_patterns = [
            r'"created_at":\s*"[^"]*"',  # Timestamps might be low-value in some contexts
            r'"updated_at":\s*"[^"]*"',
            r'"metadata":\s*\{[^}]*\}',  # Generic metadata
            r'"_internal"',  # Internal fields
            r'"debug"',  # Debug information
        ]

        low_value_count = sum(
            1 for pattern in low_value_patterns if re.search(pattern, response_str)
        )

        # If more than 20% of detected patterns are low-value, flag it
        total_fields = response_str.count('":')  # Rough field count
        return total_fields > 0 and (low_value_count / max(total_fields, 1)) > 0.2

    def _detect_verbose_identifiers(self, response: Any) -> bool:
        """Detect if response contains verbose technical identifiers."""
        if not isinstance(response, (dict, list)):
            return False

        response_str = json.dumps(response)

        # Check for verbose identifier patterns
        for pattern in self.verbose_id_patterns:
            if re.search(pattern, response_str):
                return True

        return False

    def _detect_truncation(self, response: Any) -> bool:
        """Detect if response appears to be truncated."""
        if not isinstance(response, (dict, list)):
            return False

        # Look for common truncation indicators
        response_str = json.dumps(response).lower()
        truncation_indicators = [
            "truncated",
            "more_available",
            "has_more",
            "continuation_token",
            "next_page",
            "partial",
            "limited",
            "excerpt",
        ]

        return any(indicator in response_str for indicator in truncation_indicators)

    def _likely_returns_collections(self, tool: Any) -> bool:
        """Check if tool likely returns collections/lists."""
        tool_name = getattr(tool, "name", "").lower()
        description = getattr(tool, "description", "").lower()

        collection_indicators = [
            "list",
            "search",
            "find",
            "get_all",
            "fetch_all",
            "query",
            "browse",
            "index",
            "catalog",
            "directory",
            "collection",
        ]

        return any(
            indicator in tool_name or indicator in description
            for indicator in collection_indicators
        )

    def _would_benefit_from_filtering(self, tool: Any) -> bool:
        """Check if tool would benefit from filtering capabilities."""
        return self._likely_returns_collections(tool)

    def _would_benefit_from_format_control(self, tool: Any) -> bool:
        """Check if tool would benefit from response format control."""
        tool_name = getattr(tool, "name", "").lower()
        description = getattr(tool, "description", "").lower()

        # Tools that fetch detailed information could benefit from format control
        detail_indicators = [
            "get",
            "fetch",
            "retrieve",
            "details",
            "info",
            "describe",
            "analyze",
            "report",
            "summary",
            "profile",
        ]

        return any(
            indicator in tool_name or indicator in description
            for indicator in detail_indicators
        )

    def _generate_recommendations(
        self, issues: List[TokenEfficiencyIssue], stats: Dict[str, Any]
    ) -> List[str]:
        """Generate top-level recommendations based on found issues."""
        recommendations = []

        # Count issues by type
        issue_counts: Dict[IssueType, int] = {}
        for issue in issues:
            issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1

        # Generate specific recommendations
        if issue_counts.get(IssueType.OVERSIZED_RESPONSE, 0) > 0:
            count = issue_counts[IssueType.OVERSIZED_RESPONSE]
            recommendations.append(
                f"Implement response size limits for {count} tools with oversized responses (>25k tokens)"
            )

        if issue_counts.get(IssueType.NO_PAGINATION, 0) > 0:
            count = issue_counts[IssueType.NO_PAGINATION]
            recommendations.append(
                f"Add pagination support to {count} tools that return collections"
            )

        if issue_counts.get(IssueType.MISSING_FILTERING, 0) > 0:
            count = issue_counts[IssueType.MISSING_FILTERING]
            recommendations.append(
                f"Add filtering capabilities to {count} tools to reduce response size"
            )

        if issue_counts.get(IssueType.VERBOSE_IDENTIFIERS, 0) > 0:
            count = issue_counts[IssueType.VERBOSE_IDENTIFIERS]
            recommendations.append(
                f"Replace verbose technical identifiers with semantic ones in {count} tools"
            )

        if issue_counts.get(IssueType.NO_RESPONSE_FORMAT_CONTROL, 0) > 0:
            count = issue_counts[IssueType.NO_RESPONSE_FORMAT_CONTROL]
            recommendations.append(
                f"Add response format control (concise/detailed) to {count} tools"
            )

        # General recommendations based on stats
        if stats.get("max_tokens_observed", 0) > self.max_recommended_tokens:
            recommendations.append(
                f"Consider implementing global response size limits - observed max: {stats['max_tokens_observed']:,} tokens"
            )

        if not recommendations:
            recommendations.append(
                "All tools show good token efficiency! Consider monitoring response sizes over time."
            )

        return recommendations
