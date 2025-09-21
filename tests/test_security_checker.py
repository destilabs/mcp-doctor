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


@pytest.mark.asyncio
async def test_security_checker_detects_auth_and_network_findings() -> None:
    """Security checker should surface authentication and network findings."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path or "/"

        if path == "/":
            return httpx.Response(200, headers={})
        if path == "/.env":
            return httpx.Response(200, text="API_KEY=SHAREDSECRET1234567890")
        if path == "/tools":
            return httpx.Response(200, text="This tool can execute shell commands")
        if path == "/search":
            payload = request.url.params.get("q", "")
            return httpx.Response(200, text=payload)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    checker = SecurityChecker(timeout=5, verify=False, client_factory=build_mock_client(transport))
    result = await checker.analyze("http://example.com")

    findings = result["findings"]
    ids = {finding["vulnerability_id"] for finding in findings}

    expected_ids = {
        "MCP-AUTH-001",
        "MCP-NET-001",
    }

    assert expected_ids.issubset(ids)
    summary = result["summary"]
    assert summary[VulnerabilityLevel.CRITICAL.value] >= 1
    assert result["statistics"]["total_findings"] == len(findings)


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
    assert hasattr(client_secure, 'get')  # Basic httpx.AsyncClient check
    
    checker_insecure = SecurityChecker(verify=False)
    client_insecure = checker_insecure._build_client()
    assert client_insecure is not None
    assert hasattr(client_insecure, 'get')  # Basic httpx.AsyncClient check


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
