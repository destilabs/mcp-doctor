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
    checker = SecurityChecker(timeout=5, client_factory=build_mock_client(transport))
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
