"""Tests for token efficiency checker."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_analyzer.checkers.token_efficiency import (
    EvaluationScenario,
    IssueType,
    ResponseMetric,
    Severity,
    TokenEfficiencyChecker,
    TokenEfficiencyIssue,
)


class TestTokenEfficiencyChecker:
    """Test cases for TokenEfficiencyChecker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.checker = TokenEfficiencyChecker()

    def test_init(self):
        """Test checker initialization."""
        assert self.checker.max_recommended_tokens == 25000
        assert self.checker.sample_requests_per_tool == 3
        assert len(self.checker.pagination_params) > 0
        assert len(self.checker.filtering_params) > 0

    def test_estimate_token_count(self):
        """Test token count estimation."""
        # Simple text
        response = {"message": "Hello world"}
        tokens = self.checker._estimate_token_count(response)
        assert tokens > 0
        assert isinstance(tokens, int)

        # Large response
        large_response = {"data": "x" * 100000}  # 100k characters
        large_tokens = self.checker._estimate_token_count(large_response)
        assert large_tokens > tokens
        assert large_tokens > 20000  # Should be roughly 25k tokens

        # None response
        none_tokens = self.checker._estimate_token_count(None)
        assert none_tokens == 0

    def test_detect_verbose_identifiers(self):
        """Test verbose identifier detection."""
        # Response with UUID
        uuid_response = {"id": "550e8400-e29b-41d4-a716-446655440000", "name": "test"}
        assert self.checker._detect_verbose_identifiers(uuid_response) is True

        # Response with long hash
        hash_response = {"hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0", "name": "test"}
        assert self.checker._detect_verbose_identifiers(hash_response) is True

        # Response with semantic identifiers
        semantic_response = {"user_id": "john_doe", "project_name": "my_project"}
        assert self.checker._detect_verbose_identifiers(semantic_response) is False

        # Non-dict response
        assert self.checker._detect_verbose_identifiers("string") is False

    def test_detect_low_value_data(self):
        """Test low-value data detection."""
        # Response with many timestamps
        timestamp_response = {
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "metadata": {"internal": "data"},
            "debug": {"trace": "info"},
            "name": "test"
        }
        # This might be flagged as having low-value data
        result = self.checker._detect_low_value_data(timestamp_response)
        assert isinstance(result, bool)

        # Response with mostly high-value data
        clean_response = {"name": "test", "description": "A test item", "status": "active"}
        assert self.checker._detect_low_value_data(clean_response) is False

    def test_generate_sample_value(self):
        """Test sample value generation."""
        # URL parameter
        url_schema = {"type": "string", "description": "A URL"}
        url_value = self.checker._generate_sample_value("url", url_schema)
        assert url_value == "https://example.com"

        # Email parameter
        email_schema = {"type": "string"}
        email_value = self.checker._generate_sample_value("email", email_schema)
        assert email_value == "test@example.com"

        # Integer parameter
        int_schema = {"type": "integer"}
        int_value = self.checker._generate_sample_value("count", int_schema)
        assert int_value == 1

        # Boolean parameter
        bool_schema = {"type": "boolean"}
        bool_value = self.checker._generate_sample_value("enabled", bool_schema)
        assert bool_value is True

    def test_generate_test_scenarios(self):
        """Test test scenario generation."""
        # Tool with parameters
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.input_schema = {
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Result limit"},
                "page": {"type": "integer", "description": "Page number"}
            },
            "required": ["query"]
        }

        scenarios = self.checker._generate_test_scenarios(mock_tool)
        
        assert len(scenarios) == 3
        assert all(isinstance(s, EvaluationScenario) for s in scenarios)
        
        # Check scenario names
        scenario_names = [s.name for s in scenarios]
        assert "minimal" in scenario_names
        assert "typical" in scenario_names
        assert "large" in scenario_names

        # Minimal scenario should have required params only
        minimal = next(s for s in scenarios if s.name == "minimal")
        assert "query" in minimal.params
        
        # Large scenario should have pagination with larger values
        large = next(s for s in scenarios if s.name == "large")
        if "limit" in large.params:
            assert large.params["limit"] == 1000

    def test_likely_returns_collections(self):
        """Test collection detection."""
        # Tool that likely returns collections
        list_tool = MagicMock()
        list_tool.name = "list_users"
        list_tool.description = "List all users in the system"
        assert self.checker._likely_returns_collections(list_tool) is True

        # Tool that likely returns single items
        get_tool = MagicMock()
        get_tool.name = "get_user_profile"
        get_tool.description = "Get a specific user's profile"
        assert self.checker._likely_returns_collections(get_tool) is False

        # Search tool (returns collections)
        search_tool = MagicMock()
        search_tool.name = "search_documents"
        search_tool.description = "Search for documents"
        assert self.checker._likely_returns_collections(search_tool) is True

    def test_check_pagination_support(self):
        """Test pagination support checking."""
        # Tool with pagination
        paginated_tool = MagicMock()
        paginated_tool.name = "list_items"
        paginated_tool.description = "List all items"
        paginated_tool.input_schema = {
            "properties": {
                "limit": {"type": "integer"},
                "offset": {"type": "integer"}
            }
        }

        issues = self.checker._check_pagination_support(paginated_tool)
        assert len(issues) == 0  # No issues for paginated tool

        # Tool without pagination that should have it
        unpaginated_tool = MagicMock()
        unpaginated_tool.name = "list_all_users"
        unpaginated_tool.description = "List all users in the database"
        unpaginated_tool.input_schema = {
            "properties": {
                "filter": {"type": "string"}
            }
        }

        issues = self.checker._check_pagination_support(unpaginated_tool)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.NO_PAGINATION
        assert issues[0].severity == Severity.INFO

    def test_check_filtering_support(self):
        """Test filtering support checking."""
        # Tool without filtering that could benefit
        unfiltered_tool = MagicMock()
        unfiltered_tool.name = "search_documents"
        unfiltered_tool.description = "Search through documents"
        unfiltered_tool.input_schema = {
            "properties": {
                "text": {"type": "string"}
            }
        }

        # Verify this tool is detected as returning collections
        assert self.checker._likely_returns_collections(unfiltered_tool) is True

        issues = self.checker._check_filtering_support(unfiltered_tool)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.MISSING_FILTERING
        assert issues[0].severity == Severity.INFO

    def test_check_response_format_control(self):
        """Test response format control checking."""
        # Tool that could benefit from format control
        detail_tool = MagicMock()
        detail_tool.name = "get_user_details"
        detail_tool.description = "Get detailed user information"
        detail_tool.input_schema = {
            "properties": {
                "user_id": {"type": "string"}
            }
        }

        issues = self.checker._check_response_format_control(detail_tool)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.NO_RESPONSE_FORMAT_CONTROL
        assert issues[0].severity == Severity.INFO

    @pytest.mark.asyncio
    async def test_measure_response_sizes(self):
        """Test response size measurement."""
        # Mock tool
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.input_schema = {
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }

        # Mock client
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = {
            "result": "This is a test response with some content",
            "status": "success"
        }

        metrics = await self.checker._measure_response_sizes(mock_tool, mock_client)
        
        assert metrics.tool_name == "test_tool"
        assert len(metrics.measurements) == 3  # Three scenarios
        assert metrics.avg_tokens > 0
        assert metrics.max_tokens >= metrics.avg_tokens

        # Check that client was called
        assert mock_client.call_tool.call_count == 3

    @pytest.mark.asyncio
    async def test_measure_response_sizes_with_errors(self):
        """Test response size measurement with tool errors."""
        # Mock tool
        mock_tool = MagicMock()
        mock_tool.name = "failing_tool"
        mock_tool.input_schema = {"properties": {}}

        # Mock client that raises exceptions
        mock_client = AsyncMock()
        mock_client.call_tool.side_effect = Exception("Tool execution failed")

        metrics = await self.checker._measure_response_sizes(mock_tool, mock_client)
        
        assert metrics.tool_name == "failing_tool"
        assert len(metrics.measurements) == 3
        # All measurements should have errors
        assert all(m.error is not None for m in metrics.measurements)
        assert metrics.avg_tokens == 0

    def test_analyze_response_metrics(self):
        """Test response metrics analysis."""
        # Create mock metrics with oversized response
        mock_metrics = MagicMock()
        mock_metrics.tool_name = "oversized_tool"
        mock_metrics.measurements = [
            ResponseMetric(
                scenario="large",
                token_count=30000,  # Over limit
                response_time=1.0,
                response_size_bytes=120000,
                contains_low_value_data=False,
                has_verbose_identifiers=True
            ),
            ResponseMetric(
                scenario="typical",
                token_count=5000,
                response_time=0.5,
                response_size_bytes=20000,
                contains_low_value_data=True,
                has_verbose_identifiers=False
            )
        ]

        issues = self.checker._analyze_response_metrics(mock_metrics)
        
        # Should find multiple issues
        assert len(issues) > 0
        
        issue_types = [issue.issue_type for issue in issues]
        assert IssueType.OVERSIZED_RESPONSE in issue_types
        assert IssueType.VERBOSE_IDENTIFIERS in issue_types
        assert IssueType.REDUNDANT_DATA in issue_types

    def test_generate_recommendations(self):
        """Test recommendation generation."""
        issues = [
            TokenEfficiencyIssue(
                tool_name="tool1",
                issue_type=IssueType.OVERSIZED_RESPONSE,
                severity=Severity.WARNING,
                message="Response too large",
                suggestion="Add pagination"
            ),
            TokenEfficiencyIssue(
                tool_name="tool2",
                issue_type=IssueType.NO_PAGINATION,
                severity=Severity.INFO,
                message="No pagination",
                suggestion="Add pagination"
            ),
            TokenEfficiencyIssue(
                tool_name="tool3",
                issue_type=IssueType.NO_PAGINATION,
                severity=Severity.INFO,
                message="No pagination",
                suggestion="Add pagination"
            )
        ]

        stats = {
            "max_tokens_observed": 30000,
            "tools_exceeding_limit": 1
        }

        recommendations = self.checker._generate_recommendations(issues, stats)
        
        assert len(recommendations) > 0
        assert any("response size limits" in rec.lower() for rec in recommendations)
        assert any("pagination" in rec.lower() for rec in recommendations)
        assert any("global response size limits" in rec.lower() for rec in recommendations)

    def test_generate_recommendations_no_issues(self):
        """Test recommendation generation with no issues."""
        issues = []
        stats = {"max_tokens_observed": 5000}

        recommendations = self.checker._generate_recommendations(issues, stats)
        
        assert len(recommendations) == 1
        assert "good token efficiency" in recommendations[0].lower()
