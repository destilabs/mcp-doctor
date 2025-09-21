"""Security auditing checker for MCP servers and configurations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx


class VulnerabilityLevel(str, Enum):
    """Severity levels for detected findings."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass(slots=True)
class SecurityFinding:
    """Represents a single security finding discovered during analysis."""

    vulnerability_id: str
    title: str
    description: str
    level: VulnerabilityLevel
    category: str
    affected_component: str
    evidence: Optional[str] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding into a JSON-serializable dict."""

        data = {
            "vulnerability_id": self.vulnerability_id,
            "title": self.title,
            "description": self.description,
            "level": self.level.value,
            "category": self.category,
            "affected_component": self.affected_component,
        }
        if self.evidence is not None:
            data["evidence"] = self.evidence
        if self.recommendation is not None:
            data["recommendation"] = self.recommendation
        return data


class SecurityChecker:
    """Performs targeted security checks against MCP servers."""

    def __init__(
        self,
        *,
        timeout: int = 10,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
    ) -> None:
        self.timeout = timeout
        self._client_factory = client_factory

    async def analyze(self, target: str) -> Dict[str, Any]:
        """Run the full security auditing workflow."""

        normalized_target, parsed_target = self._normalize_target(target)
        findings: List[SecurityFinding] = []

        is_http_target = parsed_target.scheme in {"http", "https"}

        if is_http_target:
            async with self._build_client() as session:
                findings.extend(
                    await self._check_authentication(session, normalized_target)
                )
        else:
            # Non-HTTP transports (e.g., stdio) cannot be probed via HTTP checks
            findings.append(
                SecurityFinding(
                    vulnerability_id="MCP-NET-000",
                    title="Network Scan Skipped",
                    description="Security scan cannot perform HTTP checks for non-HTTP transports",
                    level=VulnerabilityLevel.INFO,
                    category="Network Security",
                    affected_component=str(parsed_target),
                    recommendation="Run the server with an HTTP endpoint to enable network probing",
                )
            )

        findings.extend(self._check_network_exposure(parsed_target))

        summary = self._summarize(findings)

        return {
            "target": normalized_target,
            "timestamp": self._current_timestamp(),
            "findings": [finding.to_dict() for finding in findings],
            "summary": summary,
            "statistics": {
                "total_findings": len(findings),
                **summary,
            },
        }

    def _build_client(self) -> httpx.AsyncClient:
        """Create an async HTTP client for outbound checks."""

        if self._client_factory:
            return self._client_factory()

        # We intentionally disable certificate verification to allow
        # scanning self-signed development servers.
        return httpx.AsyncClient(
            timeout=self.timeout,
            verify=False,
            follow_redirects=True,
        )

    @staticmethod
    def _normalize_target(target: str) -> Tuple[str, httpx.URL]:
        """Ensure the target includes a scheme and return parsed URL."""

        parsed = urlparse(target)
        if not parsed.scheme:
            parsed = urlparse(f"http://{target}")
        normalized = urlunparse(parsed)
        return normalized, httpx.URL(normalized)

    async def _check_authentication(
        self, session: httpx.AsyncClient, target: str
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        try:
            async with session.stream("GET", target, timeout=self.timeout) as response:
                headers = response.headers

                has_auth = headers.get("Authorization") is not None
                has_challenge = "www-authenticate" in headers

                if not has_auth and not has_challenge:
                    findings.append(
                        SecurityFinding(
                            vulnerability_id="MCP-AUTH-001",
                            title="Missing Authentication",
                            description="MCP server response did not advertise any authentication requirements",
                            level=VulnerabilityLevel.CRITICAL,
                            category="Authentication",
                            affected_component=target,
                            evidence="No Authorization or WWW-Authenticate headers detected",
                            recommendation="Require API keys, OAuth tokens, or delegated authentication",
                        )
                    )

                auth_header = headers.get("Authorization", "")
                if auth_header.lower().startswith("basic"):
                    findings.append(
                        SecurityFinding(
                            vulnerability_id="MCP-AUTH-002",
                            title="Weak Authentication Method",
                            description="Server advertises Basic authentication which is vulnerable to credential interception",
                            level=VulnerabilityLevel.HIGH,
                            category="Authentication",
                            affected_component=target,
                            evidence=f"Basic auth header snippet: {auth_header[:32]}...",
                            recommendation="Switch to bearer tokens or short-lived OAuth credentials",
                        )
                    )

        except (httpx.RequestError, httpx.TimeoutException) as exc:
            findings.append(
                SecurityFinding(
                    vulnerability_id="MCP-CONN-001",
                    title="Connection Error",
                    description=f"Unable to reach MCP target: {exc!s}",
                    level=VulnerabilityLevel.INFO,
                    category="Connectivity",
                    affected_component=target,
                )
            )

        return findings

    @staticmethod
    def _check_network_exposure(parsed_url: httpx.URL) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        hostname = parsed_url.host or ""

        if hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
            findings.append(
                SecurityFinding(
                    vulnerability_id="MCP-NET-002",
                    title="Local Network Binding",
                    description="Server is bound to a loopback interface",
                    level=VulnerabilityLevel.INFO,
                    category="Network Security",
                    affected_component=hostname,
                    recommendation="Limit exposure when promoting to shared environments",
                )
            )
        elif hostname:
            findings.append(
                SecurityFinding(
                    vulnerability_id="MCP-NET-001",
                    title="External Network Exposure",
                    description="Server appears accessible from external networks",
                    level=VulnerabilityLevel.MEDIUM,
                    category="Network Security",
                    affected_component=hostname,
                    evidence=f"Resolved host: {hostname}",
                    recommendation="Ensure firewall and network ACLs restrict unnecessary access",
                )
            )

        return findings

    @staticmethod
    def _summarize(findings: Iterable[SecurityFinding]) -> Dict[str, int]:
        summary = {level.value: 0 for level in VulnerabilityLevel}
        for finding in findings:
            summary[finding.level.value] += 1
        return summary

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "SecurityChecker",
    "SecurityFinding",
    "VulnerabilityLevel",
]
