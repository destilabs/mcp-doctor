"""Tests for description checker."""

import pytest
from mcp_analyzer.checkers.descriptions import DescriptionChecker, DescriptionIssue, Severity, IssueType
from mcp_analyzer.mcp_client import MCPTool


class TestDescriptionChecker:
    """Test cases for the DescriptionChecker class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.checker = DescriptionChecker()
    
    def test_good_description(self):
        """Test tool with good description passes all checks."""
        tool = MCPTool(
            name="create_income_operation",
            description="Create a new income operation in the financial system. Use this when you need to record incoming payments or revenue. Requires amount, account, and category information.",
            parameters={
                "properties": {
                    "operation_amount": {
                        "description": "The amount of the income operation in the account currency"
                    },
                    "target_account_id": {
                        "description": "Unique identifier of the account to receive the income"
                    }
                }
            }
        )
        
        issues = self.checker._analyze_single_tool(tool)
        assert len(issues) == 0, f"Good tool should have no issues, got: {[i.message for i in issues]}"
    
    def test_missing_description(self):
        """Test tool with missing description."""
        tool = MCPTool(name="test_tool", description=None)
        
        issues = self.checker._analyze_single_tool(tool)
        
        assert len(issues) >= 1
        missing_desc_issues = [i for i in issues if i.issue_type == IssueType.MISSING_DESCRIPTION]
        assert len(missing_desc_issues) == 1
        assert missing_desc_issues[0].severity == Severity.ERROR
    
    def test_too_short_description(self):
        """Test tool with too short description."""
        tool = MCPTool(name="test_tool", description="Short")
        
        issues = self.checker._analyze_single_tool(tool)
        
        short_issues = [i for i in issues if i.issue_type == IssueType.TOO_SHORT]
        assert len(short_issues) == 1
        assert short_issues[0].severity == Severity.WARNING
    
    def test_ambiguous_parameters(self):
        """Test detection of ambiguous parameter names."""
        tool = MCPTool(
            name="test_tool",
            description="A well-described tool for testing parameter name detection",
            parameters={
                "properties": {
                    "id": {"description": "Some ID"},  # Ambiguous
                    "data": {"description": "Some data"},  # Ambiguous
                    "user_account_id": {"description": "User account identifier"}  # Good
                }
            }
        )
        
        issues = self.checker._analyze_single_tool(tool)
        
        ambiguous_issues = [i for i in issues if i.issue_type == IssueType.AMBIGUOUS_PARAMS]
        assert len(ambiguous_issues) == 2  # 'id' and 'data'
        
        issue_fields = [i.field for i in ambiguous_issues]
        assert "parameter.id" in issue_fields
        assert "parameter.data" in issue_fields
        assert "parameter.user_account_id" not in issue_fields
    
    def test_technical_jargon_detection(self):
        """Test detection of technical jargon in descriptions."""
        tool = MCPTool(
            name="test_tool",
            description="This API endpoint handles JSON payload serialization and CRUD operations"
        )
        
        issues = self.checker._analyze_single_tool(tool)
        
        jargon_issues = [i for i in issues if i.issue_type == IssueType.TECHNICAL_JARGON]
        assert len(jargon_issues) == 1
        assert "api" in jargon_issues[0].message.lower()
        assert "json" in jargon_issues[0].message.lower()
        assert "crud" in jargon_issues[0].message.lower()
    
    def test_clear_purpose_detection(self):
        """Test detection of unclear purpose in descriptions."""
        unclear_tool = MCPTool(
            name="test_tool",
            description="This tool handles stuff and manages things in the system"
        )
        
        clear_tool = MCPTool(
            name="test_tool", 
            description="Create new user accounts in the authentication system"
        )
        
        unclear_issues = self.checker._analyze_single_tool(unclear_tool)
        clear_issues = self.checker._analyze_single_tool(clear_tool)
        
        unclear_purpose_issues = [i for i in unclear_issues if i.issue_type == IssueType.UNCLEAR_PURPOSE]
        clear_purpose_issues = [i for i in clear_issues if i.issue_type == IssueType.UNCLEAR_PURPOSE]
        
        assert len(unclear_purpose_issues) == 1
        assert len(clear_purpose_issues) == 0
    
    def test_missing_parameter_descriptions(self):
        """Test detection of missing parameter descriptions."""
        tool = MCPTool(
            name="test_tool",
            description="A well-described tool for testing parameter descriptions",
            parameters={
                "properties": {
                    "good_param": {"description": "This parameter has a description"},
                    "bad_param": {}  # Missing description
                }
            }
        )
        
        issues = self.checker._analyze_single_tool(tool)
        
        missing_desc_issues = [
            i for i in issues 
            if i.issue_type == IssueType.MISSING_DESCRIPTION and i.field and "parameter" in i.field
        ]
        assert len(missing_desc_issues) == 1
        assert "bad_param" in missing_desc_issues[0].field
    
    def test_context_indicators(self):
        """Test detection of missing usage context."""
        no_context_tool = MCPTool(
            name="test_tool",
            description="Updates user information in the database"
        )
        
        context_tool = MCPTool(
            name="test_tool",
            description="Updates user information when you need to modify user profile data. Use this after validating the user's identity."
        )
        
        no_context_issues = self.checker._analyze_single_tool(no_context_tool)
        context_issues = self.checker._analyze_single_tool(context_tool)
        
        no_context_missing = [i for i in no_context_issues if i.issue_type == IssueType.MISSING_CONTEXT]
        context_missing = [i for i in context_issues if i.issue_type == IssueType.MISSING_CONTEXT]
        
        assert len(no_context_missing) == 1
        assert len(context_missing) == 0
    
    def test_poor_parameter_names(self):
        """Test detection of poor parameter naming patterns."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool with various parameter names",
            parameters={
                "properties": {
                    "a": {"description": "Single letter param"},  # Poor
                    "param1": {"description": "Generic param name"},  # Poor
                    "temp": {"description": "Temporary variable"},  # Poor
                    "user_account_id": {"description": "Good descriptive name"}  # Good
                }
            }
        )
        
        issues = self.checker._analyze_single_tool(tool)
        
        poor_name_issues = [i for i in issues if i.issue_type == IssueType.POOR_PARAMETER_NAMES]
        
        # Should catch the poor names but not the good one
        poor_fields = [i.field for i in poor_name_issues]
        assert any("parameter.a" in field for field in poor_fields)
        assert any("parameter.param1" in field for field in poor_fields)
        assert not any("user_account_id" in field for field in poor_fields)
    
    def test_full_analysis_statistics(self):
        """Test the full analysis with statistics generation."""
        tools = [
            MCPTool(name="good_tool", description="Create user accounts when you need to register new users in the system"),
            MCPTool(name="bad_tool", description=None),  # Missing description
            MCPTool(name="warning_tool", description="Short"),  # Too short
        ]
        
        results = self.checker.analyze_tool_descriptions(tools)
        
        assert results["statistics"]["total_tools"] == 3
        assert results["statistics"]["tools_passed"] == 1
        assert results["statistics"]["tools_with_issues"] == 2
        assert results["statistics"]["errors"] >= 1  # Missing description
        assert results["statistics"]["warnings"] >= 1  # Too short
        
        # Check recommendations are generated
        assert len(results["recommendations"]) > 0
    
    def test_different_parameter_schema_formats(self):
        """Test handling of different parameter schema formats."""
        # Test with 'parameters' key instead of 'properties'
        tool1 = MCPTool(
            name="test_tool",
            description="Test tool with parameters key",
            parameters={
                "parameters": {
                    "good_param": {"description": "Well described parameter"}
                }
            }
        )
        
        # Test with 'fields' key
        tool2 = MCPTool(
            name="test_tool",
            description="Test tool with fields key",  
            parameters={
                "fields": {
                    "another_param": {"description": "Another well described parameter"}
                }
            }
        )
        
        issues1 = self.checker._analyze_single_tool(tool1)
        issues2 = self.checker._analyze_single_tool(tool2)
        
        # Should not have missing parameter description issues
        param_desc_issues1 = [i for i in issues1 if "parameter" in str(i.field) and i.issue_type == IssueType.MISSING_DESCRIPTION]
        param_desc_issues2 = [i for i in issues2 if "parameter" in str(i.field) and i.issue_type == IssueType.MISSING_DESCRIPTION]
        
        assert len(param_desc_issues1) == 0
        assert len(param_desc_issues2) == 0
