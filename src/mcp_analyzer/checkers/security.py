"""Security auditing checker for MCP servers and configurations."""

from __future__ import annotations

import ipaddress
import os
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
        verify: bool = True,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self.verify = verify
        self._client_factory = client_factory
        self._provided_env_vars = env_vars or {}

    async def analyze(self, target: str) -> Dict[str, Any]:
        """Run the full security auditing workflow."""

        normalized_target, parsed_target = self._normalize_target(target)
        findings: List[SecurityFinding] = []

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

        # TLS verification can be configured via the verify parameter
        return httpx.AsyncClient(
            timeout=self.timeout,
            verify=self.verify,
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

    @staticmethod
    def _check_network_exposure(parsed_url: httpx.URL) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        hostname = parsed_url.host or ""

        if hostname == "localhost":
            # Special case for localhost hostname
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
            try:
                ip = ipaddress.ip_address(hostname)

                if ip.is_loopback:
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
                elif ip.is_unspecified:
                    findings.append(
                        SecurityFinding(
                            vulnerability_id="MCP-NET-003",
                            title="Wildcard Binding",
                            description="Server is bound to all network interfaces (wildcard binding)",
                            level=VulnerabilityLevel.MEDIUM,
                            category="Network Security",
                            affected_component=hostname,
                            evidence=f"Wildcard IP address: {hostname}",
                            recommendation="Bind to specific interfaces to limit network exposure",
                        )
                    )
                else:
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
            except ValueError:
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
    def _check_api_token_usage(
        target: str, provided_env: Optional[Dict[str, str]] = None
    ) -> List[SecurityFinding]:
        """Detect usage of API tokens for MCP server access.

        Heuristics:
        - Looks for token-like variable names in provided_env (from NPX invocation)
          and in the current process environment.
        - Flags query parameters in the target containing token-like names.
        - Medium severity to highlight risks of long-lived static tokens.
        """
        findings: List[SecurityFinding] = []

        token_key_patterns = [
            "token",
            "api_key",
            "apikey",
            "access_token",
            "auth_token",
            "bearer",
            "jwt",
        ]

        def key_is_token_like(key: str) -> bool:
            kl = key.lower()
            return any(p in kl for p in token_key_patterns)

        # Collect token-like keys from provided env and process env
        provided = provided_env or {}
        proc_env = os.environ

        provided_hits = [k for k, v in provided.items() if key_is_token_like(k) and v]
        env_hits = [
            k
            for k, v in proc_env.items()
            if key_is_token_like(k) and v and len(v) >= 16
        ]

        # Check target URL query params for token-like names
        try:
            parsed = urlparse(target)
            query = parsed.query or ""
            query_hits = []
            if query:
                for part in query.split("&"):
                    if "=" in part:
                        name, _ = part.split("=", 1)
                        if key_is_token_like(name):
                            query_hits.append(name)
        except Exception:
            query_hits = []

        hit_sets = {
            "env": sorted(set(env_hits)),
            "provided": sorted(set(provided_hits)),
            "url_query": sorted(set(query_hits)),
        }

        total_hits = sum(len(v) for v in hit_sets.values())
        if total_hits == 0:
            return findings

        evidence_parts = []
        if hit_sets["provided"]:
            evidence_parts.append(
                f"provided env vars: {', '.join(hit_sets['provided'])}"
            )
        if hit_sets["env"]:
            evidence_parts.append(
                f"process env vars: {', '.join(hit_sets['env'][:5])}"
                + (" + more" if len(hit_sets["env"]) > 5 else "")
            )
        if hit_sets["url_query"]:
            evidence_parts.append(f"url params: {', '.join(hit_sets['url_query'])}")

        evidence = "; ".join(evidence_parts) if evidence_parts else None

        findings.append(
            SecurityFinding(
                vulnerability_id="MCP-AUTH-001",
                title="API Token Authentication Detected",
                description=(
                    "The MCP server appears to rely on static API tokens/keys for authentication. "
                    "Long-lived tokens increase risk of leakage and unauthorized access."
                ),
                level=VulnerabilityLevel.MEDIUM,
                category="Authentication",
                affected_component="configuration",
                evidence=evidence,
                recommendation=(
                    "Use short-lived, scoped credentials (e.g., OAuth/OIDC) or ephemeral tokens, "
                    "store secrets in a secure manager, and rotate keys regularly. Avoid passing tokens "
                    "via CLI or URL where they can be logged."
                ),
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
