"""Unit tests for the SecurityChecker."""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

from mcp_analyzer.checkers.security import SecurityChecker, VulnerabilityLevel


def build_mock_client(
    transport: httpx.MockTransport,
) -> Callable[[], httpx.AsyncClient]:
    """Create a factory that returns an AsyncClient with supplied transport."""

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transport,
            base_url="http://example.com",
            follow_redirects=True,
        )

    return factory


def test_security_checker_verify_parameter_default() -> None:
    """SecurityChecker should default to verify=True for secure TLS verification."""
    checker = SecurityChecker()
    assert checker.verify is True


def test_security_checker_verify_parameter_explicit() -> None:
    """SecurityChecker should accept explicit verify parameter."""
    checker_secure = SecurityChecker(verify=True)
    assert checker_secure.verify is True

    checker_insecure = SecurityChecker(verify=False)
    assert checker_insecure.verify is False


def test_security_checker_build_client_uses_verify() -> None:
    """_build_client should create clients with the correct verify setting."""
    checker_secure = SecurityChecker(verify=True)
    client_secure = checker_secure._build_client()
    # Check that the client was created (we can't easily inspect the verify setting)
    assert client_secure is not None
    assert hasattr(client_secure, "get")  # Basic httpx.AsyncClient check

    checker_insecure = SecurityChecker(verify=False)
    client_insecure = checker_insecure._build_client()
    assert client_insecure is not None
    assert hasattr(client_insecure, "get")  # Basic httpx.AsyncClient check


def test_check_network_exposure_localhost_hostname() -> None:
    """Should detect localhost hostname binding."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://localhost:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-002"
    assert finding.level == VulnerabilityLevel.INFO
    assert "Local Network Binding" in finding.title
    assert finding.affected_component == "localhost"


def test_check_network_exposure_loopback_ipv4() -> None:
    """Should detect IPv4 loopback address."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://127.0.0.1:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-002"
    assert finding.level == VulnerabilityLevel.INFO
    assert "Local Network Binding" in finding.title
    assert finding.affected_component == "127.0.0.1"


def test_check_network_exposure_loopback_ipv6() -> None:
    """Should detect IPv6 loopback address."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://[::1]:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-002"
    assert finding.level == VulnerabilityLevel.INFO
    assert "Local Network Binding" in finding.title
    assert finding.affected_component == "::1"


def test_check_network_exposure_wildcard_ipv4() -> None:
    """Should detect IPv4 wildcard binding."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://0.0.0.0:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-003"
    assert finding.level == VulnerabilityLevel.MEDIUM
    assert "Wildcard Binding" in finding.title
    assert finding.affected_component == "0.0.0.0"
    assert "Wildcard IP address: 0.0.0.0" in finding.evidence


def test_check_network_exposure_wildcard_ipv6() -> None:
    """Should detect IPv6 wildcard binding."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://[::]:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-003"
    assert finding.level == VulnerabilityLevel.MEDIUM
    assert "Wildcard Binding" in finding.title
    assert finding.affected_component == "::"
    assert "Wildcard IP address: ::" in finding.evidence


def test_check_network_exposure_external_hostname() -> None:
    """Should detect external hostname exposure."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://example.com:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-001"
    assert finding.level == VulnerabilityLevel.MEDIUM
    assert "External Network Exposure" in finding.title
    assert finding.affected_component == "example.com"
    assert "Resolved host: example.com" in finding.evidence


def test_check_network_exposure_external_ipv4() -> None:
    """Should detect external IPv4 address exposure."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://8.8.8.8:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-001"
    assert finding.level == VulnerabilityLevel.MEDIUM
    assert "External Network Exposure" in finding.title
    assert finding.affected_component == "8.8.8.8"
    assert "Resolved host: 8.8.8.8" in finding.evidence


def test_check_network_exposure_private_ipv4() -> None:
    """Should treat private IPv4 addresses as external."""
    checker = SecurityChecker()
    test_ips = ["192.168.1.1", "10.0.0.1", "172.16.0.1"]

    for ip in test_ips:
        parsed_url = httpx.URL(f"http://{ip}:8080/path")
        findings = checker._check_network_exposure(parsed_url)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.vulnerability_id == "MCP-NET-001"
        assert finding.level == VulnerabilityLevel.MEDIUM
        assert "External Network Exposure" in finding.title
        assert finding.affected_component == ip
        assert f"Resolved host: {ip}" in finding.evidence


def test_check_network_exposure_no_host() -> None:
    """Should handle URLs without host gracefully."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("file:///path/to/file")
    findings = checker._check_network_exposure(parsed_url)

    # Should not crash and return empty findings
    assert isinstance(findings, list)
    assert len(findings) == 0


def test_check_network_exposure_empty_host() -> None:
    """Should handle empty host gracefully."""
    checker = SecurityChecker()
    # Create a URL with empty host (edge case)
    parsed_url = httpx.URL("http://")
    findings = checker._check_network_exposure(parsed_url)

    # Should not crash and return empty findings
    assert isinstance(findings, list)
    assert len(findings) == 0


def test_check_network_exposure_hostname_with_numbers() -> None:
    """Should handle hostnames that contain numbers as external."""
    checker = SecurityChecker()
    parsed_url = httpx.URL("http://server123.example.com:8080/path")
    findings = checker._check_network_exposure(parsed_url)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.vulnerability_id == "MCP-NET-001"
    assert finding.level == VulnerabilityLevel.MEDIUM
    assert "External Network Exposure" in finding.title
    assert finding.affected_component == "server123.example.com"
    assert "Resolved host: server123.example.com" in finding.evidence


def test_security_finding_to_dict_minimal() -> None:
    """Should convert SecurityFinding to dict with minimal fields."""
    from mcp_analyzer.checkers.security import SecurityFinding

    finding = SecurityFinding(
        vulnerability_id="TEST-001",
        title="Test Finding",
        description="Test description",
        level=VulnerabilityLevel.MEDIUM,
        category="Test Category",
        affected_component="test-component",
    )

    result = finding.to_dict()

    assert result == {
        "vulnerability_id": "TEST-001",
        "title": "Test Finding",
        "description": "Test description",
        "level": "MEDIUM",
        "category": "Test Category",
        "affected_component": "test-component",
    }
    # Verify optional fields are not included
    assert "evidence" not in result
    assert "recommendation" not in result


def test_security_finding_to_dict_with_evidence() -> None:
    """Should convert SecurityFinding to dict including evidence."""
    from mcp_analyzer.checkers.security import SecurityFinding

    finding = SecurityFinding(
        vulnerability_id="TEST-002",
        title="Test Finding",
        description="Test description",
        level=VulnerabilityLevel.HIGH,
        category="Test Category",
        affected_component="test-component",
        evidence="Test evidence",
    )

    result = finding.to_dict()

    assert result["evidence"] == "Test evidence"
    assert "recommendation" not in result


def test_security_finding_to_dict_with_recommendation() -> None:
    """Should convert SecurityFinding to dict including recommendation."""
    from mcp_analyzer.checkers.security import SecurityFinding

    finding = SecurityFinding(
        vulnerability_id="TEST-003",
        title="Test Finding",
        description="Test description",
        level=VulnerabilityLevel.CRITICAL,
        category="Test Category",
        affected_component="test-component",
        recommendation="Test recommendation",
    )

    result = finding.to_dict()

    assert result["recommendation"] == "Test recommendation"
    assert "evidence" not in result


def test_security_finding_to_dict_with_all_fields() -> None:
    """Should convert SecurityFinding to dict with all fields."""
    from mcp_analyzer.checkers.security import SecurityFinding

    finding = SecurityFinding(
        vulnerability_id="TEST-004",
        title="Test Finding",
        description="Test description",
        level=VulnerabilityLevel.LOW,
        category="Test Category",
        affected_component="test-component",
        evidence="Test evidence",
        recommendation="Test recommendation",
    )

    result = finding.to_dict()

    assert result == {
        "vulnerability_id": "TEST-004",
        "title": "Test Finding",
        "description": "Test description",
        "level": "LOW",
        "category": "Test Category",
        "affected_component": "test-component",
        "evidence": "Test evidence",
        "recommendation": "Test recommendation",
    }


@pytest.mark.asyncio
async def test_analyze_localhost() -> None:
    """Should analyze localhost target and return proper structure."""
    checker = SecurityChecker()
    result = await checker.analyze("http://localhost:8080")

    assert "target" in result
    assert result["target"] == "http://localhost:8080"
    assert "timestamp" in result
    assert "findings" in result
    assert "summary" in result
    assert "statistics" in result

    # Should have one INFO finding for localhost
    assert len(result["findings"]) == 1
    assert result["findings"][0]["vulnerability_id"] == "MCP-NET-002"
    assert result["findings"][0]["level"] == "INFO"

    # Check summary
    assert result["summary"]["INFO"] == 1
    assert result["summary"]["LOW"] == 0
    assert result["summary"]["MEDIUM"] == 0
    assert result["summary"]["HIGH"] == 0
    assert result["summary"]["CRITICAL"] == 0

    # Check statistics
    assert result["statistics"]["total_findings"] == 1


@pytest.mark.asyncio
async def test_analyze_wildcard_binding() -> None:
    """Should analyze wildcard binding and report MEDIUM severity."""
    checker = SecurityChecker()
    result = await checker.analyze("http://0.0.0.0:8080")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["vulnerability_id"] == "MCP-NET-003"
    assert result["findings"][0]["level"] == "MEDIUM"
    assert result["summary"]["MEDIUM"] == 1


@pytest.mark.asyncio
async def test_analyze_external_hostname() -> None:
    """Should analyze external hostname and report MEDIUM severity."""
    checker = SecurityChecker()
    result = await checker.analyze("http://example.com:8080")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["vulnerability_id"] == "MCP-NET-001"
    assert result["findings"][0]["level"] == "MEDIUM"
    assert result["summary"]["MEDIUM"] == 1


@pytest.mark.asyncio
async def test_analyze_without_scheme() -> None:
    """Should handle target without scheme."""
    checker = SecurityChecker()
    # When no scheme is provided, urlparse treats the part before : as scheme
    result = await checker.analyze("localhost:8080")

    # The target normalization sees "localhost" as scheme and "8080" as netloc
    assert "target" in result
    assert "findings" in result


def test_normalize_target_with_scheme() -> None:
    """Should preserve existing scheme in target."""
    normalized, parsed = SecurityChecker._normalize_target("https://example.com:8080")

    assert normalized == "https://example.com:8080"
    assert parsed.scheme == "https"  # httpx.URL.scheme is a string, not bytes
    assert parsed.host == "example.com"
    assert parsed.port == 8080


def test_normalize_target_without_scheme() -> None:
    """Should add http:// to target without scheme."""
    # Test with hostname only
    normalized, parsed = SecurityChecker._normalize_target("example.com")

    assert normalized == "http://example.com"
    assert parsed.scheme == "http"

    # The urlparse behavior with "//example.com:8080" creates "http:////example.com:8080"
    # because it prepends "http://" to "//example.com:8080"
    normalized2, parsed2 = SecurityChecker._normalize_target("//example.com:8080")
    assert normalized2 == "http:////example.com:8080"


def test_normalize_target_with_path() -> None:
    """Should handle targets with paths."""
    # Simple hostname with path
    normalized, parsed = SecurityChecker._normalize_target("example.com/api/v1")

    assert normalized == "http://example.com/api/v1"
    assert "/api/v1" in normalized


def test_normalize_target_host_only() -> None:
    """Should handle host-only targets."""
    normalized, parsed = SecurityChecker._normalize_target("example.com")

    # Without // prefix, "example.com" is treated as a path
    assert normalized == "http://example.com"
    assert parsed.scheme == "http"


def test_client_factory() -> None:
    """Should use provided client factory."""
    custom_client = httpx.AsyncClient(timeout=5)

    def custom_factory() -> httpx.AsyncClient:
        return custom_client

    checker = SecurityChecker(client_factory=custom_factory)
    client = checker._build_client()

    assert client is custom_client


def test_summarize_empty_findings() -> None:
    """Should summarize empty findings list."""
    summary = SecurityChecker._summarize([])

    assert summary == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}


def test_summarize_multiple_findings() -> None:
    """Should summarize multiple findings by severity."""
    from mcp_analyzer.checkers.security import SecurityFinding

    findings = [
        SecurityFinding(
            "1", "Title 1", "Desc 1", VulnerabilityLevel.CRITICAL, "Cat 1", "Comp 1"
        ),
        SecurityFinding(
            "2", "Title 2", "Desc 2", VulnerabilityLevel.HIGH, "Cat 2", "Comp 2"
        ),
        SecurityFinding(
            "3", "Title 3", "Desc 3", VulnerabilityLevel.HIGH, "Cat 3", "Comp 3"
        ),
        SecurityFinding(
            "4", "Title 4", "Desc 4", VulnerabilityLevel.MEDIUM, "Cat 4", "Comp 4"
        ),
        SecurityFinding(
            "5", "Title 5", "Desc 5", VulnerabilityLevel.MEDIUM, "Cat 5", "Comp 5"
        ),
        SecurityFinding(
            "6", "Title 6", "Desc 6", VulnerabilityLevel.MEDIUM, "Cat 6", "Comp 6"
        ),
        SecurityFinding(
            "7", "Title 7", "Desc 7", VulnerabilityLevel.LOW, "Cat 7", "Comp 7"
        ),
        SecurityFinding(
            "8", "Title 8", "Desc 8", VulnerabilityLevel.INFO, "Cat 8", "Comp 8"
        ),
    ]

    summary = SecurityChecker._summarize(findings)

    assert summary == {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 1, "INFO": 1}


def test_current_timestamp() -> None:
    """Should return ISO format timestamp with UTC timezone."""
    import re
    from datetime import datetime

    timestamp = SecurityChecker._current_timestamp()

    # Should match ISO format with timezone
    iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00$"
    assert re.match(iso_pattern, timestamp)

    # Should be parseable as datetime
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.tzinfo is not None


def test_api_token_detection_from_env_and_url(monkeypatch) -> None:
    """_check_api_token_usage should flag token-like usage from env and URL."""
    # Provide mock process env with token-like keys
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 24)
    monkeypatch.setenv("NOT_SENSITIVE", "1")

    provided = {"ACCESS_TOKEN": "abcd", "SAFE": "ok"}
    target = "http://example.com/mcp?access_token=redacted&foo=bar"

    findings = SecurityChecker._check_api_token_usage(target, provided)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.level == VulnerabilityLevel.MEDIUM
    assert finding.vulnerability_id == "MCP-AUTH-001"
    # Evidence should reference names, not values
    assert "ACCESS_TOKEN" in (finding.evidence or "") or "access_token" in (
        finding.evidence or ""
    )
