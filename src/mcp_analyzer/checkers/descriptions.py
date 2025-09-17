"""AI-readable description checker based on Anthropic's guidelines."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class IssueType(str, Enum):
    """Types of issues that can be found."""

    MISSING_DESCRIPTION = "missing_description"
    TOO_SHORT = "too_short"
    AMBIGUOUS_PARAMS = "ambiguous_params"
    MISSING_EXAMPLES = "missing_examples"
    UNCLEAR_PURPOSE = "unclear_purpose"
    TECHNICAL_JARGON = "technical_jargon"
    MISSING_CONTEXT = "missing_context"
    POOR_PARAMETER_NAMES = "poor_parameter_names"


class Severity(str, Enum):
    """Issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class DescriptionIssue:
    """Represents an issue found in tool descriptions."""

    tool_name: str
    issue_type: IssueType
    severity: Severity
    message: str
    suggestion: str
    field: Optional[str] = None


class DescriptionChecker:
    """
    Analyzes tool descriptions for AI agent friendliness.

    Based on Anthropic's recommendations:
    - Clear, unambiguous descriptions
    - Descriptive parameter names
    - Usage context and examples
    - Natural language over technical jargon
    """

    def __init__(self):
        self.ambiguous_terms = [
            "id",
            "data",
            "info",
            "item",
            "object",
            "value",
            "param",
            "arg",
            "input",
            "output",
            "result",
            "response",
        ]

        self.technical_jargon = [
            "uuid",
            "json",
            "api",
            "endpoint",
            "crud",
            "dto",
            "orm",
            "serialize",
            "deserialize",
            "payload",
            "schema",
        ]

        self.context_indicators = [
            "when",
            "if",
            "after",
            "before",
            "during",
            "for example",
            "use this",
            "helps to",
            "allows you",
            "enables",
        ]

    def analyze_tool_descriptions(self, tools: List[Any]) -> Dict[str, Any]:
        """
        Analyze all tool descriptions for agent-friendliness.

        Args:
            tools: List of MCP tools to analyze

        Returns:
            Dictionary with analysis results
        """
        issues = []
        stats = {
            "total_tools": len(tools),
            "tools_with_issues": 0,
            "errors": 0,
            "warnings": 0,
            "info": 0,
            "tools_passed": 0,
        }

        for tool in tools:
            tool_issues = self._analyze_single_tool(tool)
            if tool_issues:
                stats["tools_with_issues"] += 1
                issues.extend(tool_issues)

                for issue in tool_issues:
                    if issue.severity == Severity.ERROR:
                        stats["errors"] += 1
                    elif issue.severity == Severity.WARNING:
                        stats["warnings"] += 1
                    elif issue.severity == Severity.INFO:
                        stats["info"] += 1
            else:
                stats["tools_passed"] += 1

        return {
            "issues": issues,
            "statistics": stats,
            "recommendations": self._generate_recommendations(issues),
        }

    def _analyze_single_tool(self, tool: Any) -> List[DescriptionIssue]:
        """Analyze a single tool for description issues."""
        issues = []
        tool_name = getattr(tool, "name", "unknown_tool")

        description = getattr(tool, "description", None)
        issues.extend(self._check_main_description(tool_name, description))

        input_schema = getattr(tool, "input_schema", None) or getattr(
            tool, "parameters", None
        )
        if input_schema:
            issues.extend(self._check_parameters(tool_name, input_schema))

        return issues

    def _check_main_description(
        self, tool_name: str, description: Optional[str]
    ) -> List[DescriptionIssue]:
        """Check the main tool description."""
        issues = []

        if not description or not description.strip():
            issues.append(
                DescriptionIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.MISSING_DESCRIPTION,
                    severity=Severity.ERROR,
                    message="Tool has no description",
                    suggestion="Add a clear description explaining what this tool does and when to use it",
                    field="description",
                )
            )
            return issues

        if len(description.strip()) < 20:
            issues.append(
                DescriptionIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.TOO_SHORT,
                    severity=Severity.WARNING,
                    message=f"Description is too short ({len(description)} chars)",
                    suggestion="Expand description to include purpose, usage context, and expected outcomes",
                    field="description",
                )
            )

        if not self._has_clear_purpose(description):
            issues.append(
                DescriptionIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.UNCLEAR_PURPOSE,
                    severity=Severity.WARNING,
                    message="Description doesn't clearly explain the tool's purpose",
                    suggestion="Start with a clear action verb and explain what the tool accomplishes",
                    field="description",
                )
            )

        jargon_found = [
            word
            for word in self.technical_jargon
            if re.search(r"\b" + re.escape(word.lower()) + r"\b", description.lower())
        ]
        if jargon_found:
            issues.append(
                DescriptionIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.TECHNICAL_JARGON,
                    severity=Severity.INFO,
                    message=f"Contains technical jargon: {', '.join(jargon_found)}",
                    suggestion="Replace technical terms with natural language that AI agents can better understand",
                    field="description",
                )
            )

        if not any(
            indicator in description.lower() for indicator in self.context_indicators
        ):
            issues.append(
                DescriptionIssue(
                    tool_name=tool_name,
                    issue_type=IssueType.MISSING_CONTEXT,
                    severity=Severity.INFO,
                    message="Description lacks usage context",
                    suggestion="Add context about when and how to use this tool (e.g., 'Use this when...', 'This helps to...')",
                    field="description",
                )
            )

        return issues

    def _check_parameters(
        self, tool_name: str, schema: Dict[str, Any]
    ) -> List[DescriptionIssue]:
        """Check parameter definitions for clarity."""
        issues = []

        if not isinstance(schema, dict):
            return issues

        properties = schema.get("properties", {})
        if not properties:
            if "parameters" in schema:
                properties = schema["parameters"]
            elif "fields" in schema:
                properties = schema["fields"]

        for param_name, param_info in properties.items():
            if not isinstance(param_info, dict):
                continue

            if param_name.lower() in self.ambiguous_terms:
                issues.append(
                    DescriptionIssue(
                        tool_name=tool_name,
                        issue_type=IssueType.AMBIGUOUS_PARAMS,
                        severity=Severity.WARNING,
                        message=f"Parameter '{param_name}' has ambiguous name",
                        suggestion=f"Use a more descriptive name like 'user_id', 'account_data', etc. instead of '{param_name}'",
                        field=f"parameter.{param_name}",
                    )
                )

            if self._is_poor_parameter_name(param_name):
                issues.append(
                    DescriptionIssue(
                        tool_name=tool_name,
                        issue_type=IssueType.POOR_PARAMETER_NAMES,
                        severity=Severity.INFO,
                        message=f"Parameter '{param_name}' could be more descriptive",
                        suggestion="Consider a more semantic name that clearly indicates the parameter's purpose",
                        field=f"parameter.{param_name}",
                    )
                )

            param_desc = param_info.get("description", "")
            if not param_desc:
                issues.append(
                    DescriptionIssue(
                        tool_name=tool_name,
                        issue_type=IssueType.MISSING_DESCRIPTION,
                        severity=Severity.WARNING,
                        message=f"Parameter '{param_name}' has no description",
                        suggestion="Add a clear description explaining what this parameter is for",
                        field=f"parameter.{param_name}.description",
                    )
                )

        return issues

    def _has_clear_purpose(self, description: str) -> bool:
        """Check if description clearly states the tool's purpose."""

        clear_action_verbs = [
            "create",
            "update",
            "delete",
            "get",
            "fetch",
            "retrieve",
            "search",
            "find",
            "list",
            "generate",
            "calculate",
            "validate",
            "check",
        ]

        vague_terms = ["handle", "manage", "process", "deal with", "stuff", "things"]

        description_lower = description.lower()

        has_clear_action = any(
            re.search(r"\b" + re.escape(verb) + r"\b", description_lower)
            for verb in clear_action_verbs
        )

        has_vague_terms = any(
            re.search(r"\b" + re.escape(term) + r"\b", description_lower)
            for term in vague_terms
        )

        return has_clear_action and not has_vague_terms

    def _is_poor_parameter_name(self, param_name: str) -> bool:
        """Check if parameter name could be improved."""
        if len(param_name) == 1:
            return True

        poor_patterns = [
            r"^param\d*$",
            r"^arg\d*$",
            r"^val\d*$",
            r"^temp\d*$",
            r"^data\d*$",
        ]

        return any(re.match(pattern, param_name.lower()) for pattern in poor_patterns)

    def _generate_recommendations(self, issues: List[DescriptionIssue]) -> List[str]:
        """Generate top-level recommendations based on found issues."""
        recommendations = []

        issue_counts: Dict[IssueType, int] = {}
        for issue in issues:
            issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1

        if issue_counts.get(IssueType.MISSING_DESCRIPTION, 0) > 0:
            count = issue_counts[IssueType.MISSING_DESCRIPTION]
            recommendations.append(
                f"Add descriptions to {count} tools that are missing them entirely"
            )

        if issue_counts.get(IssueType.AMBIGUOUS_PARAMS, 0) > 0:
            count = issue_counts[IssueType.AMBIGUOUS_PARAMS]
            recommendations.append(
                f"Rename {count} ambiguous parameters to be more descriptive"
            )

        if issue_counts.get(IssueType.TOO_SHORT, 0) > 0:
            count = issue_counts[IssueType.TOO_SHORT]
            recommendations.append(
                f"Expand descriptions for {count} tools that have very brief descriptions"
            )

        if issue_counts.get(IssueType.MISSING_CONTEXT, 0) > 0:
            count = issue_counts[IssueType.MISSING_CONTEXT]
            recommendations.append(
                f"Add usage context to {count} tools to help agents understand when to use them"
            )

        if not recommendations:
            recommendations.append(
                "All tools have good descriptions! Consider adding usage examples for even better agent experience."
            )

        return recommendations
